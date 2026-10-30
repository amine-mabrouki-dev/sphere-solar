/**
 * Carte « Mesuré vs Référence (PVsyst) ».
 *
 * Compare la production mesurée à la production de référence issue de la
 * simulation PVsyst, détecte une perte lente de performance (encrassement) et
 * un éventuel nettoyage. Données fournies par GET /inverters/{id}/performance.
 *
 * Props :
 *   - inverterId : onduleur à comparer
 *   - apiUrl, token : optionnels — si fournis, appel direct ; sinon on réutilise
 *     le helper `api` de l'application (URL serveur + jeton SecureStore).
 *   - days, mode : fenêtre et mode de référence (auto | irradiance | mensuel).
 *
 * Composants de base React Native uniquement (View, Text), aucune dépendance.
 */
import { useFocusEffect } from 'expo-router';
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { api } from '@/src/api';
import { C } from '@/src/colors';
import {
  estExclu, etatAffiche, libelleDetailJour, libelleDisponibilite, libellePastilleAujourdhui,
  libellePerduArret, mentionEtat, noteReference, texteR, dernierJourValide,
} from '@/src/etatJour';
import type { Performance, PerfState } from '@/src/types';

interface Props {
  inverterId: number | null;
  apiUrl?: string;
  token?: string;
  days?: number;
  mode?: 'auto' | 'irradiance' | 'mensuel';
}

// Couleurs et libellés d'état
const COULEUR: Record<PerfState, string> = {
  normal: C.green,
  vigilance: C.primary,   // orange (charte)
  anomalie: C.red,
  incoherent: C.muted,    // gris : ni normal ni anomalie
  incomplete: C.muted,    // gris : acquisition interrompue
  fonctionnement_insuffisant: C.muted,   // gris : moins de 3 h de fonctionnement
};
const LIBELLE: Record<PerfState, string> = {
  normal: 'Normal',
  vigilance: 'Vigilance',
  anomalie: 'Alerte',
  incoherent: 'À vérifier',
  incomplete: 'Incomplet',
  fonctionnement_insuffisant: 'Peu de marche',
};

// Barres d'un jour exclu de l'analyse (incohérent, incomplet, fonctionnement insuffisant)
const GRIS_CLAIR = C.muted + '55';

// Formatage des dates : 'YYYY-MM-DD' → '13/10/2026' (texte) ou '13/10' (histogramme)
const fmtDate = (iso: string) => {
  const [a, m, j] = iso.split('-');
  return `${j}/${m}/${a}`;
};
const fmtJour = (iso: string) => {
  const [, m, j] = iso.split('-');
  return `${j}/${m}`;
};

