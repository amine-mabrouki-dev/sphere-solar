/**
 * Comparaison des deux chaînes PV.
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  chaine2Mesuree, comparaisonChaines, ecartChaines, niveauEcart, MESSAGE_DEFAUT_CHAINE,
} from '../chaines';

const SAINE = { pv_v: 370, pv_i: 10.8, pv2_v: 368, pv2_i: 10.85 };

test('chaînes saines au soleil : écart ≈ 0 %, vert, sans message', () => {
  const pct = ecartChaines(SAINE)!;
  assert.ok(pct < 1);
  assert.deepEqual(comparaisonChaines(SAINE, 700), {
    texte: `Écart entre chaînes : ${Math.round(pct)} %`, niveau: 'faible', alerte: null,
  });
});

test('seuils de couleur : < 5 % vert, 5 à 15 % orange, > 15 % rouge', () => {
  assert.equal(niveauEcart(4.9), 'faible');
  assert.equal(niveauEcart(5), 'moyen');
  assert.equal(niveauEcart(15), 'moyen');
  assert.equal(niveauEcart(15.1), 'fort');
  assert.equal(comparaisonChaines({ ...SAINE, pv2_i: 10.8 * 0.9 }, 500)?.niveau, 'moyen');
});

test('chaîne 2 coupée (SIM_DEFAUT_CHAINE2 = 1) : courant nul, écart > 15 %, défaut probable', () => {
  const coupee = { pv_v: 370, pv_i: 10.8, pv2_v: 440.3, pv2_i: 0 };
  assert.equal(ecartChaines(coupee), 100);
  assert.deepEqual(comparaisonChaines(coupee, 650), {
    texte: 'Écart entre chaînes : 100 %', niveau: 'fort', alerte: MESSAGE_DEFAUT_CHAINE,
  });
});

test('écart de 20 % au soleil : rouge et défaut probable', () => {
  const c = comparaisonChaines({ pv_v: 370, pv_i: 10, pv2_v: 370, pv2_i: 8 }, 300);
  assert.equal(c?.texte, 'Écart entre chaînes : 20 %');
  assert.equal(c?.alerte, MESSAGE_DEFAUT_CHAINE);
});

test('ligne masquée sous 200 W/m², irradiance inconnue, ou la nuit', () => {
  const coupee = { pv_v: 370, pv_i: 10.8, pv2_v: 440.3, pv2_i: 0 };
  assert.equal(comparaisonChaines(coupee, 199), null);
  assert.equal(comparaisonChaines(coupee, null), null);
  assert.notEqual(comparaisonChaines(coupee, 200), null);          // 200 W/m² : affichée
  assert.equal(comparaisonChaines({ pv_v: 0, pv_i: 0, pv2_v: 0, pv2_i: 0 }, 500), null);
});

test('ancien firmware (pv2_v / pv2_i absents) : chaîne 2 masquée, pas de ligne, aucun message', () => {
  assert.equal(chaine2Mesuree({ pv_v: 370, pv_i: 10 }), false);
  assert.equal(chaine2Mesuree({ pv_v: 370, pv_i: 10, pv2_v: 368, pv2_i: null }), false);
  assert.equal(chaine2Mesuree(SAINE), true);
  assert.equal(chaine2Mesuree(null), false);
  assert.equal(comparaisonChaines({ pv_v: 370, pv_i: 10 }, 700), null);
  assert.equal(ecartChaines(null), null);
});
