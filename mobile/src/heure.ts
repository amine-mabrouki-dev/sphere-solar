/**
 * Heure locale du site (Tunisie, UTC+1, pas d'heure d'été), indépendante du
 * fuseau configuré sur le téléphone ou l'émulateur (souvent UTC).
 * Formatage manuel : ne dépend pas du support Intl/timeZone du moteur JS.
 */
const DECALAGE_MS = 60 * 60 * 1000;   // UTC+1

const p2 = (n: number) => String(n).padStart(2, '0');

function versTunis(d: Date): Date {
  return new Date(d.getTime() + DECALAGE_MS);   // lire ensuite avec getUTC*
}

/** « HH:MM » */
export function heureTunis(d: Date = new Date()): string {
  const t = versTunis(d);
  return `${p2(t.getUTCHours())}:${p2(t.getUTCMinutes())}`;
}

/** Mois local du site, 1..12 */
export function moisTunis(d: Date = new Date()): number {
  return versTunis(d).getUTCMonth() + 1;
}

/** « JJ/MM/AAAA » */
export function dateTunis(d: Date = new Date()): string {
  const t = versTunis(d);
  return `${p2(t.getUTCDate())}/${p2(t.getUTCMonth() + 1)}/${t.getUTCFullYear()}`;
}

/** « JJ/MM/AAAA HH:MM » */
export function dateHeureTunis(d: Date = new Date()): string {
  return `${dateTunis(d)} ${heureTunis(d)}`;
}
