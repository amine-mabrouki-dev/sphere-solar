/**
 * Constantes de référence PVsyst (simulation V7.2.8, chapitre 2).
 * COPIE de backend/app/reference.py (P_CRETE_KWC et PVSYST_MENSUEL) :
 * le test backend tests/test_constantes_mobile.py échoue si elles divergent.
 */

/** Puissance crête de l'installation (W). */
export const P_CRETE_W = 10_800;

/** Bilans mensuels PVsyst, mois 1..12 : [GlobHor, GlobInc (kWh/m²), E_Grid (MWh), PR]. */
export const PVSYST_MENSUEL: Record<number, readonly [number, number, number, number]> = {
  1:  [86.9,  131.6, 1.318, 0.927],
  2:  [99.9,  134.4, 1.330, 0.917],
  3:  [146.3, 172.9, 1.677, 0.898],
  4:  [176.6, 188.0, 1.792, 0.883],
  5:  [203.7, 197.3, 1.863, 0.874],
  6:  [209.7, 195.2, 1.814, 0.860],
  7:  [221.4, 209.7, 1.913, 0.845],
  8:  [200.3, 204.9, 1.873, 0.847],
  9:  [160.8, 183.2, 1.708, 0.863],
  10: [131.2, 170.2, 1.618, 0.880],
  11: [97.2,  146.3, 1.432, 0.906],
  12: [81.0,  129.3, 1.293, 0.926],
};

/** Rapport GlobInc / GlobHor du mois (passage horizontal → plan des modules). */
export function facteurInclinaison(mois: number): number {
  const [globHor, globInc] = PVSYST_MENSUEL[mois];
  return globInc / globHor;
}

/** Performance ratio de référence du mois. */
export function prReference(mois: number): number {
  return PVSYST_MENSUEL[mois][3];
}
