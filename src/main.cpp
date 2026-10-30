#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <time.h>

/*
 * PlatformIO ESP32 -- Solar telemetry over MQTT
 *
 *   USE_FAKE_MODBUS = 1  -> Wokwi simulator. RS485 is faked (Wokwi can't drive
 *                           real RS485). WiFi + MQTT publish path is real.
 *   USE_FAKE_MODBUS = 0  -> real hardware. Reads the Solis inverter over
 *                           RS485/Modbus (FC04 input registers).
 *
 *   Select with PlatformIO env:
 *     [env:esp32dev]  -> sim  (build flag -DUSE_FAKE_MODBUS=1)
 *     [env:esp32-hw]  -> real (build flag -DUSE_FAKE_MODBUS=0)
 *
 * Resilience:
 *   - NTP time sync -> telemetry "ts" is real Unix epoch (UTC).
 *   - MQTT Last-Will + retained birth on .../status (online/offline).
 *   - Non-blocking WiFi/MQTT reconnect; readings keep flowing while offline
 *     into a RAM ring buffer that flushes (oldest first) on reconnect.
 *   - Commands on .../cmd: {"action":"reboot"}, {"set_interval":<seconds>}.
 *
 * Dependencies (platformio.ini lib_deps):
 *   knolleary/PubSubClient
 *   bblanchon/ArduinoJson
 *   4-20ma/ModbusMaster   (only compiled when USE_FAKE_MODBUS = 0)
 */

#ifndef USE_FAKE_MODBUS
#define USE_FAKE_MODBUS 1
#endif

#ifndef USE_TLS
#define USE_TLS 0       // 1 = TLS 8883 + username/password (production broker)
#endif

#if !USE_FAKE_MODBUS
#include <ModbusMaster.h>
#endif

#if USE_TLS || USE_FAKE_MODBUS
#include <WiFiClientSecure.h>
#endif
#if USE_FAKE_MODBUS
#include <HTTPClient.h>                // météo réelle Open-Meteo (simulation)
#endif

#include "solar_sim.h"                 // modèle de production PV réaliste (simulation)
const double SIM_ENCRASSEMENT = 0.0;   // encrassement simulé (0 = propre, 1 = nul)
// Démonstration d'un défaut de chaîne : 1 = chaîne 2 coupée (courant nul).
// Se règle aussi à la compilation : build_flags = -DSIM_DEFAUT_CHAINE2=1
#ifndef SIM_DEFAUT_CHAINE2
#define SIM_DEFAUT_CHAINE2 0
#endif
// Désappariement normal de la chaîne 2 (fractions, ±1 %), tiré une fois au
// démarrage dans setup() : l'écart entre chaînes reste stable d'un message à l'autre.
double simEcartV2 = 0.0;
double simEcartI2 = 0.0;

//  SITE IDENTITY  — installation résidentielle, région de Metlaoui (Tunisie)
//    Array       : 18 x JA Solar JAM66D45-600/LB = 10.8 kWp (2 strings x 9)
//    Inverter    : Solis S5-GR3P12K, 12 kW, 3-phase, 2 MPPT, RS485
//
//  SITE_ID + INV_SERIAL below are the source of truth for the MQTT topics
//  AND must match the backend seed (backend/app/seed.py). Change them in
//  both places together, or telemetry will auto-register a second inverter.
// =====================================================================

// ---- WiFi ----
// Wokwi simulator: SSID "Wokwi-GUEST", empty password (leave as-is for sim).
// Real hardware: replace with the site's WiFi credentials.
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

// ---- MQTT broker ----
// Sim (USE_TLS=0): public plaintext broker on 1883, no auth.
// Production (USE_TLS=1): your Mosquitto on 8883 with per-device credentials;
//   paste the broker CA below and set this device's username/password.
#if USE_TLS
const char* MQTT_HOST = "YOUR_BROKER_HOST";    // same value used in gen-certs.sh
const int   MQTT_PORT = 8883;
const char* MQTT_USER = "dev-solis01";         // this device's broker user
const char* MQTT_PASS = "CHANGE_ME";           // matches mosquitto_passwd entry
// Broker CA certificate — paste the contents of broker/certs/ca.crt:
const char* CA_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
PASTE_broker_certs_ca.crt_HERE
-----END CERTIFICATE-----
)EOF";
#else
const char* MQTT_HOST = "broker.hivemq.com";   // or test.mosquitto.org
const int   MQTT_PORT = 1883;
const char* MQTT_USER = "";                    // anonymous on the public broker
const char* MQTT_PASS = "";
#endif

