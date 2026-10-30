"""Tests de la prévision de demain (app.prevision et route POST /forecast).
Aucun appel réseau : Open-Meteo et le modèle de langage sont simulés."""
import asyncio, json, os, sys
from datetime import date

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import prevision  # noqa: E402
from app.prevision import (  # noqa: E402
    EXPLICATION_REPLI, SOURCE_OPEN_METEO, SOURCE_REPLI, MeteoDemain, calculer_prevision,
    marge_fourchette, meteo_demain, performance_actuelle,
)
from test_assistant_contexte import (  # noqa: E402,F401  (assistant : fixture pytest)
    _avec_db, _base, _discussion, _donnees_contexte, assistant,
)

OCTOBRE = date(2026, 10, 20)


def _jours(*couples):
    return [{"r": r, "etat": etat} for r, etat in couples]


def _valides(*r):
    return _jours(*[(x, "anomalie" if x < 0.90 else "normal") for x in r])


# ── Calcul ────────────────────────────────────────────────────────────────────

def test_octobre_5_4_kwh_m2_performance_0_88():
    """10,8 × 5,4 × (170,2 / 131,2) × 0,880 = 66,6 kWh attendus ; × 0,88 ≈ 58,6 kWh."""
    p = calculer_prevision(OCTOBRE, MeteoDemain(5.4, 20), _valides(*[0.88] * 7))
    assert p["energie_attendue_kwh"] == 66.6
    assert p["prevision_kwh"] == 58.6
    assert p["performance_utilisee"] == 0.88 and p["performance_mesuree"] is True
    assert p["nb_jours_valides"] == 7
    assert (p["fourchette_min_kwh"], p["fourchette_max_kwh"]) == (52.7, 64.4)   # ±10 %
    assert p["date"] == "20/10" and p["irradiation_prevue_kwh_m2"] == 5.4
    assert p["source_meteo"] == SOURCE_OPEN_METEO and p["remarques"] == []


def test_jours_incoherents_incomplets_et_insuffisants_exclus_de_la_performance():
    jours = _jours((0.90, "vigilance"), (7.8, "incoherent"), (0.88, "anomalie"),
                   (0.10, "incomplete"), (0.86, "anomalie"), (0.30, "fonctionnement_insuffisant"))
    assert performance_actuelle(jours) == (0.88, 3, True)


def test_mediane_des_7_derniers_jours_valides_seulement():
    """Les jours valides plus anciens que les 7 derniers ne comptent pas."""
    jours = _valides(0.50, 0.50, 0.50, *[0.95] * 7)
    assert performance_actuelle(jours) == (0.95, 7, True)


def test_moins_de_3_jours_valides_performance_1_non_mesuree():
    jours = _jours((0.80, "anomalie"), (0.82, "anomalie"), (5.0, "incoherent"))
    assert performance_actuelle(jours) == (1.0, 2, False)
    p = calculer_prevision(OCTOBRE, MeteoDemain(5.4, 20), jours)
    assert p["performance_utilisee"] == 1.0 and p["prevision_kwh"] == 66.6
    assert "performance non mesurée" in p["remarques"]


@pytest.mark.parametrize("r, attendu", [(0.40, 0.70), (1.08, 1.05)])
def test_performance_bornee(r, attendu):
    assert performance_actuelle(_jours(*[(r, "normal")] * 3))[0] == attendu


@pytest.mark.parametrize("couverture, marge", [(0, 0.10), (29.9, 0.10), (30, 0.20), (70, 0.20),
                                               (70.1, 0.30), (100, 0.30), (None, 0.20)])
def test_fourchette_selon_couverture_nuageuse(couverture, marge):
    assert marge_fourchette(couverture) == marge


def test_open_meteo_indisponible_repli_sur_la_moyenne_pvsyst():
    """Octobre : E_Grid 1,618 MWh / 31 jours = 52,2 kWh ; × 0,88 = 45,9 kWh, ±20 %."""
    p = calculer_prevision(OCTOBRE, MeteoDemain(), _valides(*[0.88] * 5))
    assert p["energie_attendue_kwh"] == 52.2
    assert p["prevision_kwh"] == round(1618 / 31 * 0.88, 1)
    assert p["marge_pct"] == 20 and p["irradiation_prevue_kwh_m2"] is None
    assert p["source_meteo"] == SOURCE_REPLI
    assert "météo de demain indisponible" in p["remarques"]


# ── Open-Meteo (simulé) ───────────────────────────────────────────────────────

def _meteo_simulee(monkeypatch, gestionnaire):
    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(prevision.httpx, "AsyncClient",
                        lambda **kw: vrai_client(transport=httpx.MockTransport(gestionnaire), **kw))
    return asyncio.run(meteo_demain(OCTOBRE))


def test_meteo_demain_lit_irradiation_et_nuages(monkeypatch):
    def open_meteo(request):
        assert "shortwave_radiation_sum" in str(request.url) and "cloud_cover_mean" in str(request.url)
        return httpx.Response(200, json={"daily": {
            "time": ["2026-10-19", "2026-10-20"],
            "shortwave_radiation_sum": [15.0, 19.44],            # MJ/m²
            "cloud_cover_mean": [80, 45]}})
    m = _meteo_simulee(monkeypatch, open_meteo)
    assert round(m.irradiation_kwh_m2, 2) == 5.4 and m.couverture_nuageuse_pct == 45


