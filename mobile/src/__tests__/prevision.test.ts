/**
 * Textes de la carte « Prévision de demain ».
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { detailPrevision, fourchettePrevision, valeurPrevision } from '../prevision';

const PREVISION = {
  prevision_kwh: 58.6, fourchette_min_kwh: 52.7, fourchette_max_kwh: 64.4,
  irradiation_prevue_kwh_m2: 5.4, performance_utilisee: 0.88, performance_mesuree: true,
};

test('prévision, fourchette et détail au format de la carte', () => {
  assert.equal(valeurPrevision(PREVISION), '≈ 58,6 kWh');
  assert.equal(fourchettePrevision(PREVISION), 'entre 53 et 64 kWh');
  assert.equal(detailPrevision(PREVISION), 'Soleil prévu : 5,4 kWh/m² · Performance récente : 88 %');
});

test('météo indisponible et performance non mesurée', () => {
  const p = { ...PREVISION, irradiation_prevue_kwh_m2: null, performance_mesuree: false, performance_utilisee: 1 };
  assert.equal(detailPrevision(p), 'Soleil prévu : indisponible · Performance récente : non mesurée');
});
