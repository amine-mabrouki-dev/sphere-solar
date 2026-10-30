/**
 * Performance instantanée : puissance PV mesurée rapportée à la puissance
 * attendue pour l'ensoleillement du moment (PR de référence PVsyst du mois).
 *
 *   Référence principale (irradiance dans le plan des modules, Open-Meteo
 *   global_tilted_irradiance, 30° plein sud) :
 *     P_att = P_crête × (G_incl / 1000) × PR_ref du mois
 *
 *   Repli si G_incl est indisponible (irradiance horizontale G) :
 *     P_att = P_crête × (G / 1000) × (GlobInc / GlobHor du mois) × PR_ref du mois
 *
 *   performance = pv_p / P_att   (en %, arrondie à l'unité)
 *
 * Pourquoi G_incl en priorité : GlobInc / GlobHor est une moyenne MENSUELLE.
 * Heure par heure, le vrai rapport varie (≈ 1,21 à 1,35 un jour d'octobre),
 * ce qui affichait à tort ~81 % le matin et ~112 % en fin d'après-midi pour une
 * installation saine.
 *
 * Imports relatifs (pas d'alias « @/ ») : module testable directement avec Node.
 */
import { P_CRETE_W, facteurInclinaison, prReference } from './pvsyst';

/** Sous ce seuil d'irradiance horizontale (début / fin de journée), trop imprécis. */
export const G_MIN_W_M2 = 100;

export type EtatPerfInstantanee =
  | 'normal'        // 90 – 110 %  : vert
  | 'vigilance'     // 80 – 90 %   : orange
  | 'anomalie'      // < 80 %      : rouge
  | 'incoherent'    // > 110 %     : gris, « à vérifier »
  | 'indisponible'; // G < 100 W/m² ou données manquantes : « — »

export interface PerfInstantanee {
  pct: number | null;          // performance arrondie à l'unité, null si indisponible
  etat: EtatPerfInstantanee;
  // Pourquoi elle est indisponible : lumière trop faible (G < 100 W/m²) ou
  // données manquantes (mesure ou météo absente)
  motif?: 'lumiere_faible' | 'donnees';
}

/** Puissance attendue (W) à partir de l'irradiance horizontale G (formule de repli). */
export function puissanceAttendueW(g: number, mois: number): number {
  return P_CRETE_W * (g / 1000) * facteurInclinaison(mois) * prReference(mois);
}

/** Puissance attendue (W) à partir de l'irradiance dans le plan des modules. */
export function puissanceAttendueInclineeW(gIncl: number, mois: number): number {
  return P_CRETE_W * (gIncl / 1000) * prReference(mois);
}

/** Classe une performance (en %, déjà arrondie) selon les seuils d'affichage. */
export function etatPerformance(pct: number): EtatPerfInstantanee {
  if (pct > 110) return 'incoherent';
  if (pct >= 90) return 'normal';
  if (pct >= 80) return 'vigilance';
  return 'anomalie';
}

/**
 * @param pvP   puissance PV mesurée (W)
 * @param g     irradiance horizontale actuelle (W/m²) — sert au seuil de 100 W/m²
 * @param mois  mois local 1..12
 * @param gIncl irradiance actuelle dans le plan des modules (W/m²), si disponible
 */
export function performanceInstantanee(
  pvP: number | null | undefined,
  g: number | null | undefined,
  mois: number,
  gIncl?: number | null,
): PerfInstantanee {
  if (g != null && Number.isFinite(g) && g < G_MIN_W_M2) {
    return { pct: null, etat: 'indisponible', motif: 'lumiere_faible' };
  }
  if (pvP == null || g == null || !Number.isFinite(g)) {
    return { pct: null, etat: 'indisponible', motif: 'donnees' };
  }
  const pAtt = gIncl != null && Number.isFinite(gIncl) && gIncl > 0
    ? puissanceAttendueInclineeW(gIncl, mois)
    : puissanceAttendueW(g, mois);
  if (!(pAtt > 0)) return { pct: null, etat: 'indisponible', motif: 'donnees' };
  // Classement sur la valeur affichée (arrondie) : l'affichage et la couleur concordent.
  const pct = Math.round((pvP / pAtt) * 100);
  return { pct, etat: etatPerformance(pct) };
}
