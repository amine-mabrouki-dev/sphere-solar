"""
LLM-powered features, grounded in the installation's real data:
  POST /inverters/{id}/forecast   -> tomorrow's expected production (kWh),
                                     computed by app.prevision; the LLM only words it
  POST /inverters/{id}/assistant  -> domain-locked monitoring chat

Both build their context from the database and refuse to answer outside the
solar-PV monitoring domain. The Ollama API key comes from env (see app/llm.py).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app import llm
from app.api import performance as perf_api
from app.api.inverters import _check_access
from app.api.performance import LAT, LON, TZ_SITE, calculer_performance
from app.mqtt_worker import ALARM_MESSAGES
from app.prevision import ETATS_VALIDES, EXPLICATION_REPLI, calculer_prevision, meteo_demain
from app.auth import get_current_user
from app.db import get_db
from app.schemas import ChatRequest, ChatResponse, ForecastResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inverters", tags=["assistant"])

# Roles a client is allowed to send (we always supply the system message).
_ALLOWED_ROLES = {"user", "assistant"}

INSTALLATION = (
    "Tu es l'assistant de supervision d'une installation photovoltaïque de 10,8 kWc "
    "à Metlaoui (Tunisie), 2 chaînes de 9 modules, onduleur Solis S5-GR3P12K."
)

# Consignes sur les données transmises
REGLES_DONNEES = """\
- N'invente jamais de code d'alarme ni de valeur : n'utilise que les données fournies. \
Si une information manque, dis-le.
- La température fournie est celle de l'onduleur, pas celle de l'air."""

DOMAIN_SYSTEM = f"""\
{INSTALLATION}

Tu n'aides que pour cette installation : mesures, production, alertes, \
performance et conseils d'exploitation ou d'entretien. Si la question sort de ce \
cadre, refuse poliment en une phrase et reviens à la supervision.

Consignes :
- Pour juger la production, utilise uniquement la comparaison à la référence \
fournie (production mesurée ÷ production attendue d'après PVsyst et l'irradiation \
du jour). La règle du système est : alerte de perte lente si r < 0,90 pendant \
3 jours consécutifs. N'invente pas d'autre règle.
- Il existe deux types d'alertes : les alarmes de l'onduleur (codes fournis) et \
l'alerte de performance (comparaison à la référence). Si l'une ou l'autre est \
active, dis-le.
{REGLES_DONNEES}
- Si donnees_demonstration est vrai, précise que l'historique de comparaison est \
un scénario de démonstration.
- Pour le nettoyage, recommande-le quand l'alerte de performance est active ou \
que r baisse régulièrement ; ne donne pas de fréquence générale de nettoyage.
- Pour la production de demain, donne la prévision fournie (prevision_demain) \
telle quelle, avec sa fourchette ; ne calcule pas toi-même de moyenne.
- La production de demain sera connue demain soir, après le coucher du soleil.
- Réponds en français, en phrases courtes, en 150 mots au plus.
"""

EXPLICATION_SYSTEM = """\
Tu rédiges l'explication d'une prévision de production photovoltaïque pour \
l'utilisateur, en français, en 3 phrases au plus, à partir de ces chiffres \
uniquement. Ne modifie aucun nombre, n'en ajoute aucun et ne refais aucun calcul. \
Si une remarque est fournie (performance non mesurée, météo de demain \
indisponible), mentionne-la. Réponds par le texte seul, sans titre ni liste.
"""


# Conditions actuelles du site (mêmes coordonnées et même source que la carte
# météo de l'application, mobile/src/weather.ts)
OPEN_METEO_ACTUEL_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&current=temperature_2m,shortwave_radiation,global_tilted_irradiance"
    "&tilt=30&azimuth=0&timezone=Africa/Tunis"
)

# Nombre de jours de la comparaison à la référence transmise au modèle
JOURS_COMPARAISON = 7


async def _meteo_actuelle() -> Optional[dict]:
    """Température de l'air et irradiance actuelles (Open-Meteo), ou None si
    Open-Meteo ne répond pas (remplacée dans les tests)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(OPEN_METEO_ACTUEL_URL)
            resp.raise_for_status()
            cur = resp.json().get("current") or {}
    except Exception as exc:
        logger.warning("Open-Meteo (météo actuelle) indisponible : %s", exc)
        return None
    heure = cur.get("time")                       # « 2026-10-19T20:00 », heure locale
    return {
        "heure_locale": (datetime.fromisoformat(heure).strftime("%d/%m %H:%M")
                         if heure else None),
        "temperature_air_C": cur.get("temperature_2m"),
        "irradiance_horizontale_W_m2": cur.get("shortwave_radiation"),
        "irradiance_plan_modules_W_m2": cur.get("global_tilted_irradiance"),
    }


def _message_alarme(code: Optional[int]) -> Optional[str]:
    """Message français d'un code d'alarme Solis (None si pas d'alarme)."""
    if not code:
        return None
    return ALARM_MESSAGES.get(code, f"Code d'alarme {code} non répertorié : consulter le manuel Solis")


