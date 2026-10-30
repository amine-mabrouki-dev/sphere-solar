/**
 * Onglet Rapports et rapport PDF : format de la synthèse, période comparable,
 * libellés, seuils, robustesse aux champs absents.
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  aucuneDonnee, entierFr, etatMois, lireSynthese, mentionReferencePvsyst, niveauPerformance, nombreFr,
  performancePct, sousTitrePeriode, type SyntheseRapport,
} from '../rapport';
import { htmlRapport } from '../rapportHtml';

const OCTOBRE: SyntheseRapport = {
  installation: { id: 3, name: 'Client', location: 'Metlaoui' },
  inverters: [{ id: 3, serial: 'SOLIS-01', model: 'Solis S5-GR3P12K' }],
  periode: {
    type: 'month', annee: 2026, mois: 10, debut: '2026-10-01', fin: '2026-10-19',
    libelle: 'Du 1er au 19 octobre 2026', jours_comparables: 19, en_cours: true, future: false,
  },
  nb_jours_valides: 17, nb_jours_exclus: 2, nb_jours_sans_donnees: 0,
  energie_produite_kwh: 782.9, energie_attendue_kwh: 949.4, performance: 0.825,
  reference_pvsyst_mois_kwh: 1618, co2_evite_kg: 391.4,
  alarmes_onduleur: 0, alertes_performance: 2, jours_en_alerte_performance: 7,
  economies_dt: 195.72, arbres_equivalents: 19,
  summary: { max_power_w: 9053.3, avg_temp_c: 39.6 },
  inverter_metrics: [{ id: 3, serial: 'SOLIS-01', model: null, energie_produite_kwh: 782.9,
    max_power_w: 9053.3, alertes_performance: 2, alerts: [] }],
  daily_production: [
    { date: '2026-10-16', onduleur: 'SOLIS-01', etat: 'anomalie', valide: true, r: 0.883,
      energie_mesuree_kwh: 52.19, energie_attendue_kwh: 59.08, methode: 'journaliere' },
    { date: '2026-10-17', onduleur: 'SOLIS-01', etat: 'incoherent', valide: false, r: 7.828,
      energie_mesuree_kwh: 17.7, energie_attendue_kwh: 2.26, methode: 'horaire' },
  ],
};

const AOUT_SANS_DONNEES: SyntheseRapport = {
  ...OCTOBRE,
  periode: { ...OCTOBRE.periode, mois: 8, debut: '2026-08-01', fin: '2026-08-31',
    libelle: 'Du 1er au 31 août 2026', jours_comparables: 31, en_cours: false },
  nb_jours_valides: 0, nb_jours_exclus: 0, nb_jours_sans_donnees: 31,
  energie_produite_kwh: 0, energie_attendue_kwh: 0, performance: null, co2_evite_kg: 0,
  alertes_performance: 0, jours_en_alerte_performance: 0, daily_production: [],
};

// Réponse d'un serveur antérieur (cause de « Cannot read property 'debut' of undefined »)
const ANCIEN_FORMAT = {
  installation: { id: 3 }, inverters: [],
  period: { type: 'month', year: 2026, month: 10, start_date: '2026-10-01T00:00:00', end_date: '2026-10-31T23:59:59' },
  summary: { total_energy_kwh: 923.8 }, kpis: { reference_kwh: 1618 }, inverter_metrics: [], daily_production: [],
};

test('lireSynthese : accepte le format du serveur, refuse les autres sans planter', () => {
  assert.equal(lireSynthese(OCTOBRE), OCTOBRE);
  assert.equal(lireSynthese(ANCIEN_FORMAT), null);
  assert.equal(lireSynthese(null), null);
  assert.equal(lireSynthese('texte'), null);
  assert.equal(lireSynthese({ periode: '2026-10' }), null);
  assert.equal(lireSynthese({ periode: { debut: '01/10/2026', fin: '2026-10-19', libelle: 'x' } }), null);
  assert.equal(lireSynthese({ periode: { debut: '2026-10-01', fin: '2026-10-19' } }), null);   // sans libellé
});

test('sous-titre de la période comparable', () => {
  assert.equal(sousTitrePeriode(OCTOBRE), 'Du 1er au 19 octobre 2026 — 17 jours valides, 2 exclus');
  assert.equal(sousTitrePeriode({ ...OCTOBRE, nb_jours_valides: 1, nb_jours_exclus: 0 }),
    'Du 1er au 19 octobre 2026 — 1 jour valide, aucun exclu');
  assert.equal(sousTitrePeriode(AOUT_SANS_DONNEES), 'Du 1er au 31 août 2026');
});

test('sous-titre : chaîne vide si la période ou ses champs sont absents', () => {
  assert.equal(sousTitrePeriode(undefined), '');
  assert.equal(sousTitrePeriode(null), '');
  assert.equal(sousTitrePeriode({}), '');
  assert.equal(sousTitrePeriode(ANCIEN_FORMAT as never), '');
  assert.equal(sousTitrePeriode({ periode: { debut: '2026-10-01' } }), '');
  assert.equal(sousTitrePeriode({ periode: OCTOBRE.periode }), 'Du 1er au 19 octobre 2026');
});

test('nombres absents → « — »', () => {
  assert.equal(nombreFr(undefined), '—');
  assert.equal(nombreFr(null), '—');
  assert.equal(nombreFr(Number.NaN), '—');
  assert.equal(nombreFr('12' as unknown), '—');
  assert.equal(entierFr(undefined), '—');
  assert.equal(entierFr(3), '3');
  assert.equal(performancePct(undefined), '—');
  assert.equal(niveauPerformance(undefined), null);
  assert.equal(mentionReferencePvsyst({}), 'Référence PVsyst du mois entier : — kWh');
});

test('mois sans données', () => {
  assert.equal(aucuneDonnee(AOUT_SANS_DONNEES), true);
  assert.equal(aucuneDonnee({ nb_jours_valides: 0, nb_jours_exclus: 2 }), false);
  assert.equal(aucuneDonnee(OCTOBRE), false);
  assert.equal(aucuneDonnee({}), true);
});

test('nombres, performance et référence PVsyst du mois entier', () => {
  assert.equal(nombreFr(1618, 0), '1 618');
  assert.equal(nombreFr(949.44), '949,4');
  assert.equal(performancePct(0.825), '83 %');
  assert.equal(mentionReferencePvsyst(OCTOBRE), 'Référence PVsyst du mois entier : 1 618 kWh');
  assert.equal(mentionReferencePvsyst({ ...OCTOBRE, periode: { ...OCTOBRE.periode, type: 'year' } }),
    "Référence PVsyst de l'année entière : 1 618 kWh");
});

test('couleur de la performance selon les seuils habituels', () => {
  assert.equal(niveauPerformance(0.96), 'normal');
  assert.equal(niveauPerformance(0.95), 'normal');
  assert.equal(niveauPerformance(0.92), 'vigilance');
  assert.equal(niveauPerformance(0.89), 'anomalie');
  assert.equal(niveauPerformance(null), null);
});

test('mois passés, en cours et futurs', () => {
  const auj = new Date(2026, 9, 19);
  assert.equal(etatMois(2026, 9, auj), 'passe');
  assert.equal(etatMois(2026, 10, auj), 'en_cours');
  assert.equal(etatMois(2026, 11, auj), 'futur');
  assert.equal(etatMois(2025, 12, auj), 'passe');
});

test('rapport PDF : mêmes chiffres et libellés, ligne des jours exclus', () => {
  // \s couvre aussi l'espace insécable : « 1 618 » devient « 1 618 » après normalisation
  const texte = htmlRapport(OCTOBRE, 'month', 2026, 10).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
  for (const attendu of [
    'Du 1er au 19 octobre 2026 — 17 jours valides, 2 exclus',
    'Énergie produite 782,9 kWh',
    'Énergie attendue (même période) 949,4 kWh Référence PVsyst du mois entier : 1 618 kWh',
    'Performance 83 %',
    'CO₂ évité 391 kg (0,50 kg/kWh)',
    'Alarmes onduleur 0',
    'Alertes de performance 2',
    'Jours exclus : 2 (données incomplètes ou à vérifier)',
    '17/10/2026 À vérifier (exclu)',
  ]) assert.ok(texte.includes(attendu), `absent du PDF : ${attendu}`);
  assert.ok(!texte.includes('tous les 3-6 mois'));
});

test('rapport PDF : mois sans données et champs absents, sans exception', () => {
  const texte = htmlRapport(AOUT_SANS_DONNEES, 'month', 2026, 8).replace(/<[^>]+>/g, ' ');
  assert.ok(texte.includes('Aucune journée complète sur la période'));
  const partiel = { periode: OCTOBRE.periode } as unknown as SyntheseRapport;
  assert.doesNotThrow(() => htmlRapport(partiel, 'month', 2026, 10));
});
