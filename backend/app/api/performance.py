"""
Comparaison de la production mesurée à la production de référence (PVsyst).

  GET /inverters/{id}/performance?days=14&mode=auto
      mode = auto       : irradiation Open-Meteo si disponible, sinon référence mensuelle
             irradiance : irradiation Open-Meteo obligatoire
             mensuel    : référence moyenne PVsyst du mois (sans météo)

Toutes les dates sont en heure LOCALE du site (Africa/Tunis, UTC+1, sans heure
d'été) ; les mesures sont regroupées par jour local, comme l'irradiation
Open-Meteo (timezone=Africa/Tunis).

Journée d'aujourd'hui : elle n'est comparée qu'une fois la production terminée,
c'est-à-dire après le coucher du soleil + 30 min (coucher fourni par Open-Meteo
dans le même appel que l'irradiation ; repli à 19:00 si Open-Meteo ne répond
pas). Elle porte alors "jour_courant": true. Avant cette heure, elle n'est pas
dans la liste et l'objet "aujourdhui" donne l'énergie en cours et l'heure à
partir de laquelle elle sera comparée.

Journées incomplètes : un jour n'est comparé que si ses mesures couvrent la
période ensoleillée (lever → coucher du soleil, Open-Meteo ; repli 07:00 –
18:00) sans absence de plus de 30 min et sur au moins 80 % de sa durée
(app.reference.couverture_mesures). Sinon il porte l'état "incomplete" et est
exclu de la perte estimée, des jours sous le seuil et du nettoyage.

Méthode HORAIRE (réponse "mode": "horaire") : si Open-Meteo fournit l'irradiance
horaire (hourly=shortwave_radiation), chaque heure locale est analysée à partir
de readings (nombre de mesures, énergie, puissance moyenne) et classée par
app.performance_horaire.etat_heure. La performance r(j) ne porte que sur les heures de
fonctionnement ; la disponibilité, les heures d'arrêt et l'énergie perdue à
l'arrêt sont données à part. Les heures sans mesures n'influencent pas r : le
contrôle de complétude ci-dessus ne s'applique donc qu'à la méthode journalière.
Sans données horaires : méthode journalière, "mode": "journalier".
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.inverters import _check_access
from app.auth import get_current_user
from app.db import get_db
from app.performance_horaire import (
    HeureMesuree, appliquer_vraisemblance, bilan_journalier, choisir_methode, diffuse_horaire,
    irradiance_horaire,
    mesures_attendues_par_heure,
)
from app.plan_incline import irradiance_inclinee_horaire
from app.reference import JourPerformance, couverture_mesures, jour_journalier, synthese

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inverters", tags=["performance"])

# Fuseau du site. Sous Windows, zoneinfo exige le paquet tzdata ; à défaut, on
# utilise UTC+1 fixe (exact : la Tunisie n'applique pas l'heure d'été).
try:
    TZ_SITE = ZoneInfo("Africa/Tunis")
except ZoneInfoNotFoundError:
    TZ_SITE = timezone(timedelta(hours=1), "Africa/Tunis")


def _expr_jour_local() -> str:
    """Expression SQLite donnant la date LOCALE (Africa/Tunis) d'une mesure :
    une mesure à 23:30 UTC appartient au jour local suivant (00:30 à Tunis)."""
    decalage_s = int(datetime.now(TZ_SITE).utcoffset().total_seconds())
    return f"date(ts, 'unixepoch', '{decalage_s:+d} seconds')"


def _minuit_local_ts(d: date) -> int:
    """Timestamp Unix du minuit local (Africa/Tunis) du jour d."""
    return int(datetime.combine(d, time(0), tzinfo=TZ_SITE).timestamp())

# Coordonnées du site (identiques à celles du widget météo de l'application)
LAT, LON = 34.3264, 8.4050
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&daily=shortwave_radiation_sum,sunrise,sunset&hourly=shortwave_radiation,diffuse_radiation"
    "&timezone=Africa/Tunis"
)

COUCHER_REPLI = time(19, 0)              # si Open-Meteo ne répond pas
MARGE_APRES_COUCHER = timedelta(minutes=30)
# Période ensoleillée de repli pour le contrôle de complétude des mesures
LEVER_REPLI_COMPLETUDE = time(7, 0)
COUCHER_REPLI_COMPLETUDE = time(18, 0)


@dataclass
class MeteoSite:
    """Données Open-Meteo du site (dictionnaires indexés par date locale ISO)."""
    irr: Dict[str, float] = field(default_factory=dict)          # kWh/m² par jour
    couchers: Dict[str, time] = field(default_factory=dict)
    levers: Dict[str, time] = field(default_factory=dict)
    # irradiance horizontale moyenne (W/m²) des 24 heures locales [h ; h+1[ :
    # globale (horaire) et diffuse
    horaire: Dict[str, List[Optional[float]]] = field(default_factory=dict)
    diffuse: Dict[str, List[Optional[float]]] = field(default_factory=dict)


def _maintenant() -> datetime:
    """Heure locale actuelle du site (remplacée dans les tests)."""
    return datetime.now(TZ_SITE)


async def _meteo(days: int) -> MeteoSite:
    """Un seul appel Open-Meteo pour les `days` derniers jours et aujourd'hui :
      - irradiation horizontale journalière (kWh/m²) ; shortwave_radiation_sum
        est en MJ/m² (1 kWh = 3,6 MJ) ;
      - heures locales du coucher et du lever du soleil ;
      - irradiance horizontale horaire, globale et diffuse (W/m²).
    Retourne un MeteoSite vide si Open-Meteo est indisponible."""
    url = f"{OPEN_METEO_URL}&past_days={min(days + 1, 92)}&forecast_days=1"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            donnees = resp.json()
    except Exception as exc:                       # réseau indisponible, quota, etc.
        logger.warning("Open-Meteo indisponible : %s", exc)
        return MeteoSite()
    daily = donnees.get("daily", {})
    irr: Dict[str, float] = {}
    for d, mj in zip(daily.get("time", []), daily.get("shortwave_radiation_sum", [])):
        if mj is not None:
            irr[d] = mj / 3.6
    return MeteoSite(irr=irr, couchers=_heures(daily, "sunset"), levers=_heures(daily, "sunrise"),
                     horaire=irradiance_horaire(donnees.get("hourly", {})),
                     diffuse=diffuse_horaire(donnees.get("hourly", {})))


def _heures(daily: dict, cle: str) -> Dict[str, time]:
    """Heures locales d'une série journalière Open-Meteo (« 2026-10-18T17:48 »)."""
    heures: Dict[str, time] = {}
    for d, s in zip(daily.get("time", []), daily.get(cle, [])):
        if s:
            try:
                heures[d] = datetime.fromisoformat(s).time()
            except ValueError:
                pass
    return heures


