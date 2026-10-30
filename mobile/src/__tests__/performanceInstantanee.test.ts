/**
 * Tests de la performance instantanée (runner intégré de Node, sans dépendance).
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  G_MIN_W_M2,
  etatPerformance,
  performanceInstantanee,
  puissanceAttendueInclineeW,
  puissanceAttendueW,
} from '../performanceInstantanee';
import { P_CRETE_W, facteurInclinaison, prReference } from '../pvsyst';

const OCTOBRE = 10;

test('P_att = 10 800 × G/1000 × GlobInc/GlobHor × PR (octobre, G = 800)', () => {
  // 10 800 × 0,8 × (170,2 / 131,2) × 0,880 ≈ 9 863 W
  const attendu = 10_800 * 0.8 * (170.2 / 131.2) * 0.88;
  assert.ok(Math.abs(puissanceAttendueW(800, OCTOBRE) - attendu) < 1e-6);
  assert.ok(Math.abs(puissanceAttendueW(800, OCTOBRE) - 9863) < 1);
  assert.equal(P_CRETE_W, 10_800);
  assert.equal(prReference(OCTOBRE), 0.88);
  assert.ok(Math.abs(facteurInclinaison(OCTOBRE) - 170.2 / 131.2) < 1e-12);
});

test('performance = pv_p / P_att, en %, arrondie à l’unité', () => {
  const pAtt = puissanceAttendueW(800, OCTOBRE);
  assert.deepEqual(performanceInstantanee(pAtt * 0.954, 800, OCTOBRE), { pct: 95, etat: 'normal' });
  assert.deepEqual(performanceInstantanee(pAtt, 800, OCTOBRE), { pct: 100, etat: 'normal' });
});

test('« — » si G < 100 W/m² ou données manquantes', () => {
  assert.equal(G_MIN_W_M2, 100);
  assert.deepEqual(performanceInstantanee(500, 99.9, OCTOBRE), { pct: null, etat: 'indisponible', motif: 'lumiere_faible' });
  assert.deepEqual(performanceInstantanee(500, 0, OCTOBRE), { pct: null, etat: 'indisponible', motif: 'lumiere_faible' });
  assert.deepEqual(performanceInstantanee(null, 800, OCTOBRE), { pct: null, etat: 'indisponible', motif: 'donnees' });
  assert.deepEqual(performanceInstantanee(500, undefined, OCTOBRE), { pct: null, etat: 'indisponible', motif: 'donnees' });
  // À 100 W/m² pile, la valeur est calculée
  assert.notEqual(performanceInstantanee(1_000, 100, OCTOBRE).pct, null);
});

test('seuils de couleur : vert 90–110, orange 80–90, rouge < 80, gris > 110', () => {
  assert.equal(etatPerformance(110), 'normal');
  assert.equal(etatPerformance(100), 'normal');
  assert.equal(etatPerformance(90), 'normal');
  assert.equal(etatPerformance(89), 'vigilance');
  assert.equal(etatPerformance(80), 'vigilance');
  assert.equal(etatPerformance(79), 'anomalie');
  assert.equal(etatPerformance(0), 'anomalie');
  assert.equal(etatPerformance(111), 'incoherent');
});

test('irradiance inclinée disponible : P_att = 10 800 × G_incl/1000 × PR', () => {
  // 10 800 × 0,7319 × 0,880 ≈ 6 956 W (valeurs Open-Meteo du 18/10 à 12:30)
  assert.ok(Math.abs(puissanceAttendueInclineeW(731.9, OCTOBRE) - 10_800 * 0.7319 * 0.88) < 1e-6);
  const pAtt = puissanceAttendueInclineeW(731.9, OCTOBRE);
  assert.deepEqual(performanceInstantanee(pAtt * 0.98, 614, OCTOBRE, 731.9), { pct: 98, etat: 'normal' });
});

test('fin d’après-midi : la référence inclinée évite un faux « à vérifier »', () => {
  // 18/10 à 16:00 : G = 265 W/m², G_incl = 358 W/m² (rapport 1,35 > moyenne mensuelle 1,30).
  // Installation saine : pv_p = P_crête × G_incl/1000 × PR.
  const pvP = 10_800 * 0.358 * 0.88;
  assert.deepEqual(performanceInstantanee(pvP, 265, OCTOBRE, 358), { pct: 100, etat: 'normal' });
  // Avec la seule formule mensuelle, la même mesure sortait au-dessus de 100 %
  assert.ok(performanceInstantanee(pvP, 265, OCTOBRE).pct! > 100);
});

test('repli sur la formule mensuelle si G_incl est absent ou nul', () => {
  const attendu = performanceInstantanee(5_000, 600, OCTOBRE);
  assert.deepEqual(performanceInstantanee(5_000, 600, OCTOBRE, null), attendu);
  assert.deepEqual(performanceInstantanee(5_000, 600, OCTOBRE, 0), attendu);
  assert.deepEqual(performanceInstantanee(5_000, 600, OCTOBRE, Number.NaN), attendu);
  // Le seuil de 100 W/m² porte toujours sur l'irradiance horizontale
  assert.deepEqual(performanceInstantanee(500, 80, OCTOBRE, 300), { pct: null, etat: 'indisponible', motif: 'lumiere_faible' });
});

test('le classement suit la valeur affichée (arrondie)', () => {
  const pAtt = puissanceAttendueW(600, OCTOBRE);
  // 89,6 % s'affiche « 90 » → vert ; 110,4 % s'affiche « 110 » → vert
  assert.deepEqual(performanceInstantanee(pAtt * 0.896, 600, OCTOBRE), { pct: 90, etat: 'normal' });
  assert.deepEqual(performanceInstantanee(pAtt * 1.104, 600, OCTOBRE), { pct: 110, etat: 'normal' });
  // 119 % (passage nuageux : G faible mais production encore élevée) → à vérifier
  assert.deepEqual(performanceInstantanee(pAtt * 1.19, 600, OCTOBRE), { pct: 119, etat: 'incoherent' });
});
