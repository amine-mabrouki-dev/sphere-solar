"""
Production de référence de l'installation (simulation PVsyst V7.2.8, chapitre 2)
et comparaison avec la production mesurée.

Indicateur : r(j) = E_mes(j) / E_att(j)
  - mode « irradiance » : E_att(j) = Pc × H_inc(j) × PR_ref(m)
        H_inc(j) = H_hor(j) × (GlobInc / GlobHor du mois)   [conversion plan incliné 30°]
        H_hor(j) : irradiation horizontale du jour (Open-Meteo)
  - mode « mensuel »    : E_att(j) = E_Grid(m) / nombre de jours du mois
        (référence moyenne PVsyst, utilisée si l'irradiation n'est pas disponible)

Méthode HORAIRE (si Open-Meteo fournit l'irradiance heure par heure) : chaque
heure est classée « nuit », « donnees_manquantes », « arret » ou
« fonctionnement » (etat_heure). On sépare alors :
  - la PERFORMANCE r(j) = Σ E_mes / Σ E_att sur les seules heures de
    fonctionnement, avec E_att(h) = Pc × (G_h / 1000) × (GlobInc/GlobHor) × PR(m) ;
  - la DISPONIBILITÉ = heures de fonctionnement / (fonctionnement + arrêt) ;
  - l'énergie non produite à cause des arrêts = Σ E_att des heures d'arrêt.
Un arrêt (client, réseau, onduleur) ou des mesures manquantes ne faussent donc
plus r. Sans données horaires, la méthode JOURNALIÈRE ci-dessus s'applique.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

P_CRETE_KWC = 10.8

# Bilans mensuels PVsyst (Tableau des bilans mensuels du chapitre 2)
#            GlobHor  GlobInc  E_Grid (MWh)  PR
PVSYST_MENSUEL = {
    1:  (86.9,  131.6, 1.318, 0.927),
    2:  (99.9,  134.4, 1.330, 0.917),
    3:  (146.3, 172.9, 1.677, 0.898),
    4:  (176.6, 188.0, 1.792, 0.883),
    5:  (203.7, 197.3, 1.863, 0.874),
    6:  (209.7, 195.2, 1.814, 0.860),
    7:  (221.4, 209.7, 1.913, 0.845),
    8:  (200.3, 204.9, 1.873, 0.847),
    9:  (160.8, 183.2, 1.708, 0.863),
    10: (131.2, 170.2, 1.618, 0.880),
    11: (97.2,  146.3, 1.432, 0.906),
    12: (81.0,  129.3, 1.293, 0.926),
}

# Règle de détection (à calibrer sur les données réelles du site)
SEUIL_R = 0.90             # en dessous : production anormalement basse
SEUIL_VIGILANCE = 0.95     # entre 0,90 et 0,95 : à surveiller
SEUIL_INCOHERENT = 1.10    # au-dessus : physiquement peu plausible (compteur ou données à vérifier)
JOURS_CONSECUTIFS = 3      # durée minimale d'un écart pour lever une alerte
REBOND_NETTOYAGE = 0.08    # remontée minimale de r d'un jour à l'autre = nettoyage probable
R_MIN_APRES_NETTOYAGE = 0.95   # après un nettoyage, r doit revenir dans [0,95 ; 1,10]
MESSAGE_INCOHERENT = "Valeur à vérifier (compteur ou données)"

# Complétude des mesures pendant la période ensoleillée (lever → coucher du soleil)
TROU_MAX_S = 30 * 60       # absence de mesures tolérée au plus (30 min)
COUVERTURE_MIN = 0.80      # part minimale de la période ensoleillée couverte
PAS_CONTINU_S = 10 * 60    # deux mesures espacées d'au plus 10 min : période couverte
MESSAGE_INCOMPLET = "Données incomplètes (acquisition interrompue)"


def pr_reference(month: int) -> float:
    return PVSYST_MENSUEL[month][3]


def facteur_inclinaison(month: int) -> float:
    """Rapport GlobInc / GlobHor du mois : passe de l'irradiation horizontale
    à l'irradiation reçue par le plan des modules (30°, plein sud)."""
    glob_hor, glob_inc, _, _ = PVSYST_MENSUEL[month]
    return glob_inc / glob_hor


def energie_attendue(day: date, h_hor_kwh_m2: Optional[float]) -> tuple[float, str]:
    """Énergie attendue du jour (kWh) et mode de calcul utilisé."""
    m = day.month
    if h_hor_kwh_m2 is not None and h_hor_kwh_m2 > 0:
        h_inc = h_hor_kwh_m2 * facteur_inclinaison(m)
        return P_CRETE_KWC * h_inc * pr_reference(m), "irradiance"
    e_grid_mwh = PVSYST_MENSUEL[m][2]
    return e_grid_mwh * 1000.0 / calendar.monthrange(day.year, m)[1], "mensuel"


