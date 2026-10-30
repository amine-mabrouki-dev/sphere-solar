/**
 * Onglet Historique — production mesurée vs référence PVsyst.
 * Puces de période (7/14/30 jours, Mois) → GET /performance?days=N&mode=mensuel.
 * Histogramme jour par jour, bilan de période, détail par jour, bandeau d'alerte.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { api } from '@/src/api';
import { C } from '@/src/colors';
import {
  estExclu, etatAffiche, libelleDetailJour, libelleDisponibilite, libellePastilleAujourdhui,
  libellePerduArret, mentionEtat, texteR,
} from '@/src/etatJour';
import { INFO_PRODUCTION_REFERENCE } from '@/src/explications';
import InfoBouton from '@/app/components/InfoBouton';
import { useSite } from '@/src/site';
import DashboardSection from '@/app/components/DashboardSection';
import type { Performance, PerfState } from '@/src/types';

const COULEUR: Record<PerfState, string> = {
  normal: C.green,
  vigilance: C.primary,
  anomalie: C.red,
  incoherent: C.muted,   // gris : valeur à vérifier
  incomplete: C.muted,   // gris : acquisition interrompue
  fonctionnement_insuffisant: C.muted,   // gris : moins de 3 h de fonctionnement
};
const LIBELLE: Record<PerfState, string> = {
  normal: 'Normal',
  vigilance: 'Vigilance',
  anomalie: 'Anomalie',
  incoherent: 'À vérifier',
  incomplete: 'Incomplet',
  fonctionnement_insuffisant: 'Peu de marche',
};

// Barres d'un jour exclu de l'analyse (incohérent, incomplet, fonctionnement insuffisant)
const GRIS_CLAIR = C.muted + '55';

const fr1 = (v: number | null | undefined) => (v != null ? v.toFixed(1).replace('.', ',') : '—');

type Periode = { cle: string; libelle: string; days: number };

function periodes(): Periode[] {
  const joursEcoules = new Date().getDate();   // jours écoulés du mois en cours
  return [
    { cle: '7', libelle: '7 jours', days: 7 },
    { cle: '14', libelle: '14 jours', days: 14 },
    { cle: '30', libelle: '30 jours', days: 30 },
    { cle: 'mois', libelle: 'Mois', days: Math.max(1, joursEcoules) },
  ];
}

export default function HistoriqueScreen() {
  const { inverterId } = useSite();
  const listePeriodes = useMemo(periodes, []);
  const [periode, setPeriode] = useState<Periode>(listePeriodes[1]);   // 14 jours par défaut
  const [perf, setPerf] = useState<Performance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (inverterId == null) return;
    let actif = true;
    setLoading(true);
    setError('');
    api.performance(inverterId, periode.days, 'auto')
      .then((p) => { if (actif) setPerf(p); })
      .catch((e: any) => {
        if (!actif) return;
        setPerf(null);
        setError(String(e?.message || '').includes('422')
          ? 'Pas encore de journée complète enregistrée.'
          : 'Comparaison indisponible pour le moment.');
      })
      .finally(() => { if (actif) setLoading(false); });
    return () => { actif = false; };
  }, [inverterId, periode]);

  // Puces de période
  const chips = (
    <View style={s.chipsRow}>
      {listePeriodes.map((p) => {
        const actif = p.cle === periode.cle;
        return (
          <TouchableOpacity key={p.cle} onPress={() => setPeriode(p)} activeOpacity={0.8}
            style={[s.chip, actif && s.chipActive]}>
            <Text style={[s.chipText, actif && s.chipTextActive]}>{p.libelle}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );

  // r > 1,10 → toujours « À vérifier », jamais « Normal » (voir src/etatJour.ts)
  const jours = (perf?.jours ?? []).map((d) => ({ ...d, etat: etatAffiche(d) }));
  const totalMes = jours.reduce((a, j) => a + j.energie_mesuree_kwh, 0);
  const totalAtt = jours.reduce((a, j) => a + j.energie_attendue_kwh, 0);
  const ecartPct = totalAtt > 0 ? ((totalMes - totalAtt) / totalAtt) * 100 : 0;
  const maxE = Math.max(1, ...jours.map((j) => Math.max(j.energie_attendue_kwh, j.energie_mesuree_kwh)));

  return (
    <ScrollView style={s.scroll} contentContainerStyle={s.content}>
      {chips}

      {/* Bandeau d'alerte de performance */}
      {perf?.alerte_performance && (
        <View style={s.banner}>
          <Text style={s.bannerText}>{perf.message}</Text>
        </View>
      )}

      {loading ? (
        <View style={s.center}><ActivityIndicator color={C.primary} size="large" /></View>
      ) : error ? (
        <View style={s.msgCard}><Text style={s.msg}>{error}</Text></View>
      ) : jours.length === 0 ? (
        <View style={s.msgCard}><Text style={s.msg}>Aucune donnée sur la période.</Text></View>
      ) : (
        <>
          {/* Histogramme */}
          <DashboardSection
            title="Production mesurée et attendue"
            subtitle="Jours complets · référence : simulation PVsyst"
            titleAccessory={<InfoBouton {...INFO_PRODUCTION_REFERENCE} />}
          >
            <View style={s.card}>
              <View style={s.chart}>
                {jours.map((j, i) => {
                  const hAtt = (j.energie_attendue_kwh / maxE) * 120;
                  const hMes = (j.energie_mesuree_kwh / maxE) * 120;
                  const montrerDate = jours.length <= 10 || i % 2 === 0;
                  return (
                    <View key={j.date} style={s.col}>
                      <View style={s.bars}>
                        <View style={[s.bar, { height: Math.max(hAtt, 2), backgroundColor: estExclu(j.etat) ? GRIS_CLAIR : C.ref }]} />
                        <View style={[s.bar, { height: Math.max(hMes, 2), backgroundColor: estExclu(j.etat) ? GRIS_CLAIR : C.primary }]} />
                      </View>
                      <Text style={s.colLabel}>{montrerDate ? (j.jour_courant ? 'Auj.' : j.date.slice(8)) : ''}</Text>
                    </View>
                  );
                })}
              </View>
              <View style={s.legend}>
                <View style={s.legItem}><View style={[s.sw, { backgroundColor: C.ref }]} /><Text style={s.legTxt}>Attendue</Text></View>
                <View style={s.legItem}><View style={[s.sw, { backgroundColor: C.primary }]} /><Text style={s.legTxt}>Mesurée</Text></View>
              </View>
              {/* La journée en cours n'est pas comparée (pas de barre) : ligne à part */}
              {libellePastilleAujourdhui(perf?.aujourdhui) != null && (
                <View style={s.pastilleEnCours}>
                  <Text style={s.pastilleEnCoursTxt}>{libellePastilleAujourdhui(perf?.aujourdhui)}</Text>
                </View>
              )}
            </View>
          </DashboardSection>

          {/* Bilan de la période */}
          <DashboardSection title="Bilan de la période" subtitle={`${jours.length} jour${jours.length > 1 ? 's' : ''} complet${jours.length > 1 ? 's' : ''}`}>
            <View style={s.grid}>
              <Bilan label="Énergie mesurée" value={fr1(totalMes)} unit="kWh" />
              <Bilan label="Énergie attendue" value={fr1(totalAtt)} unit="kWh" />
              <Bilan label="Écart" value={`${ecartPct >= 0 ? '+' : ''}${ecartPct.toFixed(1).replace('.', ',')}`} unit="%" rouge={ecartPct < 0} />
              <Bilan label="Perte estimée" value={fr1(perf?.perte_estimee_kwh)} unit="kWh" rouge={(perf?.perte_estimee_kwh ?? 0) > 0} />
            </View>
          </DashboardSection>

          {/* Détail par jour (plus récent en premier) */}
          <DashboardSection title="Détail par jour complet" subtitle="r = mesurée / attendue">
            <View style={s.card}>
              {[...jours].reverse().map((j) => (
                <View key={j.date} style={s.dayRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.dayDate}>{j.jour_courant ? "Aujourd'hui" : j.date}</Text>
                    <Text style={s.dayKwh}>{fr1(j.energie_mesuree_kwh)} / {fr1(j.energie_attendue_kwh)} kWh</Text>
                    {libelleDetailJour(j) != null && <Text style={s.dayKwh}>{libelleDetailJour(j)}</Text>}
                    {libellePerduArret(j) != null && <Text style={s.dayKwh}>{libellePerduArret(j)}</Text>}
                    {mentionEtat(j.etat) != null && <Text style={s.dayKwh}>{mentionEtat(j.etat)}</Text>}
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={[s.dayR, { color: COULEUR[j.etat] }]}>r = {texteR(j, 'ratio')}</Text>
                    {/* Disponibilité : heures de fonctionnement / heures de soleil */}
                    {libelleDisponibilite(j) != null && <Text style={s.dayDispo}>{libelleDisponibilite(j)}</Text>}
                  </View>
                  <View style={[s.badge, { borderColor: COULEUR[j.etat], backgroundColor: COULEUR[j.etat] + '22' }]}>
                    <Text style={[s.badgeTxt, { color: COULEUR[j.etat] }]}>{LIBELLE[j.etat]}</Text>
                  </View>
                </View>
              ))}
            </View>
          </DashboardSection>
        </>
      )}

      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