const int   SITE_ID    = 1;                    // internal site id (matches seed)
const char* INV_SERIAL = "SOLIS-S5GR3P12K-01"; // TODO: replace with the real
                                               // inverter nameplate serial,
                                               // then update the backend seed.
uint32_t    PUBLISH_MS = 500;   // ms — cadence 0,5 s (temps réel)

// ---- Energy persistence state (simulator & backend sync) ----
Preferences prefs;
const char* PREFS_NS = "solar";
const char* PREF_KEY_ETOTAL = "e_total";
const char* PREF_KEY_EDAY = "e_day";
const char* PREF_KEY_DAYKEY = "day_key";

// ---- NTP (UTC; "ts" is Unix epoch seconds) ----
const char* NTP1 = "pool.ntp.org";
const char* NTP2 = "time.google.com";

#if USE_TLS
WiFiClientSecure net;
#else
WiFiClient       net;
#endif
PubSubClient mqtt(net);
char telemetryTopic[80];
char cmdTopic[80];
char statusTopic[80];
uint32_t lastPublish = 0;

// ---- Simulated cumulative energy (kWh) ----
// Real inverters expose monotonic energy counters, so the simulator must too:
// e_total emulates a lifetime meter that only ever increases, and e_day
// resets at the day rollover. e_day is the exact energy produced since sunrise
// (real time, no acceleration) so measured/reference stays consistent with
// PVsyst; e_total advances by the same increments (persisted in NVS).
double   simETotalKwh    = 9000.0;   // lifetime base
double   simEDayKwh      = 0.0;
uint32_t simEDayKey       = 0;       // epoch/86400 of the current accumulation day

// =====================================================================
//  RS485 / Modbus  (real hardware only)
// =====================================================================
#if !USE_FAKE_MODBUS

// MAX485 transceiver wiring
#define RS485_RX      16   // ESP32 RX2  <- MAX485 RO
#define RS485_TX      17   // ESP32 TX2  -> MAX485 DI
#define RS485_DE_RE    4   // MAX485 DE+RE tied together -> GPIO4
#define MODBUS_SLAVE   1   // Solis default Modbus address

ModbusMaster node;
void preTransmission()  { digitalWrite(RS485_DE_RE, HIGH); }  // drive bus (TX)
void postTransmission() { digitalWrite(RS485_DE_RE, LOW);  }  // listen (RX)

// ---------------------------------------------------------------------
//  Solis S5-GR3P string-inverter register map.
//  Source: Solis "RS485_MODBUS Communication Protocol Ver19" (read input
//  registers, function code 0x04). Cross-checked against the open-source
//  Pho3niX90/solis_modbus Home Assistant integration.
//  9600 8N1, slave id 1. 32-bit values are high-word first (big-endian).
//  Addresses are the on-the-wire offsets used by working integrations
//  (the protocol table is 1-based; these are that value minus 1).
//
//  >>> VERIFY against your unit's protocol version before trusting values.
//      Quick check: pv_v (DC Voltage 1) should read ~300–400 V in sun.
// ---------------------------------------------------------------------
struct Metric {
  const char* key;     // canonical telemetry field
  uint16_t    addr;    // input-register address
  uint8_t     words;   // 1 = 16-bit, 2 = 32-bit
  float       scale;   // raw * scale = engineering value
  bool        isSigned;
};

// Entrée PV 2 (chaîne 2). Adresses À CONFIRMER dans le protocole Solis
// « RS485_MODBUS Communication Protocol » de l'onduleur installé : elles
// suivent 3021/3022 (tension et courant de l'entrée 1) dans la carte de
// l'intégration solis_modbus, mais n'ont pas été vérifiées sur le document
// ni sur l'onduleur. Contrôle : au soleil, pv2_v ≈ pv_v (300 – 400 V).
constexpr uint16_t REG_PV2_V = 3023;   // À CONFIRMER — tension DC entrée 2 (0,1 V)
constexpr uint16_t REG_PV2_I = 3024;   // À CONFIRMER — courant DC entrée 2 (0,1 A)