def _heure_locale(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, TZ_SITE).strftime("%d/%m %H:%M")


def _jj_mm(date_iso: Optional[str]) -> Optional[str]:
    """« 2026-10-19 » → « 19/10 »."""
    return f"{date_iso[8:10]}/{date_iso[5:7]}" if date_iso else None


async def _comparaison_reference(db, inverter_id: int) -> dict:
    """Comparaison à la référence des 7 derniers jours, calculée par la même
    fonction que la route /inverters/{id}/performance. Seules les journées
    valides sont transmises (les autres ne jugent pas la performance)."""
    try:
        perf = await calculer_performance(db, inverter_id, days=JOURS_COMPARAISON, mode="auto")
    except HTTPException as exc:
        return {"disponible": False, "raison": str(exc.detail)}
    except Exception as exc:
        logger.warning("Comparaison à la référence indisponible : %s", exc)
        return {"disponible": False, "raison": "calcul impossible pour le moment"}
    return {
        "disponible": True,
        "regle_alerte": (f"alerte de perte lente si r < {perf['seuil_r']:.2f}".replace(".", ",")
                         + f" pendant "
                         f"{perf['jours_consecutifs_requis']} jours consécutifs"),
        "methode": perf.get("mode"),
        "alerte_performance": perf["alerte_performance"],
        "message": perf["message"],
        "jours_sous_seuil": perf["jours_sous_seuil"],
        "perte_estimee_kWh": perf["perte_estimee_kwh"],
        "nettoyage_detecte": _jj_mm(perf["nettoyage_detecte"]),
        "donnees_demonstration": perf["donnees_demonstration"],
        "jours_valides": [
            {"date": _jj_mm(j["date"]), "r": j["r"], "etat": j["etat"], "methode": j["methode"],
             "energie_mesuree_kWh": j["energie_mesuree_kwh"],
             "energie_attendue_kWh": j["energie_attendue_kwh"]}
            for j in perf["jours"] if j["etat"] in ETATS_VALIDES
        ],
    }


async def _prevision_ou_absence(db, inverter_id: int):
    try:
        return await _prevision_demain(db, inverter_id)
    except Exception as exc:
        logger.warning("Prévision de demain indisponible : %s", exc)
        return "indisponible"


async def _build_context(db, inverter_id: int) -> dict:
    """Gather a compact snapshot of the inverter for the LLM."""
    async with db.execute(
        """SELECT inv.serial, inv.model, inst.location
           FROM inverters inv JOIN installations inst ON inst.id = inv.installation_id
           WHERE inv.id = ?""",
        (inverter_id,),
    ) as cur:
        meta = await cur.fetchone()

    async with db.execute(
        "SELECT * FROM latest_metrics WHERE inverter_id = ?", (inverter_id,)
    ) as cur:
        latest = await cur.fetchone()

    async with db.execute(
        """SELECT code, message, raised_at FROM alerts
           WHERE inverter_id = ? AND cleared_at IS NULL ORDER BY raised_at DESC""",
        (inverter_id,),
    ) as cur:
        open_alerts = [dict(r) for r in await cur.fetchall()]

    return {
        "meta": dict(meta) if meta else {},
        "latest": dict(latest) if latest else {},
        "open_alerts": open_alerts,
        "comparaison_reference": await _comparaison_reference(db, inverter_id),
        "meteo_actuelle": await _meteo_actuelle(),
        "prevision_demain": await _prevision_ou_absence(db, inverter_id),
    }


def _context_data(ctx: dict) -> dict:
    """Contexte transmis au modèle, chaque grandeur nommée avec son unité."""
    meta   = ctx["meta"]
    latest = ctx["latest"]
    # Le nom de l'installation (nom du client) n'est pas transmis au modèle :
    # l'assistant ne peut donc pas l'afficher.
    data: dict = {
        "site": f"Metlaoui ({meta.get('location')})",
        "onduleur": {"modele": meta.get("model"), "numero_serie": meta.get("serial")},
    }
    if latest:
        data["mesures_actuelles"] = {
            "heure_locale": _heure_locale(latest.get("ts")),
            "puissance_pv_W": latest.get("pv_p"),
            "chaine_1_tension_V": latest.get("pv_v"),
            "chaine_1_courant_A": latest.get("pv_i"),
            "chaine_2_tension_V": latest.get("pv2_v"),
            "chaine_2_courant_A": latest.get("pv2_i"),
            "reseau_tension_V": latest.get("ac_v"),
            "reseau_courant_A": latest.get("ac_i"),
            "reseau_frequence_Hz": latest.get("freq"),
            "temperature_onduleur_C": latest.get("temp"),
            "energie_jour_kWh": latest.get("e_day"),
            "energie_totale_kWh": latest.get("e_total"),
            "code_alarme_onduleur": latest.get("alarm") or 0,
            "message_alarme_onduleur": _message_alarme(latest.get("alarm")),
        }
    else:
        data["mesures_actuelles"] = "aucune mesure reçue"
    data["comparaison_reference_7_jours"] = ctx["comparaison_reference"]
    data["prevision_demain"] = ctx["prevision_demain"]
    data["alarmes_onduleur_ouvertes"] = [
        {"code": a["code"], "message": _message_alarme(a["code"]),
         "depuis": _heure_locale(a["raised_at"])}
        for a in ctx["open_alerts"]
    ]
    data["meteo_actuelle_site"] = ctx["meteo_actuelle"] or "indisponible"
    return data