function PerformanceReferenceCard({
  inverterId,
  apiUrl,
  token,
  days = 14,
  mode = 'auto',
}: Props) {
  const [perf, setPerf] = useState<Performance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Rafraîchissement : à chaque ouverture de l'écran et toutes les 10 minutes,
  // pour que la journée apparaisse d'elle-même après le coucher du soleil.
  const [rafraichir, setRafraichir] = useState(0);
  useFocusEffect(useCallback(() => { setRafraichir((n) => n + 1); }, []));
  useEffect(() => {
    const h = setInterval(() => setRafraichir((n) => n + 1), 10 * 60_000);
    return () => clearInterval(h);
  }, []);
  const dejaCharge = useRef(false);

  useEffect(() => {
    if (inverterId == null) return;
    let actif = true;
    // Indicateur de chargement seulement au premier affichage (pas de clignotement)
    if (!dejaCharge.current) setLoading(true);

    // Si apiUrl + token sont fournis, appel direct ; sinon helper `api` existant.
    const charger = async (): Promise<Performance> => {
      if (apiUrl && token) {
        const res = await fetch(
          `${apiUrl}/inverters/${inverterId}/performance?days=${days}&mode=${mode}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok) throw new Error(`${res.status}`);
        return res.json();
      }
      return api.performance(inverterId, days, mode);
    };

    charger()
      .then((p) => { if (actif) { setPerf(p); setError(''); dejaCharge.current = true; } })
      .catch((e: any) => {
        if (!actif || dejaCharge.current) return;   // rafraîchissement raté : on garde l'affichage
        setError(String(e?.message || '').includes('422')
          ? 'Pas encore de journée complète enregistrée pour comparer.'
          : 'Comparaison indisponible pour le moment.');
      })
      .finally(() => { if (actif) setLoading(false); });

    return () => { actif = false; };
  }, [inverterId, apiUrl, token, days, mode, rafraichir]);

  if (loading) {
    return <View style={[s.card, s.centre]}><ActivityIndicator color={C.primary} /></View>;
  }
  if (error || !perf) {
    return <View style={[s.card, s.centre]}><Text style={s.muted}>{error || 'Aucune donnée.'}</Text></View>;
  }

  // r > 1,10 → toujours « À vérifier », jamais « Normal » (voir src/etatJour.ts) ;
  // jours incohérents et incomplets : gris, avec leur mention, exclus de l'analyse
  const jours = perf.jours.map((d) => ({ ...d, etat: etatAffiche(d) }));
  // Grand pourcentage : DERNIER JOUR VALIDE (normal, vigilance, anomalie), jamais un
  // jour exclu. Badge : règle d'alerte (jours valides) puis état de ce jour.
  const valide = dernierJourValide(jours);
  const rPct = valide ? Math.round(valide.r * 100) : null;
  const etat: PerfState | null = perf.alerte_performance ? 'anomalie' : (valide?.etat ?? null);
  // Un saut vers une valeur incohérente n'est jamais un nettoyage (garde-fou si
  // le backend interrogé est antérieur à cette règle)
  const nettoyageValide = perf.nettoyage_detecte != null
    && !estExclu(jours.find((d) => d.date === perf.nettoyage_detecte)?.etat ?? 'normal');
  const aDesExclus = jours.some((d) => estExclu(d.etat));
  const pastille = libellePastilleAujourdhui(perf.aujourdhui);
  // Mode majoritaire sur la période (pour le libellé de référence en pied de carte)
  const nbIrr = jours.filter((d) => d.mode === 'irradiance').length;
  const modeRef = nbIrr > jours.length / 2
    ? 'PVsyst et irradiation du jour (Open-Meteo)'
    : 'moyenne mensuelle PVsyst';

  // On affiche au plus les 10 derniers jours pour rester lisible sur mobile.
  const visibles = jours.slice(-10);
  const maxE = Math.max(1, ...visibles.map((d) => Math.max(d.energie_attendue_kwh, d.energie_mesuree_kwh)));

  return (
    <View style={s.card}>
      {/* En-tête : pourcentage du dernier jour + badge d'état */}
      <View style={s.enTete}>
        <View style={{ flex: 1 }}>
          <Text style={s.pct}>{rPct != null ? `${rPct} %` : '—'}</Text>
          <Text style={s.pctSub}>
            {valide
              ? `de la production attendue — dernier jour valide : ${
                valide.jour_courant ? "aujourd'hui" : fmtJour(valide.date)}`
              : 'Pas encore de journée valide'}
          </Text>
          {/* r calculé sur les seules heures de fonctionnement (arrêt ou mesures manquantes) */}
          {valide?.methode === 'horaire' && <Text style={s.pctSub}>(sur les heures de fonctionnement)</Text>}
        </View>
        {/* Pas de badge tant qu'aucun jour n'est valide */}
        {etat != null && (
          <View style={[s.badge, { borderColor: COULEUR[etat], backgroundColor: COULEUR[etat] + '22' }]}>
            <View style={[s.badgeDot, { backgroundColor: COULEUR[etat] }]} />
            <Text style={[s.badgeTxt, { color: COULEUR[etat] }]}>{LIBELLE[etat]}</Text>
          </View>
        )}
      </View>

      {/* Étiquette « données simulées » (disparaît avec des données réelles) */}
      {perf.donnees_demonstration && (
        <View style={s.demoTag}>
          <Text style={s.demoTagTxt}>Scénario de démonstration — données simulées</Text>
        </View>
      )}

      {/* Message du serveur, tiré de la règle d'alerte sur les jours valides */}
      <Text style={s.message}>{perf.message_jours_valides ?? perf.message}</Text>
      {nettoyageValide && (
        <Text style={s.nettoyage}>🧹 Nettoyage détecté le {fmtDate(perf.nettoyage_detecte!)}</Text>
      )}

      {/* Histogramme jour par jour : attendue (gris) vs mesurée (orange) */}
      <View style={s.graphe}>
        {visibles.map((d, i) => {
          const hAtt = (d.energie_attendue_kwh / maxE) * 90;
          const hMes = (d.energie_mesuree_kwh / maxE) * 90;
          return (
            <View key={i} style={s.colonne}>
              <View style={s.barres}>
                <View style={[s.barre, { height: Math.max(hAtt, 3), backgroundColor: estExclu(d.etat) ? GRIS_CLAIR : C.ref }]} />
                <View style={[s.barre, {
                  height: Math.max(hMes, 3),
                  backgroundColor: estExclu(d.etat) ? GRIS_CLAIR : C.primary,
                }]} />
              </View>
              {/* valeur de r sous chaque jour, colorée selon l'état ; « — » pour un jour exclu */}
              <Text style={[s.rTxt, { color: COULEUR[d.etat] }]}>{texteR(d, 'pourcent')}</Text>
              {/* Disponibilité : heures de fonctionnement / heures de soleil utile ;
                  rien si elle est inconnue. Colonne étroite : retour à la ligne. */}
              {libelleDisponibilite(d) != null && (
                <Text style={s.dispoTxt} numberOfLines={3}>{libelleDisponibilite(d)}</Text>
              )}
              <Text style={s.jourTxt}>
                {visibles.length <= 10 || i % 2 === 0 ? (d.jour_courant ? 'Auj.' : fmtJour(d.date)) : ''}
              </Text>
            </View>
          );
        })}
      </View>

      {/* Légende */}
      <View style={s.legende}>
        <View style={s.legItem}><View style={[s.swatch, { backgroundColor: C.primary }]} /><Text style={s.legTxt}>Mesurée</Text></View>
        <View style={s.legItem}><View style={[s.swatch, { backgroundColor: C.ref }]} /><Text style={s.legTxt}>Attendue</Text></View>
      </View>
      {/* Journée en cours (pas encore comparée, pas de barre) : ligne à part */}
      {pastille != null && (
        <View style={s.pastilleEnCours}><Text style={s.pastilleEnCoursTxt}>{pastille}</Text></View>
      )}

      {/* Récap des 3 derniers jours complets (pour la lecture du jury) */}
      <Text style={s.recapTitre}>3 derniers jours complets</Text>
      <View style={s.recap}>
        {[...jours].slice(-3).reverse().map((d) => (
          <View key={d.date} style={s.recapLigne}>
            <View style={s.recapRow}>
              <Text style={s.recapDate}>{d.jour_courant ? "Aujourd'hui" : fmtJour(d.date)}</Text>
              <Text style={s.recapKwh}>
                {d.energie_mesuree_kwh.toFixed(1).replace('.', ',')} / {d.energie_attendue_kwh.toFixed(1).replace('.', ',')} kWh
              </Text>
              <Text style={[s.recapR, { color: COULEUR[d.etat] }]}>r = {texteR(d, 'ratio')}</Text>
            </View>
            {libelleDetailJour(d) != null && <Text style={s.recapDetail}>{libelleDetailJour(d)}</Text>}
            {libellePerduArret(d) != null && <Text style={s.recapDetail}>{libellePerduArret(d)}</Text>}
            {mentionEtat(d.etat) != null && <Text style={s.recapMention}>{mentionEtat(d.etat)}</Text>}
          </View>
        ))}
      </View>

      {/* Mode de référence + seuil + perte estimée */}
      <Text style={s.pied}>{noteReference(perf.mode, modeRef)}</Text>
      <Text style={s.pied}>
        Seuil 90 % pendant 3 jours
        {perf.perte_estimee_kwh > 0 ? ` · perte estimée ${perf.perte_estimee_kwh.toFixed(1).replace('.', ',')} kWh` : ''}
        {aDesExclus ? ' (jours grisés exclus)' : ''}
        {(perf.energie_perdue_arret_kwh ?? 0) > 0
          ? ` · perdu à l'arrêt ${perf.energie_perdue_arret_kwh!.toFixed(1).replace('.', ',')} kWh`
          : ''}
      </Text>
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    backgroundColor: C.surface,
    borderRadius: 14,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: C.border,
  },
  centre: { paddingVertical: 28, alignItems: 'center' },
  muted: { color: C.muted, fontSize: 13, textAlign: 'center' },

  enTete: { flexDirection: 'row', alignItems: 'flex-start' },
  pct: { color: C.text, fontSize: 34, fontWeight: '800' },
  pctSub: { color: C.muted, fontSize: 12, marginTop: -2 },

  demoTag: { alignSelf: 'flex-start', backgroundColor: C.primary + '26', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, marginTop: 8 },
  demoTagTxt: { color: C.primary, fontSize: 11, fontWeight: '600' },

  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5,
  },
  badgeDot: { width: 7, height: 7, borderRadius: 4 },
  badgeTxt: { fontSize: 11, fontWeight: '700' },

  message: { color: C.text, fontSize: 13, marginTop: 12, lineHeight: 18 },
  nettoyage: { color: C.green, fontSize: 12, fontWeight: '600', marginTop: 6 },

  graphe: {
    flexDirection: 'row', justifyContent: 'space-around', alignItems: 'flex-end',
    marginTop: 16,
  },
  colonne: { flex: 1, alignItems: 'center' },
  barres: { flexDirection: 'row', alignItems: 'flex-end', height: 95, gap: 2 },
  barre: { width: 6, borderRadius: 3 },
  rTxt: { fontSize: 10, fontWeight: '700', marginTop: 5 },
  dispoTxt: { color: C.muted, fontSize: 7, lineHeight: 9, marginTop: 1, textAlign: 'center' },
  jourTxt: { color: C.muted, fontSize: 8, marginTop: 2 },

  legende: { flexDirection: 'row', alignItems: 'center', gap: 16, marginTop: 12 },
  // Pastille sur sa propre ligne, sous la légende ; le texte peut passer à la ligne
  pastilleEnCours: {
    alignSelf: 'flex-start', maxWidth: '100%', marginTop: 8,
    borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: C.muted + '22', borderWidth: 1, borderColor: C.muted + '55',
  },
  pastilleEnCoursTxt: { color: C.muted, fontSize: 10, fontWeight: '600' },
  legItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  swatch: { width: 12, height: 12, borderRadius: 3 },
  legTxt: { color: C.muted, fontSize: 11 },

  pied: { color: C.muted, fontSize: 11, marginTop: 10, fontStyle: 'italic' },

  recapTitre: { color: C.muted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginTop: 14, marginBottom: 6, textTransform: 'uppercase' },
  recap: { borderTopWidth: 1, borderTopColor: C.border },
  recapLigne: { paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: C.border },
  recapRow: { flexDirection: 'row', alignItems: 'center' },
  recapMention: { color: C.muted, fontSize: 11, fontStyle: 'italic', marginTop: 2, marginLeft: 48 },
  recapDetail: { color: C.muted, fontSize: 11, marginTop: 2, marginLeft: 54 },
  recapDate: { color: C.text, fontSize: 12, fontWeight: '700', minWidth: 48, marginRight: 6 },
  recapKwh: { color: C.muted, fontSize: 12, flex: 1 },
  recapR: { fontSize: 12, fontWeight: '800' },
});

export default memo(PerformanceReferenceCard);
