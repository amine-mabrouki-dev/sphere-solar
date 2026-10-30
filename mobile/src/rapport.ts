/**
 * Synthèse des rapports (onglet Rapports et rapport PDF), à partir de
 * GET /installations/{id}/report-data (backend/app/report.py, schéma Pydantic
 * SyntheseRapport de backend/app/schemas.py) : période comparable, jours
 * valides et exclus, performance de la période.
 *
 * La réponse est vérifiée à son arrivée (lireSynthese) et toutes les fonctions
 * de mise en forme acceptent des valeurs absentes : un serveur d'une autre
 * version ne fait jamais planter l'écran.
 */
import type { PerfState } from './types';

// ── Format de la réponse (identique au schéma SyntheseRapport du serveur) ────

export interface PeriodeRapport {
  type: 'month' | 'year';
  annee: number;
  mois: number | null;
  debut: string;               // AAAA-MM-JJ : premier jour de la période
  fin: string;                 // AAAA-MM-JJ : dernier jour comparable (dernier jour
                               // de la période s'il n'y en a aucun)
  libelle: string;             // « Du 1er au 19 octobre 2026 »
  jours_comparables: number;   // jours complets passés de la période
  en_cours: boolean;
  future: boolean;
}

export interface JourRapport {
  date: string;                // AAAA-MM-JJ, heure locale
  onduleur: string;
  etat: PerfState;
  valide: boolean;
  r: number;
  energie_mesuree_kwh: number;
  energie_attendue_kwh: number;
  methode: string;
}

export interface SyntheseRapport {
  installation: { id: number; name: string; location: string | null };
  inverters: { id: number; serial: string; model: string | null }[];
  periode: PeriodeRapport;
  nb_jours_valides: number;
  nb_jours_exclus: number;
  nb_jours_sans_donnees: number;
  energie_produite_kwh: number;
  energie_attendue_kwh: number;
  performance: number | null;         // produite ÷ attendue (null : aucun jour valide)
  reference_pvsyst_mois_kwh: number;  // mois (ou année) entier, à titre indicatif
  co2_evite_kg: number;
  alarmes_onduleur: number;
  alertes_performance: number;
  jours_en_alerte_performance: number;
  economies_dt: number;
  arbres_equivalents: number;
  summary: { max_power_w: number; avg_temp_c: number | null };
  inverter_metrics: {
    id: number; serial: string; model: string | null; energie_produite_kwh: number;
    max_power_w: number; alertes_performance: number;
    alerts: { id: number; code: number; message: string | null; raised_at: number; cleared_at: number | null }[];
  }[];
  daily_production: JourRapport[];
}

const DATE_ISO = /^\d{4}-\d{2}-\d{2}$/;

/** La réponse du serveur si elle a le format attendu (periode avec debut, fin
 *  et libelle), sinon null — par exemple un serveur d'une version antérieure,
 *  qui renvoyait « period » avec start_date et end_date. */
export function lireSynthese(json: unknown): SyntheseRapport | null {
  if (!json || typeof json !== 'object') return null;
  const p = (json as { periode?: unknown }).periode as Partial<PeriodeRapport> | undefined;
  if (!p || typeof p !== 'object') return null;
  if (typeof p.debut !== 'string' || !DATE_ISO.test(p.debut)) return null;
  if (typeof p.fin !== 'string' || !DATE_ISO.test(p.fin)) return null;
  if (typeof p.libelle !== 'string') return null;
  return json as SyntheseRapport;
}

// ── Mise en forme ────────────────────────────────────────────────────────────

export const MOIS_LONG = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
  'septembre', 'octobre', 'novembre', 'décembre'];

export const MESSAGE_INDISPONIBLE = 'Synthèse indisponible pour cette période';
export const MESSAGE_AUCUNE_DONNEE = 'Aucune donnée pour cette période';

// Seuils habituels de la comparaison (backend/app/reference.py : SEUIL_R, SEUIL_VIGILANCE)
export const SEUIL_R = 0.90;
export const SEUIL_VIGILANCE = 0.95;

