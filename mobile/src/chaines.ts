/**
 * Comparaison des deux chaînes PV (entrées PV 1 et PV 2 de l'onduleur).
 *
 *   écart (%) = |P1 − P2| / max(P1, P2) × 100,   avec P = tension × courant
 *
 * Même formule que le simulateur (include/solar_sim.h, ecartChainesPct).
 * La ligne d'écart n'est affichée que si les deux chaînes sont mesurées et que
 * l'irradiance atteint 200 W/m² : en lumière faible, les courants sont petits
 * et l'écart relatif n'a pas de sens. Couleur : vert sous 5 %, orange de 5 à
 * 15 %, rouge au-delà avec « Une seule chaîne en baisse : défaut de chaîne
 * probable » (connecteur, fusible, ombrage, module endommagé).
 *
 * Imports relatifs uniquement : module testable directement avec Node.
 */

export const SEUIL_ECART_VIGILANCE = 5;     // %
export const SEUIL_ECART_DEFAUT = 15;       // %
export const G_MIN_ECART = 200;             // W/m² : en dessous, ligne masquée
export const MESSAGE_DEFAUT_CHAINE = 'Une seule chaîne en baisse : défaut de chaîne probable';

export type NiveauEcart = 'faible' | 'moyen' | 'fort';

interface MesuresChaines {
  pv_v?: number | null;
  pv_i?: number | null;
  pv2_v?: number | null;
  pv2_i?: number | null;
}

/** true si l'entrée PV 2 est mesurée (pv2_v et pv2_i présents). Avec un ancien
 *  firmware, ils sont absents : le bloc « Chaîne 2 » est masqué. */
export function chaine2Mesuree(m: MesuresChaines | null | undefined): boolean {
  return m != null && m.pv2_v != null && m.pv2_i != null;
}

/** Écart relatif des puissances des deux chaînes (%), ou null si une mesure
 *  manque ou si aucune chaîne ne produit (nuit). */
export function ecartChaines(m: MesuresChaines | null | undefined): number | null {
  if (!m || m.pv_v == null || m.pv_i == null || m.pv2_v == null || m.pv2_i == null) return null;
  const p1 = Math.max(0, m.pv_v * m.pv_i);
  const p2 = Math.max(0, m.pv2_v * m.pv2_i);
  const pmax = Math.max(p1, p2);
  if (!(pmax > 0)) return null;
  return (Math.abs(p1 - p2) / pmax) * 100;
}

export function niveauEcart(pct: number): NiveauEcart {
  if (pct < SEUIL_ECART_VIGILANCE) return 'faible';
  if (pct <= SEUIL_ECART_DEFAUT) return 'moyen';
  return 'fort';
}

export interface ComparaisonChaines {
  texte: string;                  // « Écart entre chaînes : 1 % »
  niveau: NiveauEcart;
  alerte: string | null;          // défaut de chaîne probable (rouge), sinon null
}

/** Ligne d'écart affichée sous les deux chaînes, ou null si elle doit être
 *  masquée (chaîne 2 non mesurée, irradiance inconnue ou sous 200 W/m², nuit).
 *  @param g irradiance actuelle (W/m²) */
export function comparaisonChaines(m: MesuresChaines | null | undefined,
                                   g: number | null | undefined): ComparaisonChaines | null {
  if (!chaine2Mesuree(m) || g == null || !(g >= G_MIN_ECART)) return null;
  const pct = ecartChaines(m);
  if (pct == null) return null;
  const niveau = niveauEcart(pct);
  return {
    texte: `Écart entre chaînes : ${Math.round(pct)} %`,
    niveau,
    alerte: niveau === 'fort' ? MESSAGE_DEFAUT_CHAINE : null,
  };
}
