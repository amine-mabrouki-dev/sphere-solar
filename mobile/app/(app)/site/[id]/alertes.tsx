/**
 * Onglet Alertes.
 * Puces Ouvertes (n) / Acquittées / Toutes.
 * - Carte « Performance » en tête si une alerte de performance est active.
 * - Alertes onduleur : Acquitter (POST dismiss) + Demander à l'assistant.
 * - Section des dernières alertes acquittées.
 */
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
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
import { dateHeureTunis } from '@/src/heure';
import { useSite } from '@/src/site';
import DashboardSection from '@/app/components/DashboardSection';
import type { Alert, Performance } from '@/src/types';

type Filtre = 'open' | 'ack' | 'all';

const frR = (v: number | null | undefined) => (v != null ? v.toFixed(2).replace('.', ',') : '—');

function dateHeure(tsSec: number): string {
  return dateHeureTunis(new Date(tsSec * 1000));
}

export default function AlertesScreen() {
  const { inverterId, openAlertsCount, perfAlert, refreshAlerts } = useSite();
  const [filtre, setFiltre] = useState<Filtre>('open');
  const [liste, setListe] = useState<Alert[]>([]);
  const [perf, setPerf] = useState<Performance | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  const charger = useCallback(async () => {
    if (inverterId == null) return;
    setLoading(true);
    try {
      const open = filtre === 'open' ? true : filtre === 'ack' ? false : undefined;
      setListe(await api.alerts(inverterId, open));
    } catch {
      setListe([]);
    } finally {
      setLoading(false);
    }
    try {
      setPerf(await api.performance(inverterId, 7, 'auto'));
    } catch {
      setPerf(null);   // 422 ou indisponible : pas de carte performance
    }
  }, [inverterId, filtre]);

  useEffect(() => { charger(); }, [charger]);

  const acquitter = async (id: number) => {
    if (inverterId == null) return;
    setBusyId(id);
    try {
      await api.dismissAlert(inverterId, id);
      await charger();
      refreshAlerts();            // met à jour la pastille de l'onglet
    } catch { /* ignore */ } finally {
      setBusyId(null);
    }
  };

  const demanderAssistant = (message: string) => {
    const question = `L'alerte "${message}" est active : que signifie-t-elle, quelles sont les causes probables et que dois-je faire ?`;
    router.push({ pathname: '/site/[id]/assistant', params: { id: inverterId ?? 0, ask: question } });
  };

  const ouvertes = liste.filter((a) => a.cleared_at == null);
  const acquittees = liste.filter((a) => a.cleared_at != null);
  const montrerOuvertes = filtre === 'open' || filtre === 'all';
  const montrerAcquittees = filtre === 'ack' || filtre === 'all';
  const rienAOuvert = montrerOuvertes && ouvertes.length === 0 && !(perf?.alerte_performance);

  const puces: { cle: Filtre; libelle: string }[] = [
    { cle: 'open', libelle: `Ouvertes (${openAlertsCount})` },
    { cle: 'ack', libelle: 'Acquittées' },
    { cle: 'all', libelle: 'Toutes' },
  ];

  return (
    <ScrollView style={s.scroll} contentContainerStyle={s.content}>
      {/* Puces */}
      <View style={s.chipsRow}>
        {puces.map((p) => {
          const actif = p.cle === filtre;
          return (
            <TouchableOpacity key={p.cle} onPress={() => setFiltre(p.cle)} activeOpacity={0.8}
              style={[s.chip, actif && s.chipActive]}>
              <Text style={[s.chipText, actif && s.chipTextActive]}>{p.libelle}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={C.primary} size="large" /></View>
      ) : (
        <>
          {/* Alertes ouvertes */}
          {montrerOuvertes && (
            <DashboardSection title="Alertes ouvertes" subtitle="Les plus récentes en premier" barColor={C.red}>
              {/* Carte performance (pas d'acquittement) */}
              {perf?.alerte_performance && (
                <View style={[s.alertCard, s.perfCard]}>
                  <View style={s.cardTop}>
                    <View style={[s.badge, { backgroundColor: C.red }]}>
                      <Text style={s.badgeTxt}>Performance</Text>
                    </View>
                    {perf.jours?.length ? (
                      <Text style={s.date}>{perf.jours[perf.jours.length - 1].date}</Text>
                    ) : null}
                  </View>
                  <Text style={s.title}>Perte lente de performance</Text>
                  <Text style={s.desc}>
                    r = {frR(perf.r_dernier_jour)} · sous le seuil depuis {perf.jours_sous_seuil} jour
                    {perf.jours_sous_seuil > 1 ? 's' : ''}.
                  </Text>
                  <Text style={s.hint}>
                    Disparaît quand la production revient au-dessus de 90 % de la référence.
                  </Text>
                </View>
              )}

              {/* Alertes onduleur */}
              {ouvertes.map((a) => {
                const titre = a.message || `Code ${a.code}`;
                return (
                  <View key={a.id} style={[s.alertCard, s.invCard]}>
                    <View style={s.cardTop}>
                      <View style={[s.badge, { backgroundColor: C.primary }]}>
                        <Text style={[s.badgeTxt, { color: '#1A1A1A' }]}>Onduleur · code {a.code}</Text>
                      </View>
                      <Text style={s.date}>{dateHeure(a.raised_at)}</Text>
                    </View>
                    <Text style={s.title}>{titre}</Text>
                    <View style={s.btnRow}>
                      <TouchableOpacity style={s.btnPrimary} onPress={() => acquitter(a.id)} disabled={busyId === a.id} activeOpacity={0.85}>
                        {busyId === a.id
                          ? <ActivityIndicator color="#1A1A1A" size="small" />
                          : <Text style={s.btnPrimaryTxt}>Acquitter</Text>}
                      </TouchableOpacity>
                      <TouchableOpacity style={s.btnSecondary} onPress={() => demanderAssistant(titre)} activeOpacity={0.85}>
                        <Text style={s.btnSecondaryTxt}>Demander à l'assistant</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })}

              {rienAOuvert && (
                <View style={s.okCard}><Text style={s.okText}>✓ Aucune alerte active</Text></View>
              )}
            </DashboardSection>
          )}

          {/* Dernières alertes acquittées */}
          {montrerAcquittees && (
            <DashboardSection title="Dernières alertes acquittées" subtitle="Historique" barColor={C.ref}>
              {acquittees.length === 0 ? (
                <View style={s.okCard}><Text style={s.mutedText}>Aucune alerte acquittée.</Text></View>
              ) : (
                <View style={s.card}>
                  {acquittees.map((a) => (
                    <View key={a.id} style={s.ackRow}>
                      <Text style={s.ackCheck}>✓</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={s.ackTitle}>{a.message || `Code ${a.code}`}</Text>
                        <Text style={s.ackDate}>Acquittée le {a.cleared_at ? dateHeure(a.cleared_at) : '—'}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </DashboardSection>
          )}
        </>
      )}

      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: C.bg },
  content: { paddingBottom: 40, paddingTop: 10 },
  center: { paddingVertical: 40, alignItems: 'center' },

  chipsRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 14, marginBottom: 6 },
  chip: { height: 28, borderRadius: 14, paddingHorizontal: 14, justifyContent: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.border },
  chipActive: { backgroundColor: C.primary, borderColor: C.primary },
  chipText: { color: C.text, fontSize: 12, fontWeight: '600' },
  chipTextActive: { color: '#1A1A1A', fontWeight: '800' },

  card: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 6 },

  alertCard: { marginHorizontal: 14, marginBottom: 10, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },
  perfCard: { borderColor: C.red, borderLeftWidth: 4 },
  invCard: { borderLeftWidth: 4, borderLeftColor: C.primary },

  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  badge: { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  badgeTxt: { color: '#fff', fontSize: 11, fontWeight: '800' },
  date: { color: C.muted, fontSize: 11 },
  title: { color: C.text, fontSize: 14, fontWeight: '700' },
  desc: { color: C.muted, fontSize: 13, marginTop: 6, lineHeight: 18 },
  hint: { color: C.muted, fontSize: 11, marginTop: 8, fontStyle: 'italic' },

  btnRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  btnPrimary: { backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 16, height: 38, alignItems: 'center', justifyContent: 'center' },
  btnPrimaryTxt: { color: '#1A1A1A', fontSize: 13, fontWeight: '800' },
  btnSecondary: { borderWidth: 1, borderColor: C.primary, borderRadius: 10, paddingHorizontal: 16, height: 38, alignItems: 'center', justifyContent: 'center' },
  btnSecondaryTxt: { color: C.primary, fontSize: 13, fontWeight: '700' },

  okCard: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 18, alignItems: 'center' },
  okText: { color: C.green, fontSize: 14, fontWeight: '700' },
  mutedText: { color: C.muted, fontSize: 13 },

  ackRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: C.border },
  ackCheck: { color: C.green, fontSize: 16, fontWeight: '800' },
  ackTitle: { color: C.muted, fontSize: 13 },
  ackDate: { color: C.muted, fontSize: 11, marginTop: 2, opacity: 0.8 },
});