function estNombre(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** Nombre à la française : « 1 618,0 » (espace insécable pour les milliers) ; « — » si absent. */
export function nombreFr(v: unknown, decimales = 1): string {
  if (!estNombre(v)) return '—';
  const [ent, dec] = v.toFixed(decimales).split('.');
  const groupes = ent.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return dec ? `${groupes},${dec}` : groupes;
}

/** Nombre entier (compteur d'alertes, de jours) ; « — » si absent. */
export function entierFr(v: unknown): string {
  return estNombre(v) ? String(Math.round(v)) : '—';
}

/** « 82 % » ; « — » si absent. */
export function performancePct(p: unknown): string {
  return estNombre(p) ? `${Math.round(p * 100)} %` : '—';
}

/** Niveau de couleur de la performance, selon les seuils de la comparaison. */
export function niveauPerformance(p: unknown): 'normal' | 'vigilance' | 'anomalie' | null {
  if (!estNombre(p)) return null;
  if (p < SEUIL_R) return 'anomalie';
  if (p < SEUIL_VIGILANCE) return 'vigilance';
  return 'normal';
}

function pluriel(n: number, mot: string): string {
  return `${n} ${mot}${n > 1 ? 's' : ''}`;
}

type SyntheseLue = Partial<Pick<SyntheseRapport, 'nb_jours_valides' | 'nb_jours_exclus'>> & {
  periode?: Partial<PeriodeRapport> | null;
};

/** « Du 1er au 19 octobre 2026 — 17 jours valides, 2 exclus » ; le libellé seul
 *  sans jour comparé ; chaîne vide si la période ou ses champs sont absents. */
export function sousTitrePeriode(d: SyntheseLue | null | undefined): string {
  const p = d?.periode;
  if (!p || typeof p.debut !== 'string' || typeof p.fin !== 'string' || typeof p.libelle !== 'string') {
    return '';
  }
  const valides = d?.nb_jours_valides, exclus = d?.nb_jours_exclus;
  if (!estNombre(valides) || !estNombre(exclus) || valides + exclus === 0) return p.libelle;
  const texteExclus = exclus === 0 ? 'aucun exclu' : pluriel(exclus, 'exclu');
  return `${p.libelle} — ${pluriel(valides, 'jour')} ${valides > 1 ? 'valides' : 'valide'}, ${texteExclus}`;
}

/** true si aucun jour n'a été mesuré sur la période (ni valide ni exclu). */
export function aucuneDonnee(d: Partial<Pick<SyntheseRapport, 'nb_jours_valides' | 'nb_jours_exclus'>>): boolean {
  return !(estNombre(d.nb_jours_valides) && d.nb_jours_valides > 0)
    && !(estNombre(d.nb_jours_exclus) && d.nb_jours_exclus > 0);
}

/** « Référence PVsyst du mois entier : 1 618 kWh » */
export function mentionReferencePvsyst(
  d: { periode?: Partial<PeriodeRapport> | null; reference_pvsyst_mois_kwh?: number },
): string {
  const entier = d.periode?.type === 'year' ? "de l'année entière" : 'du mois entier';
  return `Référence PVsyst ${entier} : ${nombreFr(d.reference_pvsyst_mois_kwh, 0)} kWh`;
}

/** « Jours exclus : 2 (données incomplètes ou à vérifier) » (rapport PDF) */
export function ligneJoursExclus(nb: unknown): string {
  return `Jours exclus : ${entierFr(nb)} (données incomplètes ou à vérifier)`;
}

/** État d'un mois (1..12) de l'année `annee` par rapport à aujourd'hui. */
export function etatMois(annee: number, mois: number, aujourdhui: Date): 'passe' | 'en_cours' | 'futur' {
  const a = aujourdhui.getFullYear(), m = aujourdhui.getMonth() + 1;
  if (annee > a || (annee === a && mois > m)) return 'futur';
  return annee === a && mois === m ? 'en_cours' : 'passe';
}
