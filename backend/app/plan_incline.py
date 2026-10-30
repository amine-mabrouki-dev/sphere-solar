"""
Irradiance horaire sur le plan des modules (30°, plein sud) à Metlaoui.

Le rapport mensuel PVsyst GlobInc / GlobHor est juste sur une journée complète,
mais pas heure par heure : le gain du plan incliné est plus fort à midi qu'en
début ou en fin de journée. Pour chaque heure on calcule donc :

1. la position du soleil au milieu de l'heure (heure locale UTC+1) :
   déclinaison et équation du temps (formules de Cooper et Spencer), angle
   horaire, hauteur du soleil, angle d'incidence sur le plan incliné ;
2. l'irradiance inclinée par le modèle isotrope :
      G_inc = (G − D) × cos(incidence) / cos(zénith)
              + D × (1 + cos β) / 2 + G × albédo × (1 − cos β) / 2
   avec G et D les irradiances globale et diffuse horizontales d'Open-Meteo,
   le rapport cos(incidence) / cos(zénith) limité à 5, et la composante
   directe ignorée quand le soleil est à moins de 5° au-dessus de l'horizon ;
3. un calage mensuel pour rester cohérent avec PVsyst : sur une journée claire
   type du 15 du mois, on calcule le rapport Σ G_inc (modèle) ÷ Σ G, et chaque
   heure est multipliée par (GlobInc / GlobHor du mois) ÷ ce rapport. Sur une
   journée complète, on retrouve ainsi la référence de la méthode journalière.
"""
from __future__ import annotations

import math
from datetime import date
from functools import lru_cache
from typing import List, Optional, Sequence

from app.reference import facteur_inclinaison

LATITUDE = 34.3264            # degrés nord
LONGITUDE = 8.4050            # degrés est
UTC_DECALAGE_H = 1            # Africa/Tunis : UTC+1 toute l'année
INCLINAISON = 30.0            # degrés, plein sud
ALBEDO = 0.20
RB_MAX = 5.0                  # limite du rapport cos(incidence) / cos(zénith)
HAUTEUR_MIN = 5.0             # degrés : en dessous, composante directe ignorée
PART_DIFFUSE_CIEL_CLAIR = 0.15   # part diffuse de la journée claire type


def _rad(x: float) -> float:
    return math.radians(x)


def declinaison(d: date) -> float:
    """Déclinaison du soleil (degrés), formule de Cooper."""
    n = d.timetuple().tm_yday
    return 23.45 * math.sin(_rad(360.0 * (284 + n) / 365.0))


def equation_du_temps(d: date) -> float:
    """Équation du temps (minutes), formule de Spencer simplifiée."""
    b = _rad(360.0 * (d.timetuple().tm_yday - 81) / 364.0)
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def angle_horaire(d: date, heure_locale: float) -> float:
    """Angle horaire (degrés, négatif le matin) pour une heure locale décimale.
    Temps solaire = heure locale + 4 min × (longitude − méridien du fuseau) + équation du temps."""
    temps_solaire = (heure_locale
                     + (4.0 * (LONGITUDE - 15.0 * UTC_DECALAGE_H) + equation_du_temps(d)) / 60.0)
    return 15.0 * (temps_solaire - 12.0)


def cos_zenith(delta: float, omega: float) -> float:
    phi = _rad(LATITUDE)
    return (math.sin(phi) * math.sin(_rad(delta))
            + math.cos(phi) * math.cos(_rad(delta)) * math.cos(_rad(omega)))


def cos_incidence(delta: float, omega: float, beta: float = INCLINAISON) -> float:
    """Cosinus de l'angle d'incidence sur un plan incliné de beta, plein sud
    (hémisphère nord) : même formule que le zénith avec la latitude φ − β."""
    phi_b = _rad(LATITUDE - beta)
    return (math.sin(phi_b) * math.sin(_rad(delta))
            + math.cos(phi_b) * math.cos(_rad(delta)) * math.cos(_rad(omega)))


def position_soleil(d: date, heure_locale: float) -> dict:
    """Position du soleil à une heure locale décimale (ex. 12,5 = milieu de 12 h – 13 h)."""
    delta = declinaison(d)
    omega = angle_horaire(d, heure_locale)
    cz = cos_zenith(delta, omega)
    ci = cos_incidence(delta, omega)
    return {
        "declinaison": delta,
        "equation_du_temps": equation_du_temps(d),
        "angle_horaire": omega,
        "hauteur": math.degrees(math.asin(max(-1.0, min(1.0, cz)))),
        "zenith": math.degrees(math.acos(max(-1.0, min(1.0, cz)))),
        "incidence": math.degrees(math.acos(max(-1.0, min(1.0, ci)))),
        "cos_zenith": cz,
        "cos_incidence": ci,
    }


def irradiance_inclinee_isotrope(g: Optional[float], dif: Optional[float],
                                 d: date, heure_locale: float) -> float:
    """Irradiance sur le plan incliné (W/m²), modèle isotrope, SANS calage."""
    if g is None or g <= 0:
        return 0.0
    dif = min(max(dif or 0.0, 0.0), g)
    pos = position_soleil(d, heure_locale)
    beta = _rad(INCLINAISON)
    directe = 0.0
    if pos["hauteur"] >= HAUTEUR_MIN and pos["cos_incidence"] > 0:
        rb = min(RB_MAX, pos["cos_incidence"] / pos["cos_zenith"])
        directe = (g - dif) * rb
    return (directe + dif * (1 + math.cos(beta)) / 2
            + g * ALBEDO * (1 - math.cos(beta)) / 2)


def journee_claire(d: date) -> tuple[List[float], List[float]]:
    """Journée claire type : 24 heures (milieu d'heure) de globale horizontale
    (modèle de Haurwitz, 1098 × cos z × exp(−0,057 / cos z)) et de diffuse
    (PART_DIFFUSE_CIEL_CLAIR de la globale)."""
    g = []
    for h in range(24):
        cz = position_soleil(d, h + 0.5)["cos_zenith"]
        g.append(1098.0 * cz * math.exp(-0.057 / cz) if cz > 0 else 0.0)
    return g, [x * PART_DIFFUSE_CIEL_CLAIR for x in g]


@lru_cache(maxsize=12)
def rapport_modele(month: int) -> float:
    """Σ G_inc (modèle isotrope) ÷ Σ G sur la journée claire type du 15 du mois."""
    d = date(2026, month, 15)
    g, dif = journee_claire(d)
    inc = sum(irradiance_inclinee_isotrope(g[h], dif[h], d, h + 0.5) for h in range(24))
    return inc / sum(g)


def facteur_calage(month: int) -> float:
    """(GlobInc / GlobHor du mois, PVsyst) ÷ rapport du modèle isotrope."""
    return facteur_inclinaison(month) / rapport_modele(month)


def irradiance_inclinee_horaire(d: date, g: Sequence[Optional[float]],
                                dif: Sequence[Optional[float]]) -> List[float]:
    """Irradiance inclinée calée (W/m²) des 24 heures locales [h ; h+1[ du jour d,
    calculée au milieu de chaque heure. Jamais négative, nulle la nuit."""
    k = facteur_calage(d.month)
    return [max(0.0, irradiance_inclinee_isotrope(g[h], dif[h], d, h + 0.5) * k) for h in range(24)]
