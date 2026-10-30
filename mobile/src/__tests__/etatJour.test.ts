/**
 * Garde-fou d'affichage : au-dessus de 110 %, jamais « normal ».
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  estExclu, etatAffiche, libelleDetailJour, libelleDisponibilite, libellePastilleAujourdhui,
  libellePerduArret, mentionEtat, noteReference, texteR, dernierJourValide, disponibiliteCalculable,
} from '../etatJour';

test('r = 1,19 renvoyé « normal » par un ancien backend → affiché « incoherent »', () => {
  assert.equal(etatAffiche({ r: 1.19, etat: 'normal' }), 'incoherent');
});

test('jusqu’à 1,10 inclus, l’état du backend est conservé', () => {
  assert.equal(etatAffiche({ r: 1.10, etat: 'normal' }), 'normal');
  assert.equal(etatAffiche({ r: 0.85, etat: 'anomalie' }), 'anomalie');
  assert.equal(etatAffiche({ r: 1.25, etat: 'incoherent' }), 'incoherent');
});

test('journée incomplète : conservée, grise et mentionnée, même avec r > 1,10', () => {
  assert.equal(etatAffiche({ r: 0.62, etat: 'incomplete' }), 'incomplete');
  assert.equal(etatAffiche({ r: 1.25, etat: 'incomplete' }), 'incomplete');
  assert.equal(estExclu('incomplete'), true);
  assert.equal(estExclu('anomalie'), false);
  assert.equal(mentionEtat('incomplete'), 'Données incomplètes (acquisition interrompue)');
  assert.equal(mentionEtat('normal'), null);
});

test('fonctionnement insuffisant : conservé, gris, mentionné', () => {
  assert.equal(etatAffiche({ r: 7.8, etat: 'fonctionnement_insuffisant' }), 'fonctionnement_insuffisant');
  assert.equal(estExclu('fonctionnement_insuffisant'), true);
  assert.equal(mentionEtat('fonctionnement_insuffisant'), 'Fonctionnement insuffisant (moins de 3 h au soleil)');
});

test('disponibilité, détail du jour et perte à l’arrêt (méthode combinée)', () => {
  const j = {
    r: 0.93, heures_fonctionnement: 6, heures_soleil_utile: 10, heures_arret: 4,
    disponibilite: 60, energie_perdue_arret_kwh: 21.43,
  };
  assert.equal(libelleDisponibilite(j), '6 h / 10 h de soleil');
  assert.equal(libelleDetailJour(j), 'Performance 93 % — Disponibilité 60 % (6 h sur 10 h de soleil)');
  assert.equal(libellePerduArret(j), "Perdu à l'arrêt : 21,4 kWh");
  // Perte de 0,5 kWh ou moins : pas de mention
  assert.equal(libellePerduArret({ ...j, energie_perdue_arret_kwh: 0.5 }), null);
  assert.equal(libellePerduArret({ ...j, energie_perdue_arret_kwh: 0.51 }), "Perdu à l'arrêt : 0,5 kWh");
  // Disponibilité inconnue (pas de données horaires) : rien sous r, performance seule
  const sans = { r: 1.02, heures_fonctionnement: null, heures_soleil_utile: null, disponibilite: null };
  assert.equal(libelleDisponibilite(sans), null);
  assert.equal(libelleDetailJour(sans), 'Performance 102 %');
  assert.equal(libelleDetailJour({ r: 1 }), 'Performance 100 %');
});

test('jours exclus : jamais de pourcentage, « — » et le motif', () => {
  for (const etat of ['fonctionnement_insuffisant', 'incoherent', 'incomplete'] as const) {
    assert.equal(texteR({ r: 0.72, etat }, 'pourcent'), '—');
    assert.equal(texteR({ r: 0.72, etat }, 'ratio'), '—');
    assert.equal(libelleDetailJour({ r: 0.72, etat, heures_fonctionnement: 2, heures_soleil_utile: 2, disponibilite: 100 }), null);
  }
  assert.equal(mentionEtat('fonctionnement_insuffisant')?.startsWith('Fonctionnement insuffisant'), true);
  assert.equal(mentionEtat('incoherent')?.startsWith('Valeur à vérifier'), true);
  assert.equal(mentionEtat('incomplete')?.startsWith('Données incomplètes'), true);
  // Jours valides : valeur affichée
  assert.equal(texteR({ r: 0.876, etat: 'anomalie' }, 'pourcent'), '88');
  assert.equal(texteR({ r: 0.876, etat: 'anomalie' }, 'ratio'), '0,88');
  assert.equal(libelleDetailJour({ r: 0.93, etat: 'normal' }), 'Performance 93 %');
});

test('grand pourcentage : dernier jour valide', () => {
  const jours = [
    { date: '2026-10-15', etat: 'normal' as const },
    { date: '2026-10-16', etat: 'anomalie' as const },
    { date: '2026-10-17', etat: 'incoherent' as const },
    { date: '2026-10-18', etat: 'fonctionnement_insuffisant' as const },
  ];
  assert.equal(dernierJourValide(jours)?.date, '2026-10-16');
  assert.equal(dernierJourValide(jours.slice(2)), null);
  assert.equal(dernierJourValide([]), null);
});

test('heures mesurées et disponibilité non calculable', () => {
  // 18/10 : 2 h en marche, 8 h sans mesures, 10 h de soleil au total
  const j = {
    r: 0.72, etat: 'normal' as const, heures_fonctionnement: 2, heures_soleil_utile: 2,
    heures_soleil_total: 10, heures_arret: 0, heures_donnees_manquantes: 8, disponibilite: 100,
  };
  assert.equal(libelleDisponibilite(j), '2 h mesurées sur 10 h de soleil');
  assert.equal(disponibiliteCalculable(j), false);
  assert.equal(libelleDetailJour(j), 'Performance 72 % — Disponibilité : non calculable (données incomplètes)');
  // 1 h sans mesure sur 10 (10 %) : disponibilité affichée
  const k = { ...j, heures_fonctionnement: 6, heures_soleil_utile: 9, heures_arret: 3,
              heures_donnees_manquantes: 1, disponibilite: 66.7 };
  assert.equal(disponibiliteCalculable(k), true);
  assert.equal(libelleDisponibilite(k), '6 h mesurées sur 10 h de soleil');
  assert.equal(libelleDetailJour(k), 'Performance 72 % — Disponibilité 67 % (6 h sur 9 h de soleil)');
  // 2 h sur 10 (20 %) : non calculable ; sans heures_soleil_total (backend antérieur) : déduit
  assert.equal(disponibiliteCalculable({ ...k, heures_donnees_manquantes: 2, heures_soleil_total: 10 }), false);
  assert.equal(libelleDisponibilite({ ...j, heures_soleil_total: undefined }), '2 h mesurées sur 10 h de soleil');
});

test('note du bas selon le mode', () => {
  assert.equal(noteReference('combinee'),
    "Référence : PVsyst et irradiation d'Open-Meteo — méthode journalière pour les journées "
    + "complètes, horaire en cas d'arrêt ou de mesures manquantes");
  assert.equal(noteReference('journaliere', 'moyenne mensuelle PVsyst'), 'Référence : moyenne mensuelle PVsyst');
});

test('pastille « Aujourd’hui » selon l’état de la journée', () => {
  assert.equal(
    libellePastilleAujourdhui({ energie_kwh: 22.21, termine: false, comparaison_a_partir_de: '18:45' }),
    'Aujourd\'hui : 22,2 kWh — comparaison à partir de 18:45',
  );
  assert.equal(
    libellePastilleAujourdhui({ energie_kwh: null, termine: false, comparaison_a_partir_de: '18:18' }),
    'Aujourd\'hui : comparaison à partir de 18:18',
  );
  assert.equal(libellePastilleAujourdhui({ energie_kwh: 50, termine: true, comparaison_a_partir_de: '18:18' }), null);
  assert.equal(libellePastilleAujourdhui(undefined), 'Aujourd\'hui : en cours');
});