def fin_de_production(jour: date, couchers: Dict[str, time]) -> datetime:
    """Heure locale à partir de laquelle la journée est terminée :
    coucher du soleil + 30 min (coucher de repli : 19:00)."""
    coucher = couchers.get(jour.isoformat(), COUCHER_REPLI)
    return datetime.combine(jour, coucher, tzinfo=TZ_SITE) + MARGE_APRES_COUCHER


def periode_ensoleillee(jour: date, levers: Dict[str, time],
                        couchers: Dict[str, time]) -> Tuple[int, int]:
    """Timestamps Unix du lever et du coucher du soleil du jour (repli 07:00 – 18:00)."""
    lever = levers.get(jour.isoformat(), LEVER_REPLI_COMPLETUDE)
    coucher = couchers.get(jour.isoformat(), COUCHER_REPLI_COMPLETUDE)
    return (int(datetime.combine(jour, lever, tzinfo=TZ_SITE).timestamp()),
            int(datetime.combine(jour, coucher, tzinfo=TZ_SITE).timestamp()))


async def _mesures_completes(db, inverter_id: int, jour: date,
                             levers: Dict[str, time], couchers: Dict[str, time]) -> bool:
    """True si les mesures du jour couvrent la période ensoleillée (voir
    app.reference.couverture_mesures). Les mesures sont ramenées à la minute
    (au plus ~720 valeurs par jour, quelle que soit la cadence d'envoi)."""
    debut, fin = periode_ensoleillee(jour, levers, couchers)
    async with db.execute(
        "SELECT DISTINCT ts / 60 * 60 FROM readings WHERE inverter_id = ? AND ts >= ? AND ts <= ?",
        (inverter_id, debut, fin),
    ) as cur:
        minutes = [r[0] for r in await cur.fetchall()]
    return couverture_mesures(minutes, debut, fin)[0]


@dataclass
class _Heure:
    """Agrégats SQL d'une heure locale de readings."""
    nb: int
    p_moy: Optional[float]      # moyenne de pv_p (W)
    e_max: Optional[float]      # plus grande valeur de e_day (kWh)
    ts_max: int                 # dernière mesure de l'heure


async def _heures_mesurees(db, inverter_id: int, start_ts: int, end_ts: int) -> Dict[int, _Heure]:
    """Agrégats par heure locale, indexés par le rang de l'heure depuis start_ts
    (minuit local ; la Tunisie n'a pas d'heure d'été, chaque jour a 24 heures)."""
    async with db.execute(
        """SELECT (ts - ?) / 3600 AS k, COUNT(*), AVG(pv_p), MAX(e_day), MAX(ts)
           FROM readings WHERE inverter_id = ? AND ts >= ? AND ts < ?
           GROUP BY k""",
        (start_ts, inverter_id, start_ts, end_ts),
    ) as cur:
        return {k: _Heure(nb, p, e, t) for k, nb, p, e, t in await cur.fetchall()}


