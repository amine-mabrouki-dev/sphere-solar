"""
Prévision de la production de demain, calculée par le serveur avec les mêmes
valeurs PVsyst que la comparaison à la référence (app.reference).

  E_att(demain) = Pc × H_hor prévu × (GlobInc / GlobHor du mois) × PR_ref du mois
  prévision     = E_att × performance actuelle

  - H_hor prévu : irradiation horizontale de demain prévue par Open-Meteo
    (shortwave_radiation_sum, MJ/m² ÷ 3,6) ;
  - performance actuelle : médiane de r sur les 7 derniers jours VALIDES
    (normal, vigilance, anomalie), bornée à [0,70 ; 1,05] ; moins de 3 jours
    valides : 1,0 (« performance non mesurée ») ;
  - fourchette selon la couverture nuageuse moyenne prévue (cloud_cover_mean) :
    ±10 % sous 30 %, ±20 % de 30 à 70 %, ±30 % au-delà, ±20 % si inconnue ;
  - Open-Meteo indisponible : E_att = moyenne PVsyst d'un jour du mois
    (E_Grid ÷ nombre de jours), « météo de demain indisponible ».
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Iterable, Optional

import httpx

from app.reference import energie_attendue

logger = logging.getLogger(__name__)

LAT, LON = 34.3264, 8.4050          # mêmes coordonnées que app.api.performance
OPEN_METEO_PREVISION_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&daily=shortwave_radiation_sum,cloud_cover_mean"
    "&timezone=Africa/Tunis&forecast_days=2"
)

ETATS_VALIDES = ("normal", "vigilance", "anomalie")
NB_JOURS_PERFORMANCE = 7       # médiane sur les 7 derniers jours valides
MIN_JOURS_VALIDES = 3          # en dessous : performance non mesurée (1,0)
PERF_MIN, PERF_MAX = 0.70, 1.05

SOURCE_OPEN_METEO = "Open-Meteo (prévision de demain)"
SOURCE_REPLI = "Moyenne PVsyst du mois (météo de demain indisponible)"
EXPLICATION_REPLI = ("Prévision calculée à partir de la météo prévue et de la "
                     "performance récente de l'installation.")


@dataclass
class MeteoDemain:
    """Prévision Open-Meteo pour demain (None si inconnue)."""
    irradiation_kwh_m2: Optional[float] = None
    couverture_nuageuse_pct: Optional[float] = None


async def meteo_demain(demain: date) -> MeteoDemain:
    """Irradiation horizontale (kWh/m²) et couverture nuageuse moyenne (%)
    prévues pour `demain`. MeteoDemain vide si Open-Meteo ne répond pas."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(OPEN_METEO_PREVISION_URL)
            resp.raise_for_status()
            daily = resp.json().get("daily", {})
    except Exception as exc:                       # réseau indisponible, quota, etc.
        logger.warning("Open-Meteo (prévision de demain) indisponible : %s", exc)
        return MeteoDemain()
    jours = daily.get("time", [])
    if demain.isoformat() not in jours:
        return MeteoDemain()
    i = jours.index(demain.isoformat())

    def valeur(cle: str) -> Optional[float]:
        serie = daily.get(cle) or []
        return serie[i] if i < len(serie) else None

    mj = valeur("shortwave_radiation_sum")
    return MeteoDemain(irradiation_kwh_m2=mj / 3.6 if mj is not None else None,
                       couverture_nuageuse_pct=valeur("cloud_cover_mean"))


def performance_actuelle(jours: Iterable[dict]) -> tuple[float, int, bool]:
    """(performance, nombre de jours valides retenus, mesurée ?) d'après les jours
    de la comparaison à la référence (dicts avec "r" et "etat", ordre chronologique)."""
    valides = [j["r"] for j in jours if j["etat"] in ETATS_VALIDES][-NB_JOURS_PERFORMANCE:]
    if len(valides) < MIN_JOURS_VALIDES:
        return 1.0, len(valides), False
    return min(PERF_MAX, max(PERF_MIN, median(valides))), len(valides), True


def marge_fourchette(couverture_pct: Optional[float]) -> float:
    """Demi-largeur relative de la fourchette selon la couverture nuageuse prévue."""
    if couverture_pct is None:
        return 0.20
    if couverture_pct < 30:
        return 0.10
    if couverture_pct <= 70:
        return 0.20
    return 0.30


def calculer_prevision(demain: date, meteo: MeteoDemain, jours: Iterable[dict]) -> dict:
    """Prévision de demain (sans l'explication rédigée)."""
    perf, nb_valides, mesuree = performance_actuelle(jours)
    h = meteo.irradiation_kwh_m2
    meteo_ok = h is not None and h > 0
    e_att, _ = energie_attendue(demain, h if meteo_ok else None)
    prevision = e_att * perf
    marge = marge_fourchette(meteo.couverture_nuageuse_pct if meteo_ok else None)

    remarques = []
    if not mesuree:
        remarques.append("performance non mesurée")
    if not meteo_ok:
        remarques.append("météo de demain indisponible")
    return {
        "date": demain.strftime("%d/%m"),
        "prevision_kwh": round(prevision, 1),
        "fourchette_min_kwh": round(prevision * (1 - marge), 1),
        "fourchette_max_kwh": round(prevision * (1 + marge), 1),
        "marge_pct": round(marge * 100),
        "energie_attendue_kwh": round(e_att, 1),
        "irradiation_prevue_kwh_m2": round(h, 2) if meteo_ok else None,
        "couverture_nuageuse_prevue_pct": (meteo.couverture_nuageuse_pct if meteo_ok else None),
        "performance_utilisee": round(perf, 3),
        "performance_mesuree": mesuree,
        "nb_jours_valides": nb_valides,
        "source_meteo": SOURCE_OPEN_METEO if meteo_ok else SOURCE_REPLI,
        "remarques": remarques,
    }