const Metric METRICS[] = {
  // key       addr  words scale   signed
  { "pv_v",    3021, 1,    0.1f,   false },  // DC voltage, string 1
  { "pv_i",    3022, 1,    0.1f,   false },  // DC current, string 1
  { "pv2_v",   REG_PV2_V, 1, 0.1f, false },  // DC voltage, string 2 (À CONFIRMER)
  { "pv2_i",   REG_PV2_I, 1, 0.1f, false },  // DC current, string 2 (À CONFIRMER)
  { "pv_p",    3006, 2,    1.0f,   false },  // total DC output power (W)
  { "ac_v",    3033, 1,    0.1f,   false },  // A-phase grid voltage
  { "ac_i",    3036, 1,    0.1f,   false },  // A-phase grid current
  { "freq",    3042, 1,    0.01f,  false },  // grid frequency (Hz)
  { "e_day",   3014, 1,    0.1f,   false },  // energy today (kWh)
  { "e_total", 3008, 2,    1.0f,   false },  // total energy (kWh)
  { "temp",    3041, 1,    0.1f,   true  },  // inverter temperature (°C, signed)
};
const size_t NUM_METRICS = sizeof(METRICS) / sizeof(METRICS[0]);

// Reads one metric. Returns false on Modbus error (caller serializes null).
bool readMetric(const Metric& m, float& out) {
  uint8_t rc = node.readInputRegisters(m.addr, m.words);
  if (rc != node.ku8MBSuccess) {
    Serial.printf("  modbus read %s @%u failed rc=0x%02X\n", m.key, m.addr, rc);
    return false;
  }
  uint16_t hi = node.getResponseBuffer(0);
  if (m.words == 2) {
    uint16_t lo = node.getResponseBuffer(1);
    uint32_t v  = ((uint32_t)hi << 16) | lo;
    out = (m.isSigned ? (float)(int32_t)v : (float)v) * m.scale;
  } else {
    out = (m.isSigned ? (float)(int16_t)hi : (float)hi) * m.scale;
  }
  return true;
}

static inline float round2(float v) { return roundf(v * 100.0f) / 100.0f; }

#else  // ---- USE_FAKE_MODBUS: simulator curve for Wokwi ----

uint32_t nowEpoch();   // déclarations anticipées (définies plus bas)
bool timeSynced();

// Facteur de production PV réaliste : courbe en cloche selon l'heure du jour
// (0 la nuit, maximum à midi), atténuée par l'encrassement simulé. Metlaoui
// est en UTC+1 ; on décale l'heure epoch (UTC) d'une heure.
double localHour() {
  double hod = std::fmod(nowEpoch() / 3600.0 + 1.0, 24.0);   // heure locale (UTC+1)
  if (hod < 0) hod += 24.0;
  return hod;
}

float fakeSolarFactor() {
  return (float)solar::factor(localHour(), SIM_ENCRASSEMENT);
}

// Mois courant (1..12), pour caler la puissance crête sur la référence PVsyst.
int currentMonth() {
  time_t t = (time_t)nowEpoch() + 3600;   // UTC+1
  struct tm tmv;
  gmtime_r(&t, &tmv);
  return tmv.tm_mon + 1;
}

// ---- Météo réelle du site (Open-Meteo) ----
// Irradiance dans le plan des modules (30°, plein sud) et température de l'air,
// au pas de 15 min pour la journée UTC en cours. La production simulée suit
// ainsi l'ensoleillement réel de Metlaoui (lever/coucher, nuages, saison).
const char* METEO_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=34.32&longitude=8.40"
  "&minutely_15=global_tilted_irradiance,temperature_2m&tilt=30&azimuth=0"
  "&timezone=GMT&forecast_days=1";
const int      METEO_N = 96;                     // 24 h × 4
const uint32_t METEO_REFRESH_MS = 15UL * 60000;  // nouvelle série toutes les 15 min
const uint32_t METEO_RETRY_MS   = 60000;         // nouvel essai après un échec
float    meteoGti[METEO_N];
float    meteoTair[METEO_N];
uint32_t meteoJour = 0;            // epoch/86400 de la série chargée (0 = aucune)
uint32_t meteoDernierEssaiMs = 0;
uint32_t meteoDernierSuccesMs = 0;

