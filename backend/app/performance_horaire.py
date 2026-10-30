"""
Méthode HORAIRE de comparaison à la référence : performance et disponibilité.

Chaque heure locale [h ; h+1[ est classée (etat_heure) :
  - « nuit »                 : irradiance < 50 W/m² (ou inconnue) ;
  - « donnees_manquantes »   : moins de 50 % des mesures attendues dans l'heure ;
  - « faible_ensoleillement » : puissance quasi nulle sous 50 à 100 W/m² (aube,
                               crépuscule) — l'onduleur peut ne pas avoir démarré ;
  - « arret »                : puissance < 2 % de l'attendue avec G ≥ 100 W/m² ;
  - « fonctionnement »       : sinon.

Par jour (bilan_journalier) :
  - performance r(j) = Σ E_mes / Σ E_att sur les seules heures de fonctionnement ;
  - disponibilité = heures de fonctionnement / (fonctionnement + arrêt) ;
  - énergie perdue à l'arrêt = Σ E_att des heures d'arrêt.
Les heures « nuit », « faible_ensoleillement » et « donnees_manquantes »
n'entrent ni dans la performance ni dans la disponibilité.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from app.reference import (
    MESSAGE_FONCTIONNEMENT_INSUFFISANT, P_CRETE_KWC, JourPerformance, etat_jour,
    facteur_inclinaison, jour_journalier, pr_reference,
)

G_NUIT = 50.0                  # W/m² : en dessous, l'heure est « nuit »
G_ARRET_MIN = 100.0            # W/m² : un arrêt n'est constaté qu'avec au moins ce soleil
PART_MESURES_MIN = 0.50        # moins de 50 % des mesures attendues : données manquantes
PART_PUISSANCE_ARRET = 0.02    # puissance < 2 % de l'attendue : installation à l'arrêt
HEURES_FONCTIONNEMENT_MIN = 3  # en dessous, la performance du jour n'est pas jugée
PERIODE_ENVOI_MIN_S = 0.5      # période d'envoi nominale de l'ESP32 (PUBLISH_MS = 500 ms)
HEURES_METEO_MIN = 20          # heures Open-Meteo renseignées au minimum pour analyser un jour

ETATS_HEURE = ("nuit", "donnees_manquantes", "faible_ensoleillement", "arret", "fonctionnement")

__all__ = [
    "HeureMesuree", "irradiance_horaire", "diffuse_horaire", "serie_horaire",
    "energie_attendue_heure", "energie_attendue_heure_inclinee", "energie_attendue_de",
    "mesures_attendues_par_heure", "etat_heure", "bilan_journalier", "choisir_methode",
    "heure_incoherente", "nb_heures_incoherentes", "appliquer_vraisemblance",
    "MESSAGE_FONCTIONNEMENT_INSUFFISANT",
]


@dataclass
class HeureMesuree:
    """Une heure locale [h ; h+1[ : irradiance Open-Meteo et mesures de readings."""
    g_wm2: Optional[float]             # irradiance horizontale moyenne de l'heure (W/m²)
    nb_mesures: int                    # mesures reçues pendant l'heure
    energie_kwh: Optional[float]       # énergie produite pendant l'heure
    puissance_moy_w: Optional[float]   # puissance moyenne de l'heure
    # irradiance sur le plan des modules (W/m², app/plan_incline.py) ; None si
    # la diffuse n'est pas disponible → G × (GlobInc / GlobHor du mois)
    g_inc_wm2: Optional[float] = None


def irradiance_horaire(hourly: dict) -> Dict[str, List[Optional[float]]]:
    """Irradiance GLOBALE horizontale horaire (shortwave_radiation), voir serie_horaire."""
    return serie_horaire(hourly, "shortwave_radiation")


def diffuse_horaire(hourly: dict) -> Dict[str, List[Optional[float]]]:
    """Irradiance DIFFUSE horizontale horaire (diffuse_radiation), voir serie_horaire.
    Vide si Open-Meteo ne la fournit pas."""
    return serie_horaire(hourly, "diffuse_radiation")


def serie_horaire(hourly: dict, cle: str) -> Dict[str, List[Optional[float]]]:
    """Série horaire Open-Meteo → {date locale : 24 valeurs (W/m²)}.

    Chez Open-Meteo, une valeur horaire datée T est la moyenne de l'heure
    PRÉCÉDENTE (de T − 1 h à T) : la valeur datée « 2026-10-18T10:00 » couvre
    09:00 – 10:00, c'est-à-dire l'heure locale qui commence à 9 h.
    Seuls les jours ayant au moins HEURES_METEO_MIN heures renseignées sont gardés."""
    horaire: Dict[str, List[Optional[float]]] = {}
    for t, g in zip(hourly.get("time", []), hourly.get(cle, [])):
        try:
            debut = datetime.fromisoformat(t) - timedelta(hours=1)
        except (TypeError, ValueError):
            continue
        horaire.setdefault(debut.date().isoformat(), [None] * 24)[debut.hour] = g
    return {d: v for d, v in horaire.items()
            if sum(g is not None for g in v) >= HEURES_METEO_MIN}


def energie_attendue_heure(month: int, g_wm2: Optional[float]) -> float:
    """Énergie attendue d'une heure (kWh) :
    10,8 × (G_h / 1000) × (GlobInc / GlobHor du mois) × PR_ref du mois."""
    g = g_wm2 if g_wm2 is not None and g_wm2 > 0 else 0.0
    return P_CRETE_KWC * g / 1000.0 * facteur_inclinaison(month) * pr_reference(month)


def energie_attendue_heure_inclinee(month: int, g_inc_wm2: float) -> float:
    """Énergie attendue d'une heure (kWh) à partir de l'irradiance déjà ramenée
    au plan des modules : 10,8 × (G_inc / 1000) × PR_ref du mois."""
    return P_CRETE_KWC * max(0.0, g_inc_wm2) / 1000.0 * pr_reference(month)


def energie_attendue_de(month: int, h: HeureMesuree) -> float:
    """Énergie attendue d'une heure : irradiance inclinée si elle est connue,
    sinon conversion mensuelle G × (GlobInc / GlobHor)."""
    if h.g_inc_wm2 is not None:
        return energie_attendue_heure_inclinee(month, h.g_inc_wm2)
    return energie_attendue_heure(month, h.g_wm2)


def mesures_attendues_par_heure(nb_par_heure: Iterable[int]) -> float:
    """Nombre de mesures attendues dans une heure pour une journée.

    La période d'envoi de l'ESP32 vaut 0,5 s par défaut mais se règle à distance
    (commande set_interval), et le scénario de démonstration écrit une mesure
    toutes les 10 min. On prend donc la cadence de l'heure la mieux couverte de
    la journée, plafonnée à la période nominale de l'ESP32 (7 200 mesures/h)."""
    return float(min(3600.0 / PERIODE_ENVOI_MIN_S, max(nb_par_heure, default=0)))


def etat_heure(g_wm2: Optional[float], nb_mesures: int, nb_attendues: float,
               puissance_moy_w: Optional[float], puissance_att_w: float) -> str:
    """État d'une heure (voir l'en-tête du module)."""
    if g_wm2 is None or g_wm2 < G_NUIT:
        return "nuit"
    if nb_attendues <= 0 or nb_mesures < PART_MESURES_MIN * nb_attendues or puissance_moy_w is None:
        return "donnees_manquantes"
    if puissance_moy_w < PART_PUISSANCE_ARRET * puissance_att_w:
        return "arret" if g_wm2 >= G_ARRET_MIN else "faible_ensoleillement"
    return "fonctionnement"


def bilan_journalier(d: date, heures: List[HeureMesuree]) -> JourPerformance:
    """Bilan horaire d'une journée : performance et disponibilité à partir de
    ses 24 heures locales."""
    m = d.month
    attendues = mesures_attendues_par_heure(h.nb_mesures for h in heures)
    e_mes = e_att = e_arret = 0.0
    n = {e: 0 for e in ETATS_HEURE}
    for h in heures:
        e_att_h = energie_attendue_de(m, h)
        etat = etat_heure(h.g_wm2, h.nb_mesures, attendues, h.puissance_moy_w, e_att_h * 1000.0)
        n[etat] += 1
        if etat == "fonctionnement":
            e_mes += h.energie_kwh if h.energie_kwh is not None else h.puissance_moy_w / 1000.0
            e_att += e_att_h
        elif etat == "arret":
            e_arret += e_att_h
    r = e_mes / e_att if e_att > 0 else 0.0
    soleil = n["fonctionnement"] + n["arret"]
    irradiation = sum(h.g_wm2 for h in heures if h.g_wm2 is not None) / 1000.0
    return JourPerformance(
        date=d.isoformat(), energie_mesuree_kwh=round(e_mes, 2),
        energie_attendue_kwh=round(e_att, 2), irradiation_kwh_m2=round(irradiation, 2),
        mode="irradiance", r=round(r, 3),
        etat=(etat_jour(r) if n["fonctionnement"] >= HEURES_FONCTIONNEMENT_MIN
              else "fonctionnement_insuffisant"),
        methode="horaire",
        heures_fonctionnement=n["fonctionnement"], heures_soleil_utile=soleil,
        heures_soleil_total=soleil + n["donnees_manquantes"], heures_arret=n["arret"],
        heures_donnees_manquantes=n["donnees_manquantes"],
        disponibilite=round(100.0 * n["fonctionnement"] / soleil, 1) if soleil else None,
        energie_perdue_arret_kwh=round(e_arret, 2))


# ── Méthode combinée : choix de la méthode pour chaque jour ───────────────────

def choisir_methode(bilan: JourPerformance, e_jour_kwh: float,
                    h_hor_kwh_m2: Optional[float]) -> JourPerformance:
    """Méthode retenue pour un jour, à partir de son bilan horaire.

      - Aucune heure de soleil mesurée (fonctionnement + arrêt = 0) : les mesures
        horaires sont inutilisables (ex. scénario de démonstration à une mesure
        par jour) → méthode JOURNALIÈRE, disponibilité inconnue (null).
      - Aucune heure « arret » ni « donnees_manquantes » : installation en marche
        et mesurée pendant tout le soleil utile → méthode JOURNALIÈRE pour r
        (énergie du jour ÷ énergie attendue avec l'irradiation journalière),
        plus robuste aux erreurs de la météo heure par heure. Les heures et la
        disponibilité (100 %) viennent du bilan horaire.
      - Sinon (arrêt ou mesures manquantes) → méthode HORAIRE : r sur les seules
        heures de fonctionnement (le bilan horaire tel quel).
    Moins de 3 heures de fonctionnement : « fonctionnement_insuffisant » dans
    tous les cas où les heures sont connues."""
    d = date.fromisoformat(bilan.date)
    soleil = (bilan.heures_fonctionnement or 0) + (bilan.heures_arret or 0)
    if soleil == 0:
        return jour_journalier(d, e_jour_kwh, h_hor_kwh_m2)
    if bilan.heures_arret == 0 and bilan.heures_donnees_manquantes == 0:
        jour = jour_journalier(d, e_jour_kwh, h_hor_kwh_m2)
        if bilan.heures_fonctionnement < HEURES_FONCTIONNEMENT_MIN:
            jour.etat = "fonctionnement_insuffisant"
        jour.heures_fonctionnement = bilan.heures_fonctionnement
        jour.heures_soleil_utile = soleil
        jour.heures_soleil_total = soleil
        jour.heures_arret = 0
        jour.heures_donnees_manquantes = 0
        jour.disponibilite = bilan.disponibilite
        jour.energie_perdue_arret_kwh = 0.0
        return jour
    return bilan


# ── Vraisemblance des énergies horaires ───────────────────────────────────────

FACTEUR_ENERGIE_MAX = 1.1      # une heure ne peut dépasser 1,1 × P_crête × 1 h (11,88 kWh)
FACTEUR_ATTENDUE_MAX = 3.0     # ni 3 × l'énergie attendue…
G_VRAISEMBLANCE_MIN = 200.0    # …quand l'irradiance atteint au moins 200 W/m²


def heure_incoherente(energie_kwh: Optional[float], energie_attendue_kwh: float,
                      g_wm2: Optional[float]) -> bool:
    """True si l'énergie mesurée d'une heure est physiquement invraisemblable :
      - plus de 1,1 × puissance crête × 1 h (11,88 kWh pour 10,8 kWc), quelle
        que soit l'heure ;
      - ou plus de 3 × l'énergie attendue, avec une irradiance d'au moins
        200 W/m² (sous 200 W/m², l'attendue est trop petite pour un rapport fiable).
    Typiquement un saut de e_day (redémarrage, simulation accélérée)."""
    if energie_kwh is None:
        return False
    if energie_kwh > FACTEUR_ENERGIE_MAX * P_CRETE_KWC:
        return True
    return (g_wm2 is not None and g_wm2 >= G_VRAISEMBLANCE_MIN
            and energie_kwh > FACTEUR_ATTENDUE_MAX * energie_attendue_kwh)


def nb_heures_incoherentes(d: date, heures: List[HeureMesuree]) -> int:
    """Nombre d'heures « incoherente » du jour d (toutes les heures mesurées)."""
    return sum(heure_incoherente(h.energie_kwh, energie_attendue_de(d.month, h), h.g_wm2)
               for h in heures)


def appliquer_vraisemblance(jour: JourPerformance, heures: List[HeureMesuree]) -> JourPerformance:
    """Un jour qui contient au moins une heure « incoherente » prend l'état
    « incoherent » (à vérifier), quelle que soit la méthode retenue."""
    n = nb_heures_incoherentes(date.fromisoformat(jour.date), heures)
    jour.heures_incoherentes = n
    if n:
        jour.etat = "incoherent"
    return jour
