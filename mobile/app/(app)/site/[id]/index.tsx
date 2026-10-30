/**
 * Onglet Accueil — tableau de bord d'une installation.
 * Sections : Météo du site · Production instantanée · Production mesurée et
 * référence · Mesures électriques.
 * Les chiffres se rafraîchissent en temps réel (toutes les 0,5 s) sans recharger
 * l'écran. Virgule comme séparateur décimal.
 */
import { router } from 'expo-router';
import { memo, useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { api } from '@/src/api';
import { C } from '@/src/colors';
import { heureTunis, moisTunis } from '@/src/heure';
import { performanceInstantanee, type EtatPerfInstantanee } from '@/src/performanceInstantanee';
import { useSite } from '@/src/site';
import { describeWeather, irradianceA, useSiteWeather, type SiteWeather } from '@/src/weather';
import DashboardSection from '@/app/components/DashboardSection';
import InfoBouton from '@/app/components/InfoBouton';
import LiveReadings from '@/app/components/LiveReadings';
import PerformanceReferenceCard from '@/app/components/PerformanceReferenceCard';
import { chaine2Mesuree, comparaisonChaines, type NiveauEcart } from '@/src/chaines';
import { INFO_PRODUCTION_REFERENCE } from '@/src/explications';
import type { LatestMetrics } from '@/src/types';

// Explications des deux indicateurs (icône « i » → fenêtre en bas de l'écran)
type Explication = { titre: string; paragraphes: string[]; calcul: string };
const INFO_PERF_INSTANTANEE: Explication = {
  titre: 'Performance instantanée',
  paragraphes: [
    "Elle compare la puissance produite en ce moment à la puissance que l'installation devrait fournir avec le soleil actuel.",
    'Elle change toutes les quelques secondes. Un nuage peut la faire baisser un instant.',
    'Une installation saine reste autour de 100 %.',
  ],
  calcul: 'Puissance mesurée ÷ (10,8 kWc × irradiance × inclinaison × PR du mois)',
};

// Couleur de l'écart entre chaînes : vert < 5 %, orange 5 – 15 %, rouge au-delà
const COULEUR_ECART: Record<NiveauEcart, string> = {
  faible: C.green,
  moyen: C.primary,
  fort: C.red,
};

// Couleur de la performance instantanée selon son état
const COULEUR_PERF: Record<EtatPerfInstantanee, string> = {
  normal: C.green,
  vigilance: C.primary,
  anomalie: C.red,
  incoherent: C.muted,
  indisponible: C.text,
};

// Formatage avec virgule décimale (charte)
const fr1 = (v: number | null | undefined) => (v != null ? v.toFixed(1).replace('.', ',') : '—');
const fr0 = (v: number | null | undefined) => (v != null ? Math.round(v).toString() : '—');

export default function AccueilScreen() {
  const { instId, inverterId, loading: siteLoading } = useSite();
  const { weather } = useSiteWeather();

  const [m, setM] = useState<LatestMetrics | null>(null);
  const [live, setLive] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Rafraîchissement temps réel des mesures (0,5 s) sans recharger l'écran
  useEffect(() => {
    if (inverterId == null) return;
    let actif = true;
    let busy = false;
    const poll = async () => {
      if (busy || !actif) return;
      busy = true;
      try {
        const l = await api.latest(inverterId);
        if (actif) { setM(l); setLive(true); }
      } catch {
        if (actif) setLive(false);
      } finally {
        busy = false;
      }
    };
    poll();
    const h = setInterval(poll, 500);
    return () => { actif = false; clearInterval(h); };
  }, [inverterId]);

  const onRefresh = useCallback(async () => {
    if (inverterId == null) return;
    setRefreshing(true);
    try { setM(await api.latest(inverterId)); setLive(true); } catch { /* ignore */ }
    finally { setRefreshing(false); }
  }, [inverterId]);

  if (siteLoading || inverterId == null) {
    return (
      <View style={s.center}>
        <ActivityIndicator color={C.primary} size="large" />
      </View>
    );
  }

  // Onduleur « en ligne » si une mesure récente (< 5 min) est disponible
  const nowSec = Date.now() / 1000;
  const online = live && m?.ts != null && nowSec - m.ts < 300;

  // Performance instantanée = pv_p / P_att (PR PVsyst du mois, irradiance
  // Open-Meteo dans le plan des modules). « — » si G < 100 W/m² ;
  // voir src/performanceInstantanee.ts.
  // Irradiance estimée à l'instant présent (séries 15 min interpolées) : la valeur
  // « current » d'Open-Meteo a jusqu'à ~20 min de retard sur la mesure.
  const irrNow = irradianceA(weather);
  const perfInst = performanceInstantanee(m?.pv_p, irrNow.horizontale, moisTunis(), irrNow.inclinee);

  // Côté continu : une ligne par entrée PV de l'onduleur (pv_v / pv_i = entrée 1,
  // pv2_v / pv2_i = entrée 2), puis la comparaison des deux chaînes.
  const chaine1 = [
    { label: 'Tension', value: fr1(m?.pv_v), unit: 'V' },
    { label: 'Courant', value: fr1(m?.pv_i), unit: 'A' },
  ];
  const chaine2 = [
    { label: 'Tension', value: fr1(m?.pv2_v), unit: 'V' },
    { label: 'Courant', value: fr1(m?.pv2_i), unit: 'A' },
  ];
  // Chaîne 2 absente (ancien firmware) : bloc masqué, sans message
  const avecChaine2 = chaine2Mesuree(m);
  // Écart entre chaînes : seulement si les deux sont mesurées et G ≥ 200 W/m²
  const comparaison = comparaisonChaines(m, irrNow.horizontale);
  // Côté alternatif et température de l'onduleur : quatre tuiles de même largeur
  const alternatif = [
    { label: 'Tension AC', value: fr1(m?.ac_v), unit: 'V' },
    { label: 'Courant AC', value: fr1(m?.ac_i), unit: 'A' },
    { label: 'Fréquence', value: fr1(m?.freq), unit: 'Hz' },
    { label: 'Température', value: fr1(m?.temp), unit: '°C' },
  ];

  const prod: {
    value: string; unit: string; label: string; couleur?: string; note?: string; info?: Explication;
  }[] = [
    { value: fr0(m?.pv_p), unit: 'W', label: 'Puissance PV' },
    { value: fr1(m?.e_day), unit: 'kWh', label: "Aujourd'hui", note: 'en cours, depuis minuit' },
    {
      value: perfInst.pct != null ? String(perfInst.pct) : '—',
      unit: perfInst.etat === 'incoherent' ? '% · à vérifier' : '%',
      label: 'Performance instantanée',
      couleur: COULEUR_PERF[perfInst.etat],
      // Sous 100 W/m² : « — » et la raison, en petit
      note: perfInst.motif === 'lumiere_faible' ? 'lumière trop faible' : 'par rapport à la production attendue',
      info: INFO_PERF_INSTANTANEE,
    },
  ];

  return (
    <ScrollView
      style={s.scroll}
      contentContainerStyle={s.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />}
    >
      {/* 1. Météo du site */}
      <DashboardSection first title="Météo du site" subtitle="Metlaoui — Open-Meteo">
        <MeteoCard online={online} weather={weather} />
      </DashboardSection>

      {/* 2. Production instantanée */}
      <DashboardSection title="Production instantanée" subtitle="Mise à jour en temps réel">
        <View style={s.card}>
          <View style={s.liveRow}>
            <View style={[s.dot, online && s.dotLive]} />
            <Text style={[s.liveLabel, online && s.liveLabelOn]}>EN DIRECT</Text>
          </View>
          <View style={s.prodRow}>
            {prod.map((p, i) => (
              <View key={p.label} style={s.prodItemWrap}>
                {i > 0 && <View style={s.prodDivider} />}
                <View style={s.prodItem}>
                  <Text style={[s.prodValue, p.couleur != null && { color: p.couleur }]}>{p.value}</Text>
                  <Text style={s.prodUnit}>{p.unit}</Text>
                  <View style={s.prodLabelRow}>
                    <Text style={s.prodLabel}>{p.label}</Text>
                    {p.info && <InfoBouton {...p.info} />}
                  </View>
                  {p.note != null && <Text style={s.prodNote}>{p.note}</Text>}
                </View>
              </View>
            ))}
          </View>
        </View>
      </DashboardSection>

      {/* 3. Production mesurée et référence (appui → Historique) */}
      <DashboardSection
        title="Production mesurée et référence"
        subtitle="Comparaison avec la simulation PVsyst"
        titleAccessory={<InfoBouton {...INFO_PRODUCTION_REFERENCE} />}
      >
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => router.push({ pathname: '/site/[id]/historique', params: { id: instId } })}
        >
          <PerformanceReferenceCard inverterId={inverterId} days={7} mode="auto" />
        </TouchableOpacity>
      </DashboardSection>

      {/* 4. Mesures électriques */}
      <DashboardSection title="Mesures électriques" subtitle="Côté continu et côté alternatif">
        <Text style={s.ligneTitre}>Chaîne 1</Text>
        <LiveReadings tiles={chaine1} cols={2} />
        {avecChaine2 && (
          <>
            <Text style={s.ligneTitre}>Chaîne 2</Text>
            <LiveReadings tiles={chaine2} cols={2} />
          </>
        )}
        {/* Comparaison des deux chaînes (puissances pv_v × pv_i) */}
        {comparaison != null && (
          <View style={s.comparaison}>
            <Text style={[s.comparaisonTxt, { color: COULEUR_ECART[comparaison.niveau] }]}>
              {comparaison.texte}
            </Text>
            {comparaison.alerte != null && <Text style={s.comparaisonAlerte}>{comparaison.alerte}</Text>}
          </View>
        )}
        <Text style={s.ligneTitre}>Côté alternatif</Text>
        <LiveReadings tiles={alternatif} cols={4} />
      </DashboardSection>

      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

// Carte météo mémoïsée : horloge interne (30 s), ne se re-rend pas au tick 0,5 s
// Nom de l'installation volontairement absent (il contient le nom du client) :
// l'en-tête n'indique que l'état de l'onduleur et la ville du site.
const MeteoCard = memo(function MeteoCard({
  online, weather,
}: { online: boolean; weather: SiteWeather | null }) {
  const [heure, setHeure] = useState(() =>
    heureTunis());
  useEffect(() => {
    const h = setInterval(
      () => setHeure(heureTunis()),
      30_000,
    );
    return () => clearInterval(h);
  }, []);

  const metriques = [
    { v: weather ? `${Math.round(weather.temperature)} °C` : '—', l: 'Température' },
    { v: weather ? `${Math.round(weather.irradiance)} W/m²` : '—', l: 'Irradiance' },
    { v: weather ? `${Math.round(weather.windSpeed)} km/h` : '—', l: 'Vent' },
    { v: weather ? `${Math.round(weather.humidity)} %` : '—', l: 'Humidité' },
  ];

  return (
    <View style={s.weatherCard}>
      <View style={s.wTopRow}>
        <View style={s.wStatus}>
          <View style={[s.dot, online && s.dotLive]} />
          <Text style={[s.wStatusTxt, online && s.wStatusOn]} numberOfLines={1}>
            {online ? 'En ligne' : 'Hors ligne'} · Metlaoui
          </Text>
        </View>
        <Text style={s.wTime}>{heure}</Text>
      </View>
      <Text style={s.wDesc}>{weather ? describeWeather(weather.weatherCode, weather.isDay) : '—'}</Text>
      <View style={s.wMetrics}>
        {metriques.map((x) => (
          <View key={x.l} style={s.wMetric}>
            <Text style={s.wMetricVal}>{x.v}</Text>
            <Text style={s.wMetricLbl}>{x.l}</Text>
          </View>
        ))}
      </View>
    </View>
  );
});

const s = StyleSheet.create({
  // Mesures électriques : titre de chaque ligne de tuiles et comparaison des chaînes
  ligneTitre: { color: C.muted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase', marginHorizontal: 16, marginBottom: 6 },
  comparaison: { marginHorizontal: 16, marginTop: -6, marginBottom: 14 },
  comparaisonTxt: { fontSize: 13, fontWeight: '700' },
  comparaisonAlerte: { color: C.red, fontSize: 12, marginTop: 3 },
  scroll: { flex: 1, backgroundColor: C.bg },
  content: { paddingBottom: 40 },
  center: { flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' },
  gutter: { paddingHorizontal: 14 },

  // Carte météo (plate, 4 métriques)
  weatherCard: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 },
  wTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  wStatus: { flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 1 },
  wStatusTxt: { color: C.muted, fontSize: 12, fontWeight: '700' },
  wStatusOn: { color: C.green },
  wTime: { color: C.text, fontSize: 22, fontWeight: '800' },
  wDesc: { color: C.text, fontSize: 22, fontWeight: '800', marginTop: 10 },
  wMetrics: { flexDirection: 'row', marginTop: 16 },
  wMetric: { flex: 1, alignItems: 'flex-start' },
  wMetricVal: { color: C.text, fontSize: 16, fontWeight: '800' },
  wMetricLbl: { color: C.muted, fontSize: 10, marginTop: 3 },

  card: {
    marginHorizontal: 14,
    backgroundColor: C.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: C.border,
    padding: 16,
  },
  liveRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.ref },
  dotLive: { backgroundColor: C.green },
  liveLabel: { color: C.muted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  liveLabelOn: { color: C.green },

  prodRow: { flexDirection: 'row', alignItems: 'center' },
  prodItemWrap: { flex: 1, flexDirection: 'row', alignItems: 'center' },
  prodDivider: { width: 1, height: 42, backgroundColor: C.border },
  prodItem: { flex: 1, alignItems: 'center' },
  prodValue: { color: C.text, fontSize: 24, fontWeight: '800' },
  prodUnit: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2 },
  prodLabel: { flexShrink: 1, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.3, textAlign: 'center' },
  prodLabelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, marginTop: 4 },
  prodNote: { color: C.muted, fontSize: 9, marginTop: 2, textAlign: 'center' },

});