def _context_text(ctx: dict) -> str:
    return ("CONTEXTE — données de l'installation (JSON) :\n"
            + json.dumps(_context_data(ctx), ensure_ascii=False, indent=1))


async def _prevision_demain(db, inverter_id: int) -> dict:
    """Prévision de demain calculée par le serveur (app.prevision), d'après la
    comparaison à la référence des 14 derniers jours (dont les 7 derniers jours
    valides donnent la performance) et la météo prévue."""
    demain = perf_api._maintenant().date() + timedelta(days=1)
    try:
        jours = (await calculer_performance(db, inverter_id, days=14, mode="auto"))["jours"]
    except HTTPException:                          # aucune journée enregistrée
        jours = []
    return calculer_prevision(demain, await meteo_demain(demain), jours)


def _fr(x: float, decimales: int = 1) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def _chiffres_explication(p: dict) -> dict:
    """Chiffres de la prévision déjà écrits comme sur la carte de l'application
    (virgule décimale, performance en %) : le modèle les recopie sans les convertir."""
    chiffres = {
        "date": p["date"],
        "prevision": f"{_fr(p['prevision_kwh'])} kWh",
        "fourchette": (f"entre {round(p['fourchette_min_kwh'])} et "
                       f"{round(p['fourchette_max_kwh'])} kWh"),
        "soleil_prevu": (f"{_fr(p['irradiation_prevue_kwh_m2'])} kWh/m²"
                         if p["irradiation_prevue_kwh_m2"] is not None else "indisponible"),
        "performance_recente": (f"{round(p['performance_utilisee'] * 100)} %"
                                if p["performance_mesuree"] else "non mesurée"),
        "jours_valides_utilises": p["nb_jours_valides"],
        "source_meteo": p["source_meteo"],
    }
    if p["couverture_nuageuse_prevue_pct"] is not None:
        chiffres["nuages_prevus"] = f"{round(p['couverture_nuageuse_prevue_pct'])} %"
    if p["remarques"]:
        chiffres["remarques"] = p["remarques"]
    return chiffres


async def _expliquer_prevision(prevision: dict) -> str:
    """Explication rédigée par le modèle à partir des seuls chiffres de la
    prévision ; phrase fixe si le modèle n'est pas configuré ou ne répond pas."""
    if not llm.is_configured():
        return EXPLICATION_REPLI
    messages = [
        {"role": "system", "content": EXPLICATION_SYSTEM},
        {"role": "user", "content": json.dumps(_chiffres_explication(prevision), ensure_ascii=False)},
    ]
    try:
        texte = (await llm.chat(messages, temperature=0.2)).strip()
    except Exception as e:
        logger.warning("Explication de la prévision indisponible : %s", e)
        return EXPLICATION_REPLI
    return texte or EXPLICATION_REPLI


@router.post("/{inverter_id}/forecast", response_model=ForecastResponse)
async def forecast_tomorrow(
    inverter_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    prevision = await _prevision_demain(db, inverter_id)
    return ForecastResponse(**prevision, explication=await _expliquer_prevision(prevision))


@router.post("/{inverter_id}/assistant", response_model=ChatResponse)
async def assistant_chat(
    inverter_id: int,
    body: ChatRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    if not llm.is_configured():
        raise HTTPException(503, "Assistant unavailable: OLLAMA_API_KEY is not configured")

    # Keep only valid client turns, cap history to bound the prompt.
    history = [
        {"role": m.role, "content": m.content}
        for m in body.messages
        if m.role in _ALLOWED_ROLES and m.content.strip()
    ][-12:]
    if not history or history[-1]["role"] != "user":
        raise HTTPException(400, "messages must end with a user turn")

    ctx = await _build_context(db, inverter_id)
    messages = [
        {"role": "system", "content": DOMAIN_SYSTEM + "\n\n" + _context_text(ctx)},
        *history,
    ]

    try:
        reply = await llm.chat(messages, temperature=0.4)
    except httpx.HTTPStatusError as e:
        logger.warning("Ollama error: %s", e)
        raise HTTPException(502, f"LLM provider error: {e.response.status_code}")
    except Exception as e:
        logger.exception("Assistant failed")
        raise HTTPException(502, f"Assistant failed: {e}")

    return ChatResponse(reply=reply.strip())