@dataclass
class JourPerformance:
    date: str
    energie_mesuree_kwh: float        # méthode horaire : heures de fonctionnement seulement
    energie_attendue_kwh: float       # idem
    irradiation_kwh_m2: Optional[float]
    mode: str
    r: float
    etat: str          # "normal", "vigilance", "anomalie", "incoherent" (r > 1,10),
                       # "incomplete" (méthode journalière : mesures interrompues) ou
                       # "fonctionnement_insuffisant" (méthode horaire : moins de 3 h)
    nettoyage: bool = False   # True si une remontée de r évoque un nettoyage ce jour-là
    methode: str = "journaliere"                      # "journaliere" ou "horaire"
    # Méthode horaire uniquement (None en méthode journalière)
    heures_fonctionnement: Optional[int] = None
    heures_soleil_utile: Optional[int] = None         # fonctionnement + arrêt
    heures_soleil_total: Optional[int] = None         # fonctionnement + arrêt + données manquantes
    heures_arret: Optional[int] = None
    heures_donnees_manquantes: Optional[int] = None
    disponibilite: Optional[float] = None             # % : fonctionnement / (fonctionnement + arrêt)
    energie_perdue_arret_kwh: Optional[float] = None  # énergie attendue des heures d'arrêt
    heures_incoherentes: Optional[int] = None         # heures à l'énergie invraisemblable


def etat_jour(r: float) -> str:
    # Ni « normal » ni « anomalie » : une production nettement supérieure à la
    # référence révèle un problème de compteur ou de données, pas une performance.
    if r > SEUIL_INCOHERENT:
        return "incoherent"
    if r < SEUIL_R:
        return "anomalie"
    if r < SEUIL_VIGILANCE:
        return "vigilance"
    return "normal"


def couverture_mesures(timestamps: Iterable[int], debut: int, fin: int) -> tuple[bool, int, float]:
    """Complétude des mesures d'une journée sur la période ensoleillée [debut ; fin]
    (timestamps Unix, lever et coucher du soleil).

    Les absences de mesures sont les écarts entre deux mesures consécutives, en
    comptant aussi le début (lever → première mesure) et la fin (dernière mesure
    → coucher). Un écart d'au plus PAS_CONTINU_S est une acquisition continue ;
    un écart plus long est une absence, retirée de la durée couverte.

    Retourne (complète, plus longue absence en s, part couverte 0..1).
    La journée est complète si aucune absence ne dépasse TROU_MAX_S et si au
    moins COUVERTURE_MIN de la période est couverte."""
    duree = fin - debut
    if duree <= 0:
        return True, 0, 1.0
    points = sorted({t for t in timestamps if debut <= t <= fin})
    bornes = [debut] + points + [fin]
    ecarts = [b - a for a, b in zip(bornes, bornes[1:])]
    trou_max = max(ecarts)
    non_couvert = sum(e for e in ecarts if e > PAS_CONTINU_S)
    taux = 1.0 - non_couvert / duree
    return trou_max <= TROU_MAX_S and taux >= COUVERTURE_MIN, trou_max, taux


# ── Éléments communs aux deux méthodes ────────────────────────────────────────
# (la méthode horaire elle-même est dans app/performance_horaire.py)

MESSAGE_FONCTIONNEMENT_INSUFFISANT = "Fonctionnement insuffisant (moins de 3 h au soleil)"

# États exclus de l'analyse (alerte, perte estimée, nettoyage)
ETATS_EXCLUS = ("incoherent", "incomplete", "fonctionnement_insuffisant")


# ── Méthode journalière ───────────────────────────────────────────────────────

def jour_journalier(d: date, e_mes: float, h_hor: Optional[float],
                    complet: bool = True) -> JourPerformance:
    """Comparaison d'une journée entière (énergie du jour, irradiation du jour)."""
    e_att, mode = energie_attendue(d, h_hor)
    r = e_mes / e_att if e_att > 0 else 0.0
    return JourPerformance(
        date=d.isoformat(), energie_mesuree_kwh=round(e_mes, 2),
        energie_attendue_kwh=round(e_att, 2),
        irradiation_kwh_m2=round(h_hor, 2) if h_hor is not None else None,
        mode=mode, r=round(r, 3), etat=etat_jour(r) if complet else "incomplete")


def comparer(jours: List[tuple]) -> dict:
    """Méthode journalière. jours : liste (date, énergie mesurée kWh, irradiation
    horizontale kWh/m² ou None [, mesures complètes : bool]), dans l'ordre
    chronologique. Sans 4e élément, la journée est considérée complète."""
    return synthese([jour_journalier(*j) for j in jours])


def message_jours_valides(alerte: bool, consecutifs: int,
                          dernier_valide: Optional[JourPerformance]) -> str:
    """Conclusion de la carte, tirée de la règle d'alerte sur les jours valides."""
    if alerte:
        return (f"Production inférieure à {int(SEUIL_R * 100)} % de la référence depuis "
                f"{consecutifs} jours : perte de performance probable (encrassement, "
                f"défaut sur une chaîne). Vérification ou nettoyage conseillé.")
    if dernier_valide is None:
        return "Pas encore de journée valide."
    if dernier_valide.etat == "anomalie":
        return (f"Dernier jour valide sous {int(SEUIL_R * 100)} % de la référence : "
                f"à surveiller (alerte après {JOURS_CONSECUTIFS} jours).")
    if dernier_valide.etat == "vigilance":
        return "Production légèrement inférieure à la référence : à surveiller."
    return "Production conforme à la référence."