bool chargerMeteo() {
  WiFiClientSecure tls;
  tls.setInsecure();               // simulation : pas de vérification du certificat
  HTTPClient http;
  http.useHTTP10(true);            // pas de réponse « chunked » → lecture en flux
  http.setTimeout(8000);
  if (!http.begin(tls, METEO_URL)) return false;
  const int code = http.GET();
  if (code != 200) {
    Serial.printf("Open-Meteo HTTP %d\n", code);
    http.end();
    return false;
  }
  JsonDocument filtre;
  filtre["minutely_15"]["global_tilted_irradiance"] = true;
  filtre["minutely_15"]["temperature_2m"] = true;
  JsonDocument doc;
  const DeserializationError err =
    deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filtre));
  http.end();
  JsonArray gti  = doc["minutely_15"]["global_tilted_irradiance"];
  JsonArray tair = doc["minutely_15"]["temperature_2m"];
  if (err || gti.size() < (size_t)METEO_N || tair.size() < (size_t)METEO_N) {
    Serial.printf("Open-Meteo : réponse invalide (%s)\n", err.c_str());
    return false;
  }
  for (int i = 0; i < METEO_N; i++) {
    meteoGti[i]  = gti[i]  | 0.0f;    // null → 0
    meteoTair[i] = tair[i] | 20.0f;
  }
  meteoJour = nowEpoch() / 86400;
  Serial.println("Open-Meteo : irradiance du jour chargée");
  return true;
}

// Appelée dans loop() : charge / rafraîchit la série sans bloquer les envois
// plus d'une fois toutes les 15 min (ou 1 min après un échec).
void majMeteo() {
  if (!timeSynced() || WiFi.status() != WL_CONNECTED) return;
  const uint32_t now = millis();
  const bool aJour = meteoJour == nowEpoch() / 86400;
  if (aJour && now - meteoDernierSuccesMs < METEO_REFRESH_MS) return;
  if (meteoDernierEssaiMs != 0 && now - meteoDernierEssaiMs < METEO_RETRY_MS) return;
  meteoDernierEssaiMs = now;
  if (chargerMeteo()) meteoDernierSuccesMs = now;
}

#endif

// =====================================================================
//  Time: real epoch once NTP has synced, else fall back to seconds-since-boot
// =====================================================================
bool timeSynced() { return time(nullptr) > 1700000000; }  // ~2023-11

uint32_t nowEpoch() {
  time_t t = time(nullptr);
  return timeSynced() ? (uint32_t)t : (uint32_t)(millis() / 1000);
}

// =====================================================================
//  Offline ring buffer — holds telemetry while MQTT is down
// =====================================================================
#define RB_N 30
String   rb[RB_N];
int      rbHead = 0, rbCount = 0;

void rbPush(const char* payload) {
  rb[(rbHead + rbCount) % RB_N] = payload;
  if (rbCount < RB_N) rbCount++;
  else rbHead = (rbHead + 1) % RB_N;   // overwrite oldest
}

void saveEnergyState();

void rbFlush() {
  while (rbCount > 0 && mqtt.connected()) {
    String& s = rb[rbHead];
    if (mqtt.publish(telemetryTopic, (const uint8_t*)s.c_str(), s.length(), false)) {
      rbHead = (rbHead + 1) % RB_N;
      rbCount--;
    } else break;   // broker pushed back — try again next cycle
  }
}