function Bilan({ label, value, unit, rouge }: { label: string; value: string; unit: string; rouge?: boolean }) {
  return (
    <View style={s.bilanCard}>
      <Text style={s.bilanLabel}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
        <Text style={[s.bilanValue, rouge && { color: C.red }]}>{value}</Text>
        <Text style={s.bilanUnit}>{unit}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: C.bg },
  content: { paddingBottom: 40, paddingTop: 10 },
  center: { paddingVertical: 40, alignItems: 'center' },

  chipsRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 14, marginBottom: 6, flexWrap: 'wrap' },
  chip: { height: 28, borderRadius: 14, paddingHorizontal: 14, justifyContent: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.border },
  chipActive: { backgroundColor: C.primary, borderColor: C.primary },
  chipText: { color: C.text, fontSize: 12, fontWeight: '600' },
  chipTextActive: { color: '#1A1A1A', fontWeight: '800' },

  banner: { marginHorizontal: 14, marginTop: 8, backgroundColor: C.red + '22', borderWidth: 1, borderColor: C.red, borderRadius: 10, padding: 12 },
  bannerText: { color: C.text, fontSize: 13, lineHeight: 18 },

  msgCard: { marginHorizontal: 14, marginTop: 12, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 20 },
  msg: { color: C.muted, fontSize: 14, textAlign: 'center' },

  card: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },

  chart: { flexDirection: 'row', alignItems: 'flex-end', height: 140 },
  col: { flex: 1, alignItems: 'center' },
  bars: { flexDirection: 'row', alignItems: 'flex-end', height: 122, gap: 1, justifyContent: 'center', width: '100%' },
  bar: { width: '38%', borderRadius: 2 },
  colLabel: { color: C.muted, fontSize: 8, marginTop: 4 },

  legend: { flexDirection: 'row', alignItems: 'center', gap: 16, marginTop: 10 },
  // Pastille sur sa propre ligne, sous la légende ; le texte peut passer à la ligne
  pastilleEnCours: {
    alignSelf: 'flex-start', maxWidth: '100%', marginTop: 8,
    borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: C.muted + '22', borderWidth: 1, borderColor: C.muted + '55',
  },
  pastilleEnCoursTxt: { color: C.muted, fontSize: 10, fontWeight: '600' },
  legItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  sw: { width: 12, height: 12, borderRadius: 3 },
  legTxt: { color: C.muted, fontSize: 11 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 14, gap: 10 },
  bilanCard: { flexBasis: '47.5%', flexGrow: 1, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },
  bilanLabel: { color: C.muted, fontSize: 11, marginBottom: 6 },
  bilanValue: { color: C.text, fontSize: 22, fontWeight: '800' },
  bilanUnit: { color: C.muted, fontSize: 12 },

  dayRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  dayDate: { color: C.text, fontSize: 13, fontWeight: '600' },
  dayKwh: { color: C.muted, fontSize: 12, marginTop: 2 },
  dayR: { fontSize: 13, fontWeight: '700' },
  dayDispo: { color: C.muted, fontSize: 10, marginTop: 2 },
  badge: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  badgeTxt: { fontSize: 10, fontWeight: '800' },
});
