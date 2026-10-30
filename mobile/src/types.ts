export interface Installation {
  id: number;
  name: string;
  location: string | null;
}

export interface Inverter {
  id: number;
  serial: string;
  model: string | null;
}

export interface LatestMetrics {
  inverter_id: number;
  ts: number | null;
  pv_v: number | null;
  pv_i: number | null;
  pv2_v?: number | null;   // entrée PV 2 (absente avec un ancien firmware ou serveur)
  pv2_i?: number | null;
  pv_p: number | null;
  ac_v: number | null;
  ac_i: number | null;
  freq: number | null;
  e_day: number | null;
  e_total: number | null;
  batt_v: number | null;
  batt_i: number | null;
  batt_soc: number | null;
  temp: number | null;
  alarm: number | null;
  updated_at: number | null;
}

export interface Reading extends Omit<LatestMetrics, 'inverter_id' | 'updated_at'> {
  id: number;
  ts: number;
}

export interface EnergyPoint {
  bucket: string;   // 'YYYY-MM-DD' for day, 'YYYY-MM' for month
  energy_kwh: number | null;
}

export interface Alert {
  id: number;
  inverter_id: number;
  code: number;
  message: string | null;
  raised_at: number;
  cleared_at: number | null;
}

// Prévision de demain calculée par le serveur (backend/app/prevision.py) ;
// seule `explication` est rédigée par le modèle de langage.
export interface Forecast {
  date: string;                              // demain, JJ/MM
  prevision_kwh: number;
  fourchette_min_kwh: number;
  fourchette_max_kwh: number;
  marge_pct: number;
  energie_attendue_kwh: number;
  irradiation_prevue_kwh_m2: number | null;  // null : météo de demain indisponible
  couverture_nuageuse_prevue_pct: number | null;
  performance_utilisee: number;
  performance_mesuree: boolean;
  nb_jours_valides: number;
  source_meteo: string;
  remarques: string[];
  explication: string;
}

export interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
}

// 'incoherent' : r > 1,10 → valeur à vérifier (compteur ou données), exclue de la perte
// 'incomplete' : mesures interrompues pendant la période ensoleillée, exclue de l'analyse
// 'fonctionnement_insuffisant' : moins de 3 h de fonctionnement au soleil, performance non jugée
export type PerfState =
  | 'normal' | 'vigilance' | 'anomalie' | 'incoherent' | 'incomplete' | 'fonctionnement_insuffisant';

export interface PerfDay {
  date: string;                       // 'YYYY-MM-DD'
  energie_mesuree_kwh: number;
  energie_attendue_kwh: number;
  irradiation_kwh_m2: number | null;
  mode: 'irradiance' | 'mensuel';
  r: number;                          // ratio mesuré / attendu
  etat: PerfState;
  jour_courant?: boolean;             // true : journée d'aujourd'hui, comparée après le coucher du soleil
  // Méthode horaire : énergies et r ne portent que sur les heures de fonctionnement.
  // Champs null (ou absents avec un backend antérieur) en méthode journalière.
  // journaliere : journée complète (ni arrêt ni mesures manquantes) ou pas de données horaires ;
  // horaire : arrêt ou mesures manquantes, r sur les seules heures de fonctionnement
  methode?: 'journaliere' | 'horaire';
  heures_fonctionnement?: number | null;
  heures_soleil_utile?: number | null; // fonctionnement + arrêt
  heures_soleil_total?: number | null; // fonctionnement + arrêt + données manquantes
  heures_arret?: number | null;
  heures_donnees_manquantes?: number | null;
  disponibilite?: number | null;      // % : fonctionnement / (fonctionnement + arrêt)
  energie_perdue_arret_kwh?: number | null;
}

/** Journée d'aujourd'hui (objet « aujourdhui » de la route /performance). */
export interface PerfAujourdhui {
  energie_kwh: number | null;         // énergie produite depuis minuit local
  termine: boolean;                   // true après coucher du soleil + 30 min
  comparaison_a_partir_de: string;    // 'HH:MM' (heure locale)
}

export interface Performance {
  inverter_id: number;
  mode_demande: 'auto' | 'irradiance' | 'mensuel';
  seuil_r: number;
  seuil_incoherent?: number;          // au-dessus : jour « incohérent » (1,10)
  jours_consecutifs_requis: number;
  jours_sous_seuil: number;
  alerte_performance: boolean;
  message: string;
  r_dernier_jour: number | null;
  perte_estimee_kwh: number;
  energie_perdue_arret_kwh?: number;  // somme des énergies attendues des heures d'arrêt
  mode?: 'combinee' | 'journaliere'; // combinee : irradiance horaire disponible
  // Conclusion fondée sur les seuls jours valides (normal, vigilance, anomalie)
  message_jours_valides?: string;
  dernier_jour_valide?: { date: string; r: number; etat: PerfState; methode?: string } | null;
  nettoyage_detecte: string | null;   // date 'YYYY-MM-DD' du nettoyage détecté, ou null
  donnees_demonstration?: boolean;    // true si la période provient du scénario de démo
  aujourdhui?: PerfAujourdhui;        // absent avec un backend antérieur
  jours: PerfDay[];
}