// =====================================================================
//  Build canonical telemetry JSON, then publish or buffer
// =====================================================================
void buildAndPublish() {
  JsonDocument doc;
  doc["site_id"] = SITE_ID;
  doc["inv"]     = INV_SERIAL;
  doc["ts"]      = nowEpoch();

#if !USE_FAKE_MODBUS
  // ---- real inverter over Modbus ----
  for (size_t i = 0; i < NUM_METRICS; i++) {
    float v;
    if (readMetric(METRICS[i], v)) doc[METRICS[i].key] = round2(v);
    else                           doc[METRICS[i].key] = nullptr;  // failed read -> null
  }
  doc["batt_v"]   = nullptr;   // string inverter: no battery
  doc["batt_i"]   = nullptr;
  doc["batt_soc"] = nullptr;
  // The Solis "status" register (3043) is a working-mode code, not a fault
  // code, so we do NOT map it to alarm (would raise false alerts).
  // TODO: map a real fault register from the protocol once confirmed.
  doc["alarm"] = 0;
  if (node.readInputRegisters(3043, 1) == node.ku8MBSuccess)
    Serial.printf("  inverter status reg(3043)=%u\n", node.getResponseBuffer(0));

#else
  // ---- simulator ----
  const int    mois = currentMonth();
  const uint32_t dayKey = nowEpoch() / 86400;
  const double minutesUtc = (nowEpoch() % 86400) / 60.0;
  double gIncl, tAir, eDay;      // irradiance plan des modules, air, énergie du jour
  if (meteoJour == dayKey) {
    // Météo réelle : production = irradiance inclinée × P_crête × PR du mois.
    // e_day = intégrale de l'irradiance depuis 00:00 UTC → exact même après un
    // démarrage en cours de journée ou un redémarrage, sans accélération.
    gIncl = solar::serieInstantanee(meteoGti, METEO_N, minutesUtc);
    tAir  = solar::serieInstantanee(meteoTair, METEO_N, minutesUtc);
    eDay  = solar::energieDepuisIrradiation(
              solar::serieIntegraleWhM2(meteoGti, METEO_N, minutesUtc), mois, SIM_ENCRASSEMENT);
  } else {
    // Repli sans Internet : courbe « ciel clair » calée sur la référence du mois.
    const double peakW = solar::peakWForMonth(mois);
    const double pCiel = fakeSolarFactor() * peakW;
    gIncl = pCiel / (solar::P_CRETE_W * solar::prReference(mois) * (1.0 - SIM_ENCRASSEMENT)) * 1000.0;
    tAir  = 22.0;
    eDay  = solar::energySinceSunriseKwh(localHour(), SIM_ENCRASSEMENT, peakW);
  }

  // Facteur de performance variable dans [0,76 ; 0,94] : la performance
  // instantanée affichée reste entre 75 % et 95 % de la production attendue.
  float nowSec = millis() / 1000.0f;
  const double perf = solar::facteurPerformance(nowSec, random(-100, 101) / 100.0);
  float pvP = (float)(solar::puissanceDepuisIrradiance(gIncl, mois, SIM_ENCRASSEMENT) * perf);
  // Énergie du jour cohérente avec la puissance : facteur moyen appliqué
  eDay *= solar::PERF_MOYENNE;
  const double tCell = solar::temperatureCellule(tAir, gIncl);
  float pvV = (float)solar::tensionChaine(gIncl, tCell);
  if (pvV > 0) pvV += random(-5, 6) / 10.0f;   // ±0,5 V
  // Deux chaînes : pv_v / pv_i = entrée PV 1 (registres 3021/3022 du mode
  // matériel), pv2_v / pv2_i = entrée PV 2 : même calcul, désappariement stable
  // (simEcartV2, simEcartI2) et son propre bruit de tension ±0,5 V ; coupée si
  // SIM_DEFAUT_CHAINE2 = 1. pv_p = pv_v × pv_i + pv2_v × pv2_i.
  const solar::MesuresChaines ch = solar::deuxChaines(
      pvP, pvV, simEcartV2, simEcartI2, random(-5, 6) / 10.0, SIM_DEFAUT_CHAINE2 != 0);
  pvP = (float)ch.puissanceTotale();
  if (SIM_DEFAUT_CHAINE2) eDay *= 0.5;          // une seule chaîne produit
  doc["pv_v"]    = round(ch.v1 * 10) / 10.0;
  doc["pv_i"]    = round(ch.i1 * 100) / 100.0;
  doc["pv2_v"]   = round(ch.v2 * 10) / 10.0;
  doc["pv2_i"]   = round(ch.i2 * 100) / 100.0;
  doc["pv_p"]    = round(pvP * 10) / 10.0;
  float acV = 230.0f + sin(nowSec * 0.9f) * 2.5f + random(-5, 6) / 10.0f; // fluctuation ±~3 V
  doc["ac_v"]    = round(acV * 10) / 10.0;
  // Puissance AC triphasée = puissance PV × rendement onduleur (≈ 97,5 % en
  // charge, plus faible à très faible charge).
  float efficiency = 0.975f - 0.05f * expf(-pvP / 600.0f);
  float acP = pvP * efficiency;
  doc["ac_i"]    = round((acP / (3.0f * (acV > 1 ? acV : 230.0f))) * 100) / 100.0;
  doc["freq"]    = round((50.0f + random(-3, 4) / 100.0f) * 100) / 100.0;   // 50 Hz ±0,03
  uint32_t nowMs = millis();
  if (simEDayKey == 0) simEDayKey = dayKey;
  if (dayKey != simEDayKey) {
    simEDayKwh = 0.0;
    simEDayKey = dayKey;
  }
  if (eDay > simEDayKwh) simETotalKwh += eDay - simEDayKwh;
  simEDayKwh = eDay;
  doc["e_day"]   = round(simEDayKwh   * 100) / 100.0;
  doc["e_total"] = round(simETotalKwh * 100) / 100.0;
  doc["batt_v"]  = nullptr;   // no battery on this inverter
  doc["batt_i"]  = nullptr;
  doc["batt_soc"]= nullptr;
  doc["temp"]    = round((solar::temperatureOnduleur(tAir, pvP) + random(-2, 3) / 10.0f) * 10) / 10.0;
  doc["alarm"]   = 0;

  static uint32_t lastEnergySaveMs = 0;
  if (nowMs - lastEnergySaveMs >= 60000) {
    saveEnergyState();
    lastEnergySaveMs = nowMs;
  }
#endif

  char payload[512];
  size_t n = serializeJson(doc, payload, sizeof(payload));

  if (mqtt.connected()) {
    rbFlush();   // drain any backlog first (keeps order)
    bool ok = mqtt.publish(telemetryTopic, (const uint8_t*)payload, n, false);
    if (ok) Serial.printf("publish OK -> %s\n", payload);
    else  { rbPush(payload); Serial.println("publish FAIL -> buffered"); }
  } else {
    rbPush(payload);
    Serial.printf("offline -> buffered (%d/%d) %s\n", rbCount, RB_N, payload);
  }
}