def energie_heure(h: Optional[_Heure], prec: Optional[_Heure], debut_ts: int,
                  tolerance_s: float) -> Tuple[Optional[float], Optional[float]]:
    """(énergie kWh, puissance moyenne W) d'une heure commençant à debut_ts.

    Énergie = e_day en fin d'heure − e_day en fin de l'heure précédente, si les
    deux heures ont une mesure à moins de `tolerance_s` de leur fin (sinon
    l'écart couvrirait aussi des heures sans mesures). À défaut, ou si e_day a
    été remis à zéro, intégration de pv_p : puissance moyenne × 1 h.
    Puissance moyenne = moyenne de pv_p, ou à défaut énergie ÷ 1 h."""
    if h is None:
        return None, None
    energie = None
    if (h.e_max is not None and prec is not None and prec.e_max is not None
            and prec.ts_max >= debut_ts - tolerance_s
            and h.ts_max >= debut_ts + 3600 - tolerance_s
            and h.e_max >= prec.e_max):
        energie = h.e_max - prec.e_max
    if energie is None and h.p_moy is not None:
        energie = h.p_moy / 1000.0
    p_moy = h.p_moy if h.p_moy is not None else (energie * 1000.0 if energie is not None else None)
    return energie, p_moy


def heures_du_jour(d: date, start: date, mesures: Dict[int, _Heure],
                   g_horaire: List[Optional[float]], debut_jour_ts: int,
                   d_horaire: Optional[List[Optional[float]]] = None) -> List[HeureMesuree]:
    """Les 24 heures locales du jour d, prêtes pour app.performance_horaire.bilan_journalier.
    Avec la diffuse horaire (d_horaire), l'irradiance est ramenée heure par heure
    au plan des modules (app.plan_incline)."""
    g_inc = irradiance_inclinee_horaire(d, g_horaire, d_horaire) if d_horaire else [None] * 24
    k0 = (d - start).days * 24
    attendues = mesures_attendues_par_heure(
        mesures[k].nb for k in range(k0, k0 + 24) if k in mesures)
    # Tolérance sur la dernière mesure d'une heure : deux périodes d'envoi, au moins 2 min
    tolerance = max(120.0, 2 * 3600.0 / attendues) if attendues else 120.0
    heures = []
    for i in range(24):
        h = mesures.get(k0 + i)
        energie, p_moy = energie_heure(h, mesures.get(k0 + i - 1), debut_jour_ts + 3600 * i, tolerance)
        heures.append(HeureMesuree(g_wm2=g_horaire[i], nb_mesures=h.nb if h else 0,
                                   energie_kwh=energie, puissance_moy_w=p_moy, g_inc_wm2=g_inc[i]))
    return heures


async def jours_compares(db, inverter_id: int, start: date, end_ts: int,
                         meteo: MeteoSite) -> List[JourPerformance]:
    """Comparaison à la référence, jour par jour, des jours locaux enregistrés
    entre minuit local du jour `start` et `end_ts` (exclu), ordre chronologique.
    Utilisée par la route /performance et par les rapports (app.report), pour
    que les énergies attendues soient calculées de la même façon. Sans
    irradiation (meteo.irr vide) : référence mensuelle PVsyst."""
    irr, couchers, levers, horaire = meteo.irr, meteo.couchers, meteo.levers, meteo.horaire
    start_ts = _minuit_local_ts(start)
    # Regroupement des mesures par date locale dans SQLite
    jour_local = _expr_jour_local()

    # Énergie du jour : valeur MAX de e_day sur le jour local. e_day ne fait que
    # croître dans la journée, le max est donc sa dernière valeur ; il résiste
    # en plus à une remise à zéro (redémarrage de l'ESP32 / du simulateur) qui
    # ferait tomber la dernière valeur brute à 0 kWh.
    sql = f"""
        SELECT {jour_local} AS d, MAX(e_day)
        FROM readings
        WHERE inverter_id = ? AND e_day IS NOT NULL AND ts >= ? AND ts < ?
        GROUP BY d
        ORDER BY d
    """
    async with db.execute(sql, (inverter_id, start_ts, end_ts)) as cur:
        rows = await cur.fetchall()

    # Méthode combinée (app.performance_horaire.choisir_methode) pour les jours
    # dont Open-Meteo fournit l'irradiance horaire : bilan horaire, puis méthode
    # journalière si le jour n'a ni arrêt ni mesures manquantes, horaire sinon.
    # Sans irradiance horaire : méthode journalière avec contrôle de complétude.
    mesures = await _heures_mesurees(db, inverter_id, start_ts, end_ts) if horaire and rows else {}
    detail: List[JourPerformance] = []
    for d_str, e_day in rows:
        d = date.fromisoformat(d_str)
        if d_str in horaire:
            heures = heures_du_jour(d, start, mesures, horaire[d_str], _minuit_local_ts(d),
                                    meteo.diffuse.get(d_str))
            jour = choisir_methode(bilan_journalier(d, heures), float(e_day), irr.get(d_str))
            # Une heure à l'énergie invraisemblable rend le jour « à vérifier »
            detail.append(appliquer_vraisemblance(jour, heures))
        else:
            complet = await _mesures_completes(db, inverter_id, d, levers, couchers)
            detail.append(jour_journalier(d, float(e_day), irr.get(d_str), complet))
    return detail


