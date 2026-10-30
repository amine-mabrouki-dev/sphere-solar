/**
 * État affiché d'un jour de comparaison à la référence.
 * Garde-fou côté application : au-dessus de 110 % de la production attendue,
 * un jour est toujours « incoherent » (« À vérifier »), jamais « normal » —
 * même si le backend interrogé est une version antérieure sans cet état.
 * Seuil identique à SEUIL_INCOHERENT de backend/app/reference.py.
 */
import type { PerfAujourdhui, PerfDay, PerfState } from './types';

export const SEUIL_INCOHERENT = 1.10;

export const MENTION_INCOHERENT = 'Valeur à vérifier (compteur ou données)';
export const MENTION_INCOMPLETE = 'Données incomplètes (acquisition interrompue)';
export const MENTION_FONCTIONNEMENT_INSUFFISANT = 'Fonctionnement insuffisant (moins de 3 h au soleil)';

/** États exclus de l'analyse (affichés en gris, avec une mention). */
export function estExclu(etat: PerfState): boolean {
  return etat === 'incoherent' || etat === 'incomplete' || etat === 'fonctionnement_insuffisant';
}

/** Dernier jour VALIDE (normal, vigilance ou anomalie) d'une liste chronologique
 *  dont les états sont déjà ceux affichés (etatAffiche), ou null s'il n'y en a pas. */
export function dernierJourValide<T extends { etat: PerfState }>(jours: T[]): T | null {
  for (let i = jours.length - 1; i >= 0; i--) {
    if (!estExclu(jours[i].etat)) return jours[i];
  }
  return null;
}

/** Mention affichée sous un jour exclu de l'analyse, sinon null. */
export function mentionEtat(etat: PerfState): string | null {
  if (etat === 'incomplete') return MENTION_INCOMPLETE;
  if (etat === 'incoherent') return MENTION_INCOHERENT;
  if (etat === 'fonctionnement_insuffisant') return MENTION_FONCTIONNEMENT_INSUFFISANT;
  return null;
}

export function etatAffiche(j: Pick<PerfDay, 'r' | 'etat'>): PerfState {
  // Une journée incomplète ou à fonctionnement insuffisant le reste, quel que soit r
  if (j.etat === 'incomplete' || j.etat === 'fonctionnement_insuffisant') return j.etat;
  return j.r > SEUIL_INCOHERENT ? 'incoherent' : j.etat;
}

type JourHoraire = Pick<PerfDay, 'r' | 'heures_fonctionnement' | 'heures_soleil_utile'
  | 'heures_soleil_total' | 'heures_arret' | 'heures_donnees_manquantes' | 'disponibilite'
  | 'energie_perdue_arret_kwh'> & { etat?: PerfState };

/** Part maximale d'heures sans mesures pour afficher la disponibilité. */
export const PART_MANQUANTES_MAX = 0.20;

/** Heures de soleil au total (fonctionnement + arrêt + données manquantes). */
function heuresSoleilTotal(j: JourHoraire): number | null {
  if (j.heures_soleil_total != null) return j.heures_soleil_total;
  if (j.heures_fonctionnement == null || j.heures_arret == null) return null;
  return j.heures_fonctionnement + j.heures_arret + (j.heures_donnees_manquantes ?? 0);
}

/** true si la disponibilité est calculable : moins de 20 % des heures de soleil
 *  sans mesures. */
export function disponibiliteCalculable(j: JourHoraire): boolean {
  const total = heuresSoleilTotal(j);
  if (j.disponibilite == null || !total) return false;
  return (j.heures_donnees_manquantes ?? 0) < PART_MANQUANTES_MAX * total;
}

/** Valeur de r affichée : « — » pour un jour exclu (jamais de pourcentage),
 *  sinon « 93 » (sous la barre, en %) ou « 0,93 » (liste des jours). */
export function texteR(j: Pick<PerfDay, 'r' | 'etat'>, format: 'pourcent' | 'ratio'): string {
  if (estExclu(j.etat)) return '—';
  return format === 'pourcent' ? String(Math.round(j.r * 100)) : j.r.toFixed(2).replace('.', ',');
}