void saveEnergyState() {
  prefs.begin(PREFS_NS, false);
  prefs.putString(PREF_KEY_ETOTAL, String(simETotalKwh, 4));
  prefs.putString(PREF_KEY_EDAY, String(simEDayKwh, 4));
  prefs.putUInt(PREF_KEY_DAYKEY, simEDayKey);
  prefs.end();
}

void loadEnergyState() {
  prefs.begin(PREFS_NS, false);
  String total = prefs.getString(PREF_KEY_ETOTAL, "");
  String today = prefs.getString(PREF_KEY_EDAY, "");
  simEDayKey = prefs.getUInt(PREF_KEY_DAYKEY, 0);
  prefs.end();

  if (total.length()) simETotalKwh = total.toDouble();
  if (today.length()) simEDayKwh = today.toDouble();

  uint32_t dayKey = nowEpoch() / 86400;
  if (simEDayKey == 0) simEDayKey = dayKey;
  if (dayKey != simEDayKey) {
    simEDayKwh = 0.0;
    simEDayKey = dayKey;
    saveEnergyState();
  }
}

void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg; for (unsigned i = 0; i < len; i++) msg += (char)payload[i];
  Serial.printf("cmd on %s: %s\n", topic, msg.c_str());

  JsonDocument d;
  if (deserializeJson(d, msg)) return;   // ignore malformed

  const char* action = d["action"] | "";
  if (strcmp(action, "reboot") == 0) {
    Serial.println("reboot command -> restarting in 200ms");
    mqtt.publish(statusTopic, "offline", true);   // clean offline before reboot
    delay(200);
    ESP.restart();
  }
  if (d["set_interval"].is<float>()) {   // secondes, décimales acceptées (0.5)
    PUBLISH_MS = max<uint32_t>(200, (uint32_t)(d["set_interval"].as<float>() * 1000));
    Serial.printf("set_interval -> %u ms\n", PUBLISH_MS);
  }

  if (d["sync_energy"].is<bool>() && d["sync_energy"].as<bool>()) {
    if (d["e_total"].is<float>() || d["e_total"].is<double>()) {
      simETotalKwh = d["e_total"].as<double>();
    }
    if (d["e_day"].is<float>() || d["e_day"].is<double>()) {
      simEDayKwh = d["e_day"].as<double>();
    }
    uint32_t dayKey = nowEpoch() / 86400;
    if (d["day_key"].is<unsigned long>()) {
      simEDayKey = d["day_key"].as<unsigned long>();
    } else {
      simEDayKey = dayKey;
    }
    saveEnergyState();
    Serial.printf("synced energy e_total=%.2f e_day=%.2f day_key=%u\n", simETotalKwh, simEDayKwh, simEDayKey);
  }
}