def test_meteo_demain_sans_nuages_fournis(monkeypatch):
    m = _meteo_simulee(monkeypatch, lambda r: httpx.Response(200, json={"daily": {
        "time": ["2026-10-19", "2026-10-20"], "shortwave_radiation_sum": [15.0, 19.44]}}))
    assert m.couverture_nuageuse_pct is None
    assert calculer_prevision(OCTOBRE, m, [])["marge_pct"] == 20


@pytest.mark.parametrize("reponse", [lambda r: httpx.Response(503),
                                     lambda r: (_ for _ in ()).throw(httpx.ConnectError("hors ligne"))])
def test_meteo_demain_open_meteo_indisponible(monkeypatch, reponse):
    assert _meteo_simulee(monkeypatch, reponse) == MeteoDemain()


# ── Route POST /forecast (modèle simulé) ──────────────────────────────────────

def _forecast(assistant, db_path, modele=None):
    """Appelle la route ; `modele` simule le modèle de langage (None : non configuré)."""
    mp = pytest.MonkeyPatch()
    if modele is None:
        mp.setattr(assistant.llm, "OLLAMA_API_KEY", "")
    else:
        vrai_client = httpx.AsyncClient
        mp.setattr(httpx, "AsyncClient",
                   lambda **kw: vrai_client(transport=httpx.MockTransport(modele), **kw))
    try:
        return asyncio.run(_avec_db(db_path, lambda db: assistant.forecast_tomorrow(
            1, user={"id": 1, "role": "admin"}, db=db)))
    finally:
        mp.undo()


def test_route_forecast_explication_du_modele(tmp_path, assistant):
    """5 jours à r = 0,88 et 5,4 kWh/m² prévus (simulés) : 58,6 kWh pour le 19/10.
    Le modèle reçoit les chiffres et la consigne de n'en modifier aucun."""
    db_path = _base(tmp_path, r_jours=(0.88,) * 5)
    recus = []

    def modele(request):
        recus.append(json.loads(request.content)["messages"])
        return httpx.Response(200, json={"message": {"content": "Demain, environ 58,6 kWh."}})

    rep = _forecast(assistant, db_path, modele)
    assert rep.date == "19/10" and rep.prevision_kwh == 58.6
    assert (rep.fourchette_min_kwh, rep.fourchette_max_kwh) == (52.7, 64.4)
    assert rep.performance_utilisee == 0.88 and rep.nb_jours_valides == 5
    assert rep.irradiation_prevue_kwh_m2 == 5.4 and rep.energie_attendue_kwh == 66.6
    assert rep.explication == "Demain, environ 58,6 kWh."
    systeme, chiffres = recus[0]
    assert "Ne modifie aucun nombre" in systeme["content"] and "3 phrases au plus" in systeme["content"]
    assert json.loads(chiffres["content"]) == {
        "date": "19/10", "prevision": "58,6 kWh", "fourchette": "entre 53 et 64 kWh",
        "soleil_prevu": "5,4 kWh/m²", "performance_recente": "88 %", "jours_valides_utilises": 5,
        "source_meteo": SOURCE_OPEN_METEO, "nuages_prevus": "20 %"}


@pytest.mark.parametrize("modele", [None, lambda r: httpx.Response(500),
                                    lambda r: httpx.Response(200, json={"message": {"content": " "}})])
def test_route_forecast_phrase_fixe_si_le_modele_ne_repond_pas(tmp_path, assistant, modele):
    rep = _forecast(assistant, _base(tmp_path, r_jours=(0.88,) * 5), modele)
    assert rep.explication == EXPLICATION_REPLI
    assert rep.prevision_kwh == 58.6


def test_route_forecast_sans_historique(tmp_path, assistant):
    rep = _forecast(assistant, _base(tmp_path))
    assert rep.performance_mesuree is False and rep.performance_utilisee == 1.0
    assert rep.prevision_kwh == 66.6


# ── Assistant ─────────────────────────────────────────────────────────────────

def test_assistant_recoit_la_prevision_et_les_seuls_jours_valides(tmp_path, assistant):
    """Un jour incohérent (r = 1,30) n'est pas transmis ; dates JJ/MM ; la
    prévision du serveur est fournie telle quelle avec ses consignes."""
    db_path = _base(tmp_path, r_jours=(0.88, 0.88, 1.30, 0.88, 0.88))
    envoyes = []

    def modele(request):
        envoyes.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Environ 58,6 kWh."}})

    _discussion(assistant, db_path, httpx.MockTransport(modele))
    texte = envoyes[0]["messages"][0]["content"]
    assert "ne calcule pas toi-même de moyenne" in texte
    assert "La production de demain sera connue demain soir, après le coucher du soleil." in texte

    ctx = _donnees_contexte(texte)
    jours = ctx["comparaison_reference_7_jours"]["jours_valides"]
    assert [j["date"] for j in jours] == ["13/10", "14/10", "16/10", "17/10"]
    assert all(j["etat"] in ("normal", "vigilance", "anomalie") for j in jours)
    assert "production_journaliere_kWh" not in ctx
    assert ctx["prevision_demain"]["prevision_kwh"] == 58.6
    assert ctx["prevision_demain"]["date"] == "19/10"
