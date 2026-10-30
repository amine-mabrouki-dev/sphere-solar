#pragma once
// ============================================================================
//  Modèle de production PV réaliste pour la SIMULATION (mode Wokwi uniquement).
//  Fournit un facteur 0..1 suivant l'heure du jour (courbe en cloche centrée
//  sur midi solaire), atténué par un facteur d'encrassement (poussière).
//  En-tête pur (aucune dépendance Arduino) → testable en natif avec g++.
// ============================================================================
#include <cmath>

namespace solar {

constexpr double PI_ = 3.14159265358979323846;
constexpr double LEVER = 6.0;      // début de production (heure locale)
constexpr double COUCHER = 18.0;   // fin de production

// Facteur journalier 0..1 selon l'heure du jour (0 la nuit, ~1 à midi).
inline double dayFactor(double hourOfDay) {
  if (hourOfDay <= LEVER || hourOfDay >= COUCHER) return 0.0;
  const double x = (hourOfDay - LEVER) / (COUCHER - LEVER);   // 0..1 sur la journée
  const double cloche = std::sin(PI_ * x);                    // 0 → 1 → 0
  return cloche * cloche;                                     // profil plus réaliste (plus pointu)
}

// Facteur effectif 0..1 : production du jour atténuée par l'encrassement (0..1).
inline double factor(double hourOfDay, double soiling) {
  const double s = soiling < 0.0 ? 0.0 : (soiling > 1.0 ? 1.0 : soiling);
  return dayFactor(hourOfDay) * (1.0 - s);
}

// Puissance PV instantanée (W) : facteur × puissance crête.
inline double powerW(double hourOfDay, double soiling, double peakW) {
  return factor(hourOfDay, soiling) * peakW;
}

// ---- Cohérence avec la référence PVsyst (backend/app/reference.py) ----
// E_Grid mensuel PVsyst (kWh) de l'installation 10,8 kWc, janvier → décembre.
constexpr double PVSYST_EGRID_KWH[12] = {
  1318, 1330, 1677, 1792, 1863, 1814, 1913, 1873, 1708, 1618, 1432, 1293};
constexpr int JOURS_MOIS[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
// Rendement simulé par rapport à la référence (installation propre, légères
// pertes réelles) → r ≈ 0,97 en mode mensuel, jamais au-dessus de 100 %.
constexpr double REALISME = 0.97;

// Énergie journalière attendue par PVsyst pour un mois 1..12 (kWh/jour).
inline double dailyReferenceKwh(int month) {
  const int m = (month < 1 ? 1 : (month > 12 ? 12 : month)) - 1;
  return PVSYST_EGRID_KWH[m] / JOURS_MOIS[m];
}

// Puissance crête simulée (W) telle qu'une journée complète produise
// REALISME × la référence du mois. L'intégrale de sin² sur la journée vaut la
// moitié de sa durée (6 h), d'où E = P × 6 h.
inline double peakWForMonth(int month) {
  return dailyReferenceKwh(month) * REALISME / ((COUCHER - LEVER) / 2.0) * 1000.0;
}

// ============================================================================
//  Modèle piloté par la MÉTÉO RÉELLE (Open-Meteo) — utilisé dès que la série
//  d'irradiance du jour est disponible ; le modèle « ciel clair » ci-dessus
//  ne sert plus que de repli (pas d'accès Internet).
// ============================================================================

// Installation (dossier technique) : 18 × JA Solar JAM66D45-600/LB = 10,8 kWc,
// 2 chaînes de 9 modules, plan incliné 30° plein sud, onduleur Solis 12 kW.
constexpr double P_CRETE_W = 10800.0;
constexpr double P_ONDULEUR_W = 12000.0;
constexpr int    MODULES_PAR_CHAINE = 9;
constexpr int    NB_CHAINES = 2;          // une chaîne par entrée PV (MPPT) de l'onduleur
constexpr double VMP_STC_V = 39.44;       // tension MPP d'un module (STC, fiche JA Solar JAM66D45-600/LB)
constexpr double COEF_TENSION = -0.0025;  // variation relative de tension par °C
constexpr double K_ECHAUFFEMENT = 0.03;   // °C par W/m² : T_cellule = T_air + k × G

// PR de référence PVsyst par mois (copie de backend/app/reference.py ;
// vérifié par backend/tests/test_constantes_mobile.py).
constexpr double PVSYST_PR[12] = {
  0.927, 0.917, 0.898, 0.883, 0.874, 0.860, 0.845, 0.847, 0.863, 0.880, 0.906, 0.926};

inline double prReference(int month) {
  const int m = (month < 1 ? 1 : (month > 12 ? 12 : month)) - 1;
  return PVSYST_PR[m];
}

// Puissance PV (W) pour une irradiance dans le plan des modules (W/m²) :
// P = P_crête × G_incl / 1000 × PR du mois × (1 − encrassement).
inline double puissanceDepuisIrradiance(double gIncl, int month, double soiling) {
  const double s = soiling < 0.0 ? 0.0 : (soiling > 1.0 ? 1.0 : soiling);
  const double g = gIncl > 0.0 ? gIncl : 0.0;
  return P_CRETE_W * g / 1000.0 * prReference(month) * (1.0 - s);
}

// Énergie (kWh) correspondant à une irradiation dans le plan des modules (Wh/m²).
inline double energieDepuisIrradiation(double hInclWhM2, int month, double soiling) {
  return puissanceDepuisIrradiance(hInclWhM2, month, soiling) / 1000.0;
}

// Facteur de performance simulé (pertes réelles par rapport à la référence :
// poussière, échauffement, ombrages, câblage…). Il varie en continu dans
// [PERF_MIN ; PERF_MAX] autour de PERF_MOYENNE, pour que la « performance
// instantanée » affichée par l'application reste entre 75 % et 95 % (marge de
// 1 point pour l'arrondi et le léger écart entre les séries météo).
constexpr double PERF_MIN = 0.76;
constexpr double PERF_MAX = 0.94;
constexpr double PERF_MOYENNE = 0.85;

// tSec : temps en secondes ; alea : nombre aléatoire dans [-1 ; 1].
inline double facteurPerformance(double tSec, double alea) {
  const double DEUX_PI = 2.0 * PI_;
  double f = PERF_MOYENNE
           + 0.060 * std::sin(DEUX_PI * tSec / 97.0)          // dérive lente (~1,5 min)
           + 0.025 * std::sin(DEUX_PI * tSec / 23.0 + 1.0)    // variation moyenne
           + 0.010 * std::sin(tSec * 3.7)                     // variation rapide
           + 0.005 * (alea < -1.0 ? -1.0 : (alea > 1.0 ? 1.0 : alea));   // bruit de mesure
  if (f < PERF_MIN) f = PERF_MIN;
  if (f > PERF_MAX) f = PERF_MAX;
  return f;
}

inline double temperatureCellule(double tAir, double gIncl) {
  return tAir + K_ECHAUFFEMENT * (gIncl > 0.0 ? gIncl : 0.0);
}

// Tension d'une chaîne au point de puissance max (V) : baisse avec la
// température des cellules et (faiblement) en lumière faible ; 0 la nuit.
inline double tensionChaine(double gIncl, double tCellule) {
  if (gIncl < 5.0) return 0.0;
  const double g = gIncl < 20.0 ? 20.0 : (gIncl > 1200.0 ? 1200.0 : gIncl);
  return MODULES_PAR_CHAINE * VMP_STC_V
       * (1.0 + COEF_TENSION * (tCellule - 25.0))
       * (1.0 + 0.03 * std::log(g / 1000.0));
}

// Courant d'UNE chaîne (A) : puissance DC totale répartie sur les NB_CHAINES
// chaînes identiques, divisée par la tension de chaîne ; 0 la nuit. C'est la
// grandeur du registre 3022 de l'onduleur réel (courant de l'entrée PV 1),
// envoyée dans le champ pv_i, comme pv_v est la tension de l'entrée PV 1.
inline double courantChaine(double pDcW, double vChaine) {
  if (vChaine <= 0.0 || pDcW <= 0.0) return 0.0;
  return pDcW / NB_CHAINES / vChaine;
}

// ---- Deux chaînes (entrées PV 1 et PV 2 de l'onduleur) ----
// Les deux chaînes sont identiques (9 modules JA Solar, même orientation) : la
// chaîne 2 suit le calcul de la chaîne 1, avec un désappariement normal et
// STABLE — tension × (1 + e_v), courant × (1 + e_i), e_v et e_i tirés une fois
// au démarrage dans [−1 % ; +1 %] — plus son propre bruit de mesure de
// tension (le même que la chaîne 1, ±0,5 V). Défaut simulé
// (SIM_DEFAUT_CHAINE2 = 1) : la chaîne 2 est coupée, son courant est nul et sa
// tension est la tension à vide (≈ 1,21 × V_mpp pour les modules JA Solar
// JAM66D45-600/LB : V_oc / V_mpp = 47,7 / 39,44).
constexpr double ECART_CHAINE2_MAX = 0.01;
constexpr double RAPPORT_VOC_VMP = 1.21;

struct MesuresChaines {
  double v1, i1;   // entrée PV 1 (V, A)
  double v2, i2;   // entrée PV 2 (V, A)
  double p1() const { return v1 * i1; }
  double p2() const { return v2 * i2; }
  double puissanceTotale() const { return p1() + p2(); }
};

// Écart de désappariement borné à ±ECART_CHAINE2_MAX (fraction : 0,01 = 1 %).
inline double borneEcart(double e) {
  return e < -ECART_CHAINE2_MAX ? -ECART_CHAINE2_MAX : (e > ECART_CHAINE2_MAX ? ECART_CHAINE2_MAX : e);
}

// pDcSainW : puissance DC des deux chaînes saines ; vChaine : tension d'une
// chaîne (bruit de mesure compris) ; eV, eI : désappariement de la chaîne 2
// (fractions, tirées une fois au démarrage, bornées à ±1 %) ; bruitV2 : bruit
// de mesure de la tension de la chaîne 2 (V), ignoré la nuit.
inline MesuresChaines deuxChaines(double pDcSainW, double vChaine, double eV, double eI,
                                  double bruitV2, bool defautChaine2) {
  MesuresChaines m;
  m.v1 = vChaine > 0.0 ? vChaine : 0.0;
  m.i1 = courantChaine(pDcSainW, m.v1);
  if (defautChaine2) {
    m.v2 = m.v1 * RAPPORT_VOC_VMP;
    m.i2 = 0.0;
  } else {
    m.v2 = m.v1 > 0.0 ? m.v1 * (1.0 + borneEcart(eV)) + bruitV2 : 0.0;
    if (m.v2 < 0.0) m.v2 = 0.0;
    m.i2 = m.i1 * (1.0 + borneEcart(eI));
  }
  return m;
}

// Écart relatif (%) entre les puissances des deux chaînes : |P1 − P2| / max(P1, P2).
// Même formule que l'application (mobile/src/chaines.ts).
inline double ecartChainesPct(double p1, double p2) {
  const double pmax = p1 > p2 ? p1 : p2;
  if (pmax <= 0.0) return 0.0;
  return std::fabs(p1 - p2) / pmax * 100.0;
}

// Température de l'onduleur (°C) : air ambiant + échauffement selon la charge.
inline double temperatureOnduleur(double tAir, double pW) {
  return tAir + 5.0 + 20.0 * (pW > 0.0 ? pW : 0.0) / P_ONDULEUR_W;
}

// Séries Open-Meteo « minutely_15 » (timezone=GMT, forecast_days=1) :
// v[i] = moyenne sur [15·i − 15 ; 15·i] minutes après 00:00 UTC.

// Valeur instantanée à `minutes` après 00:00 UTC : interpolation linéaire entre
// les milieux d'intervalles (15·i − 7,5 min), pour une courbe sans marches.
inline double serieInstantanee(const float* v, int n, double minutes) {
  if (n <= 0) return 0.0;
  const double k = (minutes + 7.5) / 15.0;
  if (k <= 0.0) return v[0];
  const int i0 = (int)k;
  if (i0 >= n - 1) return v[n - 1];
  const double t = k - i0;
  return v[i0] * (1.0 - t) + v[i0 + 1] * t;
}

// Irradiation cumulée (Wh/m²) de 00:00 UTC jusqu'à `minutes`.
inline double serieIntegraleWhM2(const float* v, int n, double minutes) {
  double total = 0.0;
  for (int i = 1; i < n; i++) {
    const double debut = 15.0 * (i - 1), fin = 15.0 * i;
    if (minutes <= debut) break;
    const double duree = (minutes < fin ? minutes : fin) - debut;   // minutes
    total += v[i] * duree / 60.0;
  }
  return total;
}

// Énergie produite depuis le lever (kWh) à l'heure donnée = intégrale exacte
// de powerW. Ne dépend que de l'heure : insensible aux redémarrages.
inline double energySinceSunriseKwh(double hourOfDay, double soiling, double peakW) {
  const double s = soiling < 0.0 ? 0.0 : (soiling > 1.0 ? 1.0 : soiling);
  double x = (hourOfDay - LEVER) / (COUCHER - LEVER);
  if (x <= 0.0) return 0.0;
  if (x > 1.0) x = 1.0;
  const double integrale = (COUCHER - LEVER) * (x / 2.0 - std::sin(2.0 * PI_ * x) / (4.0 * PI_));
  return peakW / 1000.0 * (1.0 - s) * integrale;
}

}  // namespace solar