@router.get("/{inverter_id}/performance")
async def get_performance(
    inverter_id: int,
    days: int = Query(14, ge=1, le=60),
    mode: str = Query("auto", pattern="^(auto|irradiance|mensuel)$"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    return await calculer_performance(db, inverter_id, days, mode)


async def calculer_performance(db, inverter_id: int, days: int = 14, mode: str = "auto") -> dict:
    """Comparaison à la référence des `days` derniers jours (réponse de la route
    /performance). Aussi utilisée par l'assistant (app.api.assistant), pour qu'il
    juge la production exactement comme l'application. Lève HTTPException 422
    s'il n'y a encore aucune journée enregistrée."""
    # Météo (irradiation journalière et horaire, lever et coucher du soleil) : un
    # seul appel, utile dans tous les modes (le coucher décide si la journée
    # d'aujourd'hui est terminée).
    meteo = await _meteo(days)
    irr, couchers, levers, horaire = meteo.irr, meteo.couchers, meteo.levers, meteo.horaire
    if mode == "irradiance" and not irr:
        raise HTTPException(502, "Irradiation Open-Meteo indisponible")
    if mode == "mensuel":
        irr, horaire = {}, {}

    # Dates locales du site. Aujourd'hui n'est comparé qu'après le coucher + 30 min.
    maintenant = _maintenant()
    today = maintenant.date()
    fin_prod = fin_de_production(today, couchers)
    termine = maintenant > fin_prod
    start = today - timedelta(days=days)
    start_ts = _minuit_local_ts(start)
    end_ts = _minuit_local_ts(today + timedelta(days=1)) if termine else _minuit_local_ts(today)
    detail =await jours_compares(db, inverter_id, start, end_ts,
                                  MeteoSite(irr=irr, couchers=couchers, levers=levers,
                                            horaire=horaire, diffuse=meteo.diffuse))
    if not detail:
        raise HTTPException(422, "Pas encore de journée complète enregistrée pour cet onduleur")

    # Mêmes règles pour tous les jours, aujourd'hui compris (incohérent, incomplet,
    # fonctionnement insuffisant, alerte, nettoyage).
    result = synthese(detail)
    result["mode"] = "combinee" if horaire else "journaliere"
    for j in result["jours"]:
        j["jour_courant"] = j["date"] == today.isoformat()

    # Énergie produite aujourd'hui (depuis minuit local)
    async with db.execute(
        "SELECT MAX(e_day) FROM readings WHERE inverter_id = ? AND e_day IS NOT NULL "
        "AND ts >= ? AND ts < ?",
        (inverter_id, _minuit_local_ts(today), _minuit_local_ts(today + timedelta(days=1))),
    ) as cur:
        e_auj = (await cur.fetchone())[0]
    result["aujourdhui"] = {
        "energie_kwh": round(float(e_auj), 2) if e_auj is not None else None,
        "termine": termine,
        "comparaison_a_partir_de": fin_prod.strftime("%H:%M"),
    }

    result["inverter_id"] = inverter_id
    result["mode_demande"] = mode
    result["donnees_demonstration"] = await _periode_demo(db, inverter_id, start_ts, end_ts)
    return result


async def _periode_demo(db, inverter_id: int, start_ts: int, end_ts: int) -> bool:
    """True si au moins un jour de la période provient du scénario de démonstration
    (table demo_readings). False si la table n'existe pas."""
    try:
        async with db.execute(
            "SELECT 1 FROM demo_readings WHERE inverter_id = ? AND ts >= ? AND ts < ? LIMIT 1",
            (inverter_id, start_ts, end_ts),
        ) as cur:
            return await cur.fetchone() is not None
    except Exception:            # table absente (aucune donnée de démo insérée)
        return False
