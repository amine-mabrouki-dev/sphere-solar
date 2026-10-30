/**
 * Tests de l'interpolation des séries Open-Meteo au pas de 15 min.
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { heuresVersEpochMs, valeurA, type Serie15 } from '../serie15';

const MIN = 60_000;

test('heures locales Open-Meteo → epoch (Africa/Tunis = UTC+1)', () => {
  const [t] = heuresVersEpochMs(['2026-10-18T12:15'], 3600);
  assert.equal(t, Date.UTC(2026, 9, 18, 11, 15));
});

// Rampe matinale : 0, 100, 200, 300 W/m² sur les quarts d'heure finissant à 8:00 … 8:45
const base = Date.UTC(2026, 9, 18, 8, 0);
const rampe: Serie15 = {
  finsMs: [0, 15, 30, 45].map((m) => base + m * MIN),
  valeurs: [0, 100, 200, 300],
};

test('au milieu d’un intervalle, on retrouve sa moyenne', () => {
  assert.equal(valeurA(rampe, base + 15 * MIN - 7.5 * MIN), 100);
  assert.equal(valeurA(rampe, base + 30 * MIN - 7.5 * MIN), 200);
});

test('entre deux milieux, interpolation linéaire (pas de retard d’un quart d’heure)', () => {
  // À 8:30 pile, la valeur « current » d'Open-Meteo vaudrait 200 (moyenne 8:15–8:30) ;
  // l'estimation à l'instant présent est 250.
  assert.equal(valeurA(rampe, base + 30 * MIN), 250);
});

test('bords et hors série', () => {
  assert.equal(valeurA(rampe, base - 7.5 * MIN), 0);                 // avant le 1er milieu → 1re valeur
  assert.equal(valeurA(rampe, base + 45 * MIN), 300);               // après le dernier milieu
  assert.equal(valeurA(rampe, base - 60 * MIN), null);              // hors série
  assert.equal(valeurA({ finsMs: [], valeurs: [] }, base), null);
});

test('valeurs nulles : on garde la voisine disponible', () => {
  const trouee: Serie15 = { finsMs: rampe.finsMs, valeurs: [0, null, 200, 300] };
  assert.equal(valeurA(trouee, base + 15 * MIN), 200);
});
