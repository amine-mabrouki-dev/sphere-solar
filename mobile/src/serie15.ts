/**
 * Séries Open-Meteo « minutely_15 » : la valeur d'un pas daté t est la MOYENNE
 * sur [t − 15 min ; t]. La valeur « current » a donc 7 à 22 min de retard sur
 * l'instant présent, ce qui fausse la comparaison avec la puissance mesurée
 * quand l'ensoleillement varie vite (matin, fin de journée).
 *
 * On estime la valeur à l'instant voulu par interpolation linéaire entre les
 * milieux d'intervalles (t − 7,5 min) — même méthode que le simulateur ESP32
 * (include/solar_sim.h, serieInstantanee).
 *
 * Module pur, testable avec Node (src/__tests__).
 */

export interface Serie15 {
  finsMs: number[];          // fin de chaque intervalle (epoch ms), croissant
  valeurs: (number | null)[];
}

const DEMI_PAS_MS = 7.5 * 60_000;

/** Convertit les heures locales Open-Meteo (« 2026-10-18T12:15 ») en epoch ms. */
export function heuresVersEpochMs(heures: string[], decalageUtcS: number): number[] {
  return heures.map((h) => Date.parse(`${h}:00Z`) - decalageUtcS * 1000);
}

/** Valeur estimée à `instantMs`, ou null si l'instant sort de la série. */
export function valeurA(serie: Serie15, instantMs: number): number | null {
  const { finsMs, valeurs } = serie;
  const n = Math.min(finsMs.length, valeurs.length);
  if (n === 0) return null;
  const milieu = (i: number) => finsMs[i] - DEMI_PAS_MS;
  if (instantMs < milieu(0) - DEMI_PAS_MS || instantMs > milieu(n - 1) + DEMI_PAS_MS) return null;
  if (instantMs <= milieu(0)) return valeurs[0];
  if (instantMs >= milieu(n - 1)) return valeurs[n - 1];
  let i = 0;
  while (i < n - 2 && milieu(i + 1) <= instantMs) i++;
  const a = valeurs[i], b = valeurs[i + 1];
  if (a == null || b == null) return a ?? b ?? null;
  const t = (instantMs - milieu(i)) / (milieu(i + 1) - milieu(i));
  return a + (b - a) * t;
}