def synthese(detail: List[JourPerformance]) -> dict:
    """Règles communes aux deux méthodes, appliquées à r(j) : écart durable sous
    0,90, nettoyage, perte estimée, message. detail : ordre chronologique."""
    # Les jours incohérents (r > 1,10), incomplets (acquisition interrompue) et à
    # fonctionnement insuffisant ne sont pas des mesures fiables de la
    # performance : ils sont ignorés par le comptage de l'écart durable, la
    # détection du nettoyage et la perte estimée (ils ne prolongent ni
    # n'interrompent une série d'anomalies).
    valides = [j for j in detail if j.etat not in ETATS_EXCLUS]

    # Écart durable : nombre de jours consécutifs sous le seuil, en partant du plus récent
    consecutifs = 0
    for j in reversed(valides):
        if j.r < SEUIL_R:
            consecutifs += 1
        else:
            break

    alerte = consecutifs >= JOURS_CONSECUTIFS

    # Détection d'un nettoyage : après au moins JOURS_CONSECUTIFS jours d'anomalie,
    # r remonte d'au moins REBOND_NETTOYAGE ET revient dans une plage plausible
    # [0,95 ; 1,10]. On retient la date du nettoyage le plus récent.
    nettoyage_detecte: Optional[str] = None
    anomalies_avant = 0          # nb de jours d'anomalie consécutifs se terminant la veille
    for precedent, j in zip(valides, valides[1:]):
        anomalies_avant = anomalies_avant + 1 if precedent.r < SEUIL_R else 0
        if (anomalies_avant >= JOURS_CONSECUTIFS
                and j.r - precedent.r >= REBOND_NETTOYAGE
                and R_MIN_APRES_NETTOYAGE <= j.r <= SEUIL_INCOHERENT):
            j.nettoyage = True
            nettoyage_detecte = j.date
    dernier = detail[-1] if detail else None
    if alerte:
        message = (f"Production inférieure à {int(SEUIL_R * 100)} % de la référence depuis "
                   f"{consecutifs} jours : perte de performance probable (encrassement, "
                   f"défaut sur une chaîne). Vérification ou nettoyage conseillé.")
    elif dernier and dernier.etat == "incoherent":
        # Jamais « Production conforme » sur une valeur invraisemblable
        message = (f"Dernier jour : valeur à vérifier (compteur ou données) — production "
                   f"mesurée supérieure de plus de {round((SEUIL_INCOHERENT - 1) * 100)} % "
                   f"à la référence, jour exclu de l'analyse.")
    elif dernier and dernier.etat == "incomplete":
        message = (f"Dernier jour : {MESSAGE_INCOMPLET[0].lower()}{MESSAGE_INCOMPLET[1:]}, "
                   f"jour exclu de l'analyse.")
    elif dernier and dernier.etat == "fonctionnement_insuffisant":
        message = (f"Dernier jour : {MESSAGE_FONCTIONNEMENT_INSUFFISANT[0].lower()}"
                   f"{MESSAGE_FONCTIONNEMENT_INSUFFISANT[1:]}, performance non jugée.")
    elif dernier and dernier.etat == "vigilance":
        message = "Production légèrement inférieure à la référence : à surveiller."
    elif dernier:
        message = "Production conforme à la référence."
    else:
        message = "Pas encore assez de données."

    perte_kwh = sum(max(0.0, j.energie_attendue_kwh - j.energie_mesuree_kwh) for j in valides)
    # Énergie non produite à cause des arrêts : tous les jours (méthode horaire),
    # y compris ceux dont la performance n'est pas jugée
    perte_arret = sum(j.energie_perdue_arret_kwh or 0.0 for j in detail)
    # Message et dernier jour fondés sur les seuls jours VALIDES (normal,
    # vigilance, anomalie) : un jour exclu ne remplace jamais la conclusion.
    dernier_valide = valides[-1] if valides else None
    message_valides = message_jours_valides(alerte, consecutifs, dernier_valide)
    return {
        "seuil_r": SEUIL_R,
        "seuil_incoherent": SEUIL_INCOHERENT,
        "jours_consecutifs_requis": JOURS_CONSECUTIFS,
        "jours_sous_seuil": consecutifs,
        "alerte_performance": alerte,
        "message": message,
        "r_dernier_jour": dernier.r if dernier else None,
        "message_jours_valides": message_valides,
        "dernier_jour_valide": ({"date": dernier_valide.date, "r": dernier_valide.r,
                                 "etat": dernier_valide.etat, "methode": dernier_valide.methode}
                                if dernier_valide else None),
        "perte_estimee_kwh": round(perte_kwh, 1),
        "energie_perdue_arret_kwh": round(perte_arret, 1),
        "nettoyage_detecte": nettoyage_detecte,
        "jours": [j.__dict__ for j in detail],
    }