// =====================================================================
//  Non-blocking connectivity
// =====================================================================
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  static uint32_t last = 0;
  if (millis() - last < 5000) return;
  last = millis();
  Serial.println("WiFi down — reconnecting...");
  WiFi.reconnect();
}

void ensureMQTT() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  static uint32_t last = 0;
  if (millis() - last < 2000) return;     // throttle attempts
  last = millis();

  Serial.print("MQTT connecting...");
  String id = String("esp32-") + INV_SERIAL + "-" + String(random(10000));
  // Last-Will: broker publishes retained "offline" if we drop unexpectedly.
  // Use credentials when set (production), else anonymous (public test broker).
  bool ok = (strlen(MQTT_USER) > 0)
    ? mqtt.connect(id.c_str(), MQTT_USER, MQTT_PASS, statusTopic, 0, true, "offline")
    : mqtt.connect(id.c_str(), statusTopic, 0, true, "offline");
  if (ok) {
    Serial.println(" connected");
    mqtt.publish(statusTopic, "online", true);   // retained birth
    mqtt.subscribe(cmdTopic);                     // re-subscribe every reconnect
    rbFlush();                                     // drain backlog
  } else {
    Serial.printf(" failed rc=%d\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  snprintf(telemetryTopic, sizeof(telemetryTopic), "site/%d/inv/%s/telemetry", SITE_ID, INV_SERIAL);
  snprintf(cmdTopic,       sizeof(cmdTopic),       "site/%d/inv/%s/cmd",       SITE_ID, INV_SERIAL);
  snprintf(statusTopic,    sizeof(statusTopic),    "site/%d/inv/%s/status",    SITE_ID, INV_SERIAL);
  loadEnergyState();

#if !USE_FAKE_MODBUS
  pinMode(RS485_DE_RE, OUTPUT);
  digitalWrite(RS485_DE_RE, LOW);                 // start in receive mode
  Serial2.begin(9600, SERIAL_8N1, RS485_RX, RS485_TX);
  node.begin(MODBUS_SLAVE, Serial2);
  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);
  Serial.println("Modbus RTU master ready (Serial2 9600 8N1, slave 1)");
#else
  Serial.println("SIMULATION mode (USE_FAKE_MODBUS=1) — Modbus faked");
  // Désappariement de la chaîne 2, tiré une fois (générateur matériel de l'ESP32)
  simEcartV2 = random(-1000, 1001) / 100000.0;   // [−1 % ; +1 %]
  simEcartI2 = random(-1000, 1001) / 100000.0;
  Serial.printf("Chaîne 2 simulée : écart tension %+.2f %%, courant %+.2f %%%s\n",
                simEcartV2 * 100, simEcartI2 * 100, SIM_DEFAUT_CHAINE2 ? " — DÉFAUT (chaîne coupée)" : "");
#endif

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  configTime(0, 0, NTP1, NTP2);                   // UTC epoch via NTP

#if USE_TLS
  net.setCACert(CA_CERT);                         // verify the broker against our CA
#endif
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setCallback(onMessage);
}

void loop() {
  ensureWiFi();
  ensureMQTT();
  mqtt.loop();
#if USE_FAKE_MODBUS
  majMeteo();                     // irradiance réelle du site (simulation)
#endif

  static bool announced = false;
  if (!announced && timeSynced()) {
    announced = true;
    Serial.printf("NTP synced — epoch=%u\n", nowEpoch());
  }

  uint32_t now = millis();
  if (now - lastPublish >= PUBLISH_MS) { lastPublish = now; buildAndPublish(); }
}