/** Heures de fonctionnement et heures de soleil utile, ou null si la disponibilité
 *  est inconnue (pas de données horaires). */
function heuresAuSoleil(j: JourHoraire): [number, number] | null {
  if (j.disponibilite == null || j.heures_fonctionnement == null) return null;
  const soleil = j.heures_soleil_utile ?? (j.heures_arret != null ? j.heures_fonctionnement + j.heures_arret : null);
  return soleil == null ? null : [j.heures_fonctionnement, soleil];
}

/** Indicateur gris sous le r d'un jour :
 *  - « 6 h / 10 h de soleil » (fonctionnement / soleil utile) si toutes les
 *    heures de soleil sont mesurées ;
 *  - « 2 h mesurées sur 10 h de soleil » (fonctionnement / soleil au total)
 *    s'il y a des heures sans mesures ;
 *  - null si les heures sont inconnues (pas de données horaires). */
export function libelleDisponibilite(j: JourHoraire): string | null {
  const h = heuresAuSoleil(j);
  if (!h) return null;
  const total = heuresSoleilTotal(j);
  if ((j.heures_donnees_manquantes ?? 0) > 0 && total != null) {
    return `${h[0]} h mesurées sur ${total} h de soleil`;
  }
  return `${h[0]} h / ${h[1]} h de soleil`;
}

/** Ligne de la liste des jours :
 *  « Performance 93 % — Disponibilité 60 % (6 h sur 10 h de soleil) »,
 *  ou « Performance 93 % » si la disponibilité est inconnue.
 *  null pour un jour exclu : jamais de « Performance NN % » (le motif est
 *  donné par mentionEtat). */
export function libelleDetailJour(j: JourHoraire): string | null {
  if (j.etat && estExclu(j.etat)) return null;
  const perf = `Performance ${Math.round(j.r * 100)} %`;
  const h = heuresAuSoleil(j);
  if (!h) return perf;
  if (!disponibiliteCalculable(j)) return `${perf} — Disponibilité : non calculable (données incomplètes)`;
  return `${perf} — Disponibilité ${Math.round(j.disponibilite!)} % (${h[0]} h sur ${h[1]} h de soleil)`;
}

export const SEUIL_PERDU_ARRET_KWH = 0.5;

/** « Perdu à l'arrêt : 21,4 kWh » si l'énergie perdue dépasse 0,5 kWh, sinon null. */
export function libellePerduArret(j: JourHoraire): string | null {
  const e = j.energie_perdue_arret_kwh;
  if (e == null || e <= SEUIL_PERDU_ARRET_KWH) return null;
  return `Perdu à l'arrêt : ${e.toFixed(1).replace('.', ',')} kWh`;
}

/** Note du bas de la carte selon la méthode utilisée par le serveur. */
export function noteReference(mode?: string, modeRefJournalier = 'moyenne mensuelle PVsyst'): string {
  if (mode === 'combinee') {
    return "Référence : PVsyst et irradiation d'Open-Meteo — méthode journalière pour les "
      + "journées complètes, horaire en cas d'arrêt ou de mesures manquantes";
  }
  return `Référence : ${modeRefJournalier}`;
}

/**
 * Texte de la pastille grise sous l'histogramme pour la journée d'aujourd'hui.
 *  - journée en cours : « Aujourd'hui : 22,2 kWh — comparaison à partir de 18:45 » ;
 *  - journée terminée (déjà dans l'histogramme) : null, pas de pastille ;
 *  - backend antérieur (pas d'objet « aujourdhui ») : « Aujourd'hui : en cours ».
 */
export function libellePastilleAujourdhui(auj?: PerfAujourdhui | null): string | null {
  if (!auj) return "Aujourd'hui : en cours";
  if (auj.termine) return null;
  const energie = auj.energie_kwh != null ? `${auj.energie_kwh.toFixed(1).replace('.', ',')} kWh — ` : '';
  return `Aujourd'hui : ${energie}comparaison à partir de ${auj.comparaison_a_partir_de}`;
}
