/**
 * Onglet Rapports.
 * Puces Mensuel / Annuel + sélecteur de mois ou d'année.
 * Synthèse depuis le serveur, sur la période comparable (jours complets passés,
 * jours valides) : énergie produite, énergie attendue des mêmes jours,
 * performance, CO₂ évité, alarmes onduleur et alertes de performance. Mois et
 * années futurs désactivés, période en cours marquée « en cours ». Bouton de
 * génération PDF (expo-print + expo-sharing) et rapports générés pendant la session.
 * La réponse du serveur est vérifiée (lireSynthese) : un format inattendu
 * affiche « Synthèse indisponible pour cette période », jamais un plantage.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import * as Sharing from 'expo-sharing';
import { api } from '@/src/api';
import { C } from '@/src/colors';
import { useSite } from '@/src/site';
import DashboardSection from '@/app/components/DashboardSection';
import { generateComprehensiveReport } from '@/src/reportGenerator';
import {
  aucuneDonnee, entierFr, etatMois, lireSynthese, mentionReferencePvsyst, MESSAGE_AUCUNE_DONNEE,
  MESSAGE_INDISPONIBLE, MOIS_LONG, niveauPerformance, nombreFr, performancePct, sousTitrePeriode,
  type SyntheseRapport,
} from '@/src/rapport';

type Periode = 'month' | 'year';

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
// Couleur de la carte « Performance » (seuils habituels de la comparaison)
const COULEUR_NIVEAU = { normal: C.green, vigilance: C.yellow, anomalie: C.red } as const;

// Rapports générés pendant la session (persistants tant que l'app tourne)
interface RapportGenere { id: string; titre: string; sousTitre: string; uri: string; }
const rapportsSession: RapportGenere[] = [];

export default function RapportsScreen() {
  const { instId } = useSite();
  const now = new Date();

  const [periode, setPeriode] = useState<Periode>('month');
  const [mois, setMois] = useState(now.getMonth() + 1);     // 1..12
  const [annee, setAnnee] = useState(now.getFullYear());

  const [data, setData] = useState<SyntheseRapport | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [erreur, setErreur] = useState('');                 // synthèse
  const [erreurPdf, setErreurPdf] = useState('');           // génération du PDF
  const requete = useRef(0);                                 // ignore les réponses dépassées
  const [, forcer] = useState(0);                           // re-render après génération

  const charger = useCallback(async () => {
    const id = ++requete.current;
    setLoading(true);
    setErreur('');
    setData(null);
    let d: SyntheseRapport | null = null;
    try {
      d = lireSynthese(await api.reportData(instId, periode, annee, periode === 'month' ? mois : undefined));
    } catch {
      d = null;
    }
    // Une période choisie entre-temps a sa propre requête : on ignore celle-ci
    if (id !== requete.current) return;
    setData(d);
    if (!d) setErreur(MESSAGE_INDISPONIBLE);
    setLoading(false);
  }, [instId, periode, mois, annee]);

  useEffect(() => { charger(); }, [charger]);

  const generer = async () => {
    setGenerating(true);
    setErreurPdf('');
    try {
      const uri = await generateComprehensiveReport(instId, periode, annee, periode === 'month' ? mois : undefined);
      const titre = periode === 'month' ? `${MOIS_LONG[mois - 1]} ${annee}` : `Année ${annee}`;
      rapportsSession.unshift({
        id: `${Date.now()}`,
        titre,
        sousTitre: periode === 'month' ? 'Rapport mensuel · PDF' : 'Rapport annuel · PDF',
        uri,
      });
      forcer((n) => n + 1);
    } catch (e: any) {
      setErreurPdf(e?.message ?? 'Échec de la génération du rapport.');
    } finally {
      setGenerating(false);
    }
  };

  const partager = async (uri: string) => {
    try {
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri, { mimeType: 'application/pdf' });
    } catch { /* ignore */ }
  };

  const titrePeriode = periode === 'month' ? `${MOIS_LONG[mois - 1]} ${annee}` : `Année ${annee}`;
  const niveau = niveauPerformance(data?.performance);

  return (
    <ScrollView style={s.scroll} contentContainerStyle={s.content}>
      {/* Puces de type + sélecteur */}
      <View style={s.chipsRow}>
        {([['month', 'Mensuel'], ['year', 'Annuel']] as const).map(([cle, lib]) => {
          const actif = cle === periode;
          return (
            <TouchableOpacity key={cle} onPress={() => setPeriode(cle)} activeOpacity={0.8}
              style={[s.chip, actif && s.chipActive]}>
              <Text style={[s.chipText, actif && s.chipTextActive]}>{lib}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Sélecteur de mois ou d'année */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.selectorRow}>
        {periode === 'month'
          ? MOIS.map((libelle, i) => {
              const actif = i + 1 === mois;
              const etat = etatMois(annee, i + 1, now);
              return (
                <TouchableOpacity key={libelle} onPress={() => setMois(i + 1)} activeOpacity={0.8}
                  disabled={etat === 'futur'}
                  style={[s.selChip, actif && s.selChipActive, etat === 'futur' && s.selChipFutur]}>
                  <Text style={[s.selText, actif && s.selTextActive]}>
                    {libelle}{etat === 'en_cours' ? ' · en cours' : ''}
                  </Text>
                </TouchableOpacity>
              );
            })
          : [now.getFullYear() - 2, now.getFullYear() - 1, now.getFullYear()].map((y) => {
              const actif = y === annee;
              return (
                <TouchableOpacity key={y} onPress={() => setAnnee(y)} activeOpacity={0.8}
                  style={[s.selChip, actif && s.selChipActive]}>
                  <Text style={[s.selText, actif && s.selTextActive]}>
                    {y}{y === now.getFullYear() ? ' · en cours' : ''}
                  </Text>
                </TouchableOpacity>
              );
            })}
      </ScrollView>

      {/* Synthèse */}
      <DashboardSection
        title={periode === 'month' ? 'Synthèse du mois' : "Synthèse de l'année"}
        subtitle={(data && sousTitrePeriode(data)) || titrePeriode}
      >
        {erreur ? (
          <View style={s.msgCard}><Text style={s.muted}>{erreur}</Text></View>
        ) : loading || !data ? (
          <View style={s.center}><ActivityIndicator color={C.primary} /></View>
        ) : aucuneDonnee(data) ? (
          <View style={s.msgCard}><Text style={s.muted}>{MESSAGE_AUCUNE_DONNEE}</Text></View>
        ) : (
          <View style={s.grid}>
            <KpiCard label="Énergie produite" value={nombreFr(data.energie_produite_kwh)} unit="kWh" />
            <KpiCard label="Énergie attendue (même période)" value={nombreFr(data.energie_attendue_kwh)} unit="kWh"
              note={mentionReferencePvsyst(data)} />
            <KpiCard label="Performance" value={performancePct(data.performance)} unit=""
              couleur={niveau ? COULEUR_NIVEAU[niveau] : undefined} />
            <KpiCard label="CO₂ évité" value={nombreFr(data.co2_evite_kg, 0)} unit="kg" />
            <KpiCard label="Alarmes onduleur" value={entierFr(data.alarmes_onduleur)} unit="" />
            <KpiCard label="Alertes de performance" value={entierFr(data.alertes_performance)} unit="" />
          </View>
        )}
      </DashboardSection>

      {/* Génération PDF */}
      <View style={s.gutter}>
        <TouchableOpacity style={s.genBtn} onPress={generer} disabled={generating || loading || !data} activeOpacity={0.85}>
          {generating
            ? <ActivityIndicator color="#1A1A1A" />
            : <Text style={s.genBtnTxt}>Générer le rapport PDF</Text>}
        </TouchableOpacity>
        {erreurPdf ? <Text style={[s.muted, { marginTop: 8 }]}>{erreurPdf}</Text> : null}
      </View>

      {/* Rapports précédents (session) */}
      <DashboardSection title="Rapports précédents" subtitle="Générés pendant cette session">
        {rapportsSession.length === 0 ? (
          <View style={s.msgCard}><Text style={s.muted}>Aucun rapport généré pour le moment.</Text></View>
        ) : (
          <View style={s.card}>
            {rapportsSession.map((r) => (
              <View key={r.id} style={s.repRow}>
                <View style={{ flex: 1 }}>
                  <Text style={s.repTitle}>{r.titre}</Text>
                  <Text style={s.repSub}>{r.sousTitre}</Text>
                </View>
                <TouchableOpacity style={s.repBtn} onPress={() => partager(r.uri)} activeOpacity={0.85}>
                  <Text style={s.repBtnTxt}>Voir</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.repBtn} onPress={() => partager(r.uri)} activeOpacity={0.85}>
                  <Text style={s.repBtnTxt}>Partager</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
      </DashboardSection>

      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

export function ErrorBoundary({ retry }: { error: Error; retry: () => Promise<void> }) {
  return (
    <View style={[s.scroll, s.content]}>
      <View style={[s.msgCard, { marginTop: 20 }]}>
        <Text style={s.muted}>{MESSAGE_INDISPONIBLE}</Text>
        <TouchableOpacity style={[s.repBtn, { marginTop: 14, alignSelf: 'center' }]} onPress={retry} activeOpacity={0.85}>
          <Text style={s.repBtnTxt}>Réessayer</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function KpiCard({ label, value, unit, note, couleur }: {
  label: string; value: string; unit: string; note?: string; couleur?: string;
}) {
  return (
    <View style={s.kpiCard}>
      <Text style={s.kpiLabel}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
        <Text style={[s.kpiValue, couleur ? { color: couleur } : null]}>{value}</Text>
        {unit ? <Text style={s.kpiUnit}>{unit}</Text> : null}
      </View>
      {note ? <Text style={s.kpiNote}>{note}</Text> : null}
    </View>
  );
}

const s = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: C.bg },
  content: { paddingBottom: 40, paddingTop: 10 },
  center: { paddingVertical: 30, alignItems: 'center' },
  gutter: { paddingHorizontal: 14, marginTop: 14 },
  muted: { color: C.muted, fontSize: 13, textAlign: 'center' },

  chipsRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 14, marginBottom: 10 },
  chip: { height: 28, borderRadius: 14, paddingHorizontal: 16, justifyContent: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.border },
  chipActive: { backgroundColor: C.primary, borderColor: C.primary },
  chipText: { color: C.text, fontSize: 12, fontWeight: '600' },
  chipTextActive: { color: '#1A1A1A', fontWeight: '800' },

  selectorRow: { gap: 8, paddingHorizontal: 14, paddingBottom: 4 },
  selChip: { height: 28, borderRadius: 14, paddingHorizontal: 12, justifyContent: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.border },
  selChipActive: { backgroundColor: C.border, borderColor: C.primary },
  selText: { color: C.muted, fontSize: 12, fontWeight: '600' },
  selTextActive: { color: C.text, fontWeight: '800' },
  selChipFutur: { opacity: 0.35 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 14, gap: 10 },
  kpiCard: { flexBasis: '47.5%', flexGrow: 1, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },
  kpiLabel: { color: C.muted, fontSize: 11, marginBottom: 6 },
  kpiValue: { color: C.text, fontSize: 22, fontWeight: '800' },
  kpiUnit: { color: C.muted, fontSize: 12 },
  kpiNote: { color: C.muted, fontSize: 10, marginTop: 6 },

  msgCard: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 18 },

  genBtn: { backgroundColor: C.primary, borderRadius: 12, height: 48, alignItems: 'center', justifyContent: 'center' },
  genBtnTxt: { color: '#1A1A1A', fontSize: 15, fontWeight: '800' },

  card: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 6 },
  repRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: C.border },
  repTitle: { color: C.text, fontSize: 14, fontWeight: '700' },
  repSub: { color: C.muted, fontSize: 11, marginTop: 2 },
  repBtn: { borderWidth: 1, borderColor: C.primary, borderRadius: 8, paddingHorizontal: 12, height: 32, alignItems: 'center', justifyContent: 'center' },
  repBtnTxt: { color: C.primary, fontSize: 12, fontWeight: '700' },
});
