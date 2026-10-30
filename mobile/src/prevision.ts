/**
 * Textes de la carte « Prévision de demain » (onglet Assistant).
 * La prévision est calculée par le serveur (POST /inverters/{id}/forecast,
 * backend/app/prevision.py) ; l'application ne fait que la mettre en forme.
 */

/** Champs de la réponse du serveur utilisés par la carte. */
export interface PrevisionAffichee {
  prevision_kwh: number;
  fourchette_min_kwh: number;
  fourchette_max_kwh: number;
  irradiation_prevue_kwh_m2: number | null;
  performance_utilisee: number;
  performance_mesuree: boolean;
}

export const MENTION_PREVISION =
  'Estimation à partir de la météo prévue et de la performance des derniers jours.';

/** « ≈ 58,6 kWh » */
export function valeurPrevision(p: PrevisionAffichee): string {
  return `≈ ${p.prevision_kwh.toFixed(1).replace('.', ',')} kWh`;
}

/** « entre 53 et 64 kWh » (bornes arrondies au kWh) */
export function fourchettePrevision(p: PrevisionAffichee): string {
  return `entre ${Math.round(p.fourchette_min_kwh)} et ${Math.round(p.fourchette_max_kwh)} kWh`;
}

/** « Soleil prévu : 5,4 kWh/m² · Performance récente : 88 % » */
export function detailPrevision(p: PrevisionAffichee): string {
  const soleil = p.irradiation_prevue_kwh_m2 != null
    ? `${p.irradiation_prevue_kwh_m2.toFixed(1).replace('.', ',')} kWh/m²`
    : 'indisponible';
  const perf = p.performance_mesuree
    ? `${Math.round(p.performance_utilisee * 100)} %`
    : 'non mesurée';
  return `Soleil prévu : ${soleil} · Performance récente : ${perf}`;
}
