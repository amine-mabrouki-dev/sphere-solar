"""Tests du contexte transmis au modèle de l'assistant (app.api.assistant).
Aucun appel réseau : Open-Meteo, l'heure et le modèle (Ollama) sont simulés ;
le modèle l'est par httpx.MockTransport, pour passer par le vrai client app.llm."""
import asyncio, json, logging, os, sqlite3, sys
from datetime import datetime, timedelta

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.prevision import MeteoDemain  # noqa: E402
from app.reference import energie_attendue  # noqa: E402
from test_performance import AUJ, TZ_TUNIS, _journee  # noqa: E402

CLE_TEST = "cle-ollama-de-test-0123456789"
IRR = 6.0                                         # kWh/m² chaque jour (Open-Meteo simulé)
H_DEMAIN = 5.4                                    # kWh/m² prévus pour demain (Open-Meteo simulé)
METEO_ACTUELLE = {"heure_locale": "2026-10-18T12:00", "temperature_air_C": 24.5,
                  "irradiance_horizontale_W_m2": 610.0, "irradiance_plan_modules_W_m2": 720.0}


@pytest.fixture
def assistant(monkeypatch):
    """Module app.api.assistant ; sys.modules est rétabli après le test (d'autres
    tests y remplacent app.db, app.auth et app.api.inverters par des modules simulés)."""
    sauvegarde = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    from app import llm
    from app.api import assistant as module
    globales_perf = module.calculer_performance.__globals__

    async def fausse_meteo(days):
        return globales_perf["MeteoSite"](irr={(AUJ - timedelta(days=k)).isoformat(): IRR
                                               for k in range(1, 9)})

    async def fausse_meteo_actuelle():
        return dict(METEO_ACTUELLE)

    async def fausse_meteo_demain(demain):
        return MeteoDemain(irradiation_kwh_m2=H_DEMAIN, couverture_nuageuse_pct=20)

    async def acces(inverter_id, user, db):
        return {"id": inverter_id}

    monkeypatch.setitem(globales_perf, "_meteo", fausse_meteo)
    monkeypatch.setitem(globales_perf, "_maintenant",
                        lambda: datetime(AUJ.year, AUJ.month, AUJ.day, 12, 0, tzinfo=TZ_TUNIS))
    monkeypatch.setattr(module, "_meteo_actuelle", fausse_meteo_actuelle)
    monkeypatch.setattr(module, "_check_access", acces)
    monkeypatch.setattr(module, "meteo_demain", fausse_meteo_demain)
    monkeypatch.setattr(llm, "OLLAMA_API_KEY", CLE_TEST)
    yield module
    for k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[k]
    sys.modules.update(sauvegarde)


def _base(tmp_path, r_jours=(), alertes=()):
    """Base minimale : installation, onduleur 1, dernière mesure, alertes ouvertes
    (code, message) et une journée complète par r de r_jours (la dernière la veille)."""
    db_path = tmp_path / "a.db"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE installations (id INTEGER PRIMARY KEY, location TEXT);
        CREATE TABLE inverters (id INTEGER PRIMARY KEY, installation_id INT, serial TEXT, model TEXT);
        CREATE TABLE latest_metrics (inverter_id INTEGER PRIMARY KEY, ts INT, pv_v REAL, pv_i REAL,
            pv_p REAL, pv2_v REAL, pv2_i REAL, ac_v REAL, ac_i REAL, freq REAL, e_day REAL,
            e_total REAL, temp REAL, alarm INT);
        CREATE TABLE alerts (id INTEGER PRIMARY KEY, inverter_id INT, code INT, message TEXT,
            raised_at INT, cleared_at INT);
        CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, pv_p REAL,
            e_day REAL, alarm INT);
        INSERT INTO installations VALUES (1, 'Metlaoui, Tunisie');
        INSERT INTO inverters VALUES (1, 1, 'SOLIS-TEST-01', 'Solis S5-GR3P12K');
    """)
    ts = int(datetime(AUJ.year, AUJ.month, AUJ.day, 11, 55, tzinfo=TZ_TUNIS).timestamp())
    con.execute("INSERT INTO latest_metrics VALUES (1, ?, 330, 12.1, 7900, 328, 12.0, 231, 11.4,"
                " 50.0, 21.3, 9500, 47.5, ?)", (ts, alertes[0][0] if alertes else 0))
    for code, message in alertes:
        con.execute("INSERT INTO alerts (inverter_id, code, message, raised_at) VALUES (1, ?, ?, ?)",
                    (code, message, ts - 3600))
    con.commit(); con.close()
    for k, r in enumerate(reversed(r_jours), start=1):
        d = AUJ - timedelta(days=k)
        _journee(db_path, d, energie_attendue(d, IRR)[0] * r)
    return db_path


async def _avec_db(db_path, fn):
    import aiosqlite
    db = await aiosqlite.connect(db_path); db.row_factory = aiosqlite.Row
    try:
        return await fn(db)
    finally:
        await db.close()


def _discussion(assistant, db_path, transport):
    """Appelle la route de l'assistant ; le modèle est simulé par `transport`."""
    from app.schemas import ChatRequest
    vrai_client = httpx.AsyncClient
    corps = ChatRequest(messages=[{"role": "user", "content": "Faut-il nettoyer les modules ?"}])
    mp = pytest.MonkeyPatch()
    mp.setattr(httpx, "AsyncClient", lambda **kw: vrai_client(transport=transport, **kw))
    try:
        return asyncio.run(_avec_db(db_path, lambda db: assistant.assistant_chat(
            1, corps, user={"id": 1, "role": "admin"}, db=db)))
    finally:
        mp.undo()


def _donnees_contexte(contenu_systeme: str) -> dict:
    """Le JSON du contexte, à la fin du message système."""
    return json.loads(contenu_systeme[contenu_systeme.index("{\n"):])


def test_contexte_contient_alerte_performance_alarmes_et_temperature_onduleur(tmp_path, assistant):
    db_path = _base(tmp_path, r_jours=(1.0, 0.98, 0.85, 0.84, 0.83),
                    alertes=[(301, "Défaut d'isolement - fuite à la terre détectée")])
    envoyes = []

    def modele(request):
        envoyes.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Oui."}})

    reponse = _discussion(assistant, db_path, httpx.MockTransport(modele))
    assert reponse.reply == "Oui."

    systeme = envoyes[0]["messages"][0]
    assert systeme["role"] == "system"
    texte = systeme["content"]
    # Consignes
    assert "10,8 kWc à Metlaoui" in texte and "r < 0,90 pendant 3 jours consécutifs" in texte
    assert "La température fournie est celle de l'onduleur" in texte

    ctx = _donnees_contexte(texte)
    comp = ctx["comparaison_reference_7_jours"]
    assert comp["disponible"] is True
    assert comp["alerte_performance"] is True
    assert comp["jours_sous_seuil"] == 3
    assert "perte de performance probable" in comp["message"]
    assert comp["perte_estimee_kWh"] > 0
    assert comp["donnees_demonstration"] is False
    assert "nettoyage_detecte" in comp and comp["methode"] == "journaliere"
    assert [j["etat"] for j in comp["jours_valides"]] == ["normal", "normal", "anomalie", "anomalie", "anomalie"]
    assert comp["jours_valides"][-1] == {**comp["jours_valides"][-1], "date": "17/10", "r": 0.83}

    assert ctx["alarmes_onduleur_ouvertes"][0]["code"] == 301
    assert ctx["alarmes_onduleur_ouvertes"][0]["message"] == "Défaut d'isolement - fuite à la terre détectée"
    assert ctx["mesures_actuelles"]["temperature_onduleur_C"] == 47.5
    assert ctx["mesures_actuelles"]["code_alarme_onduleur"] == 301
    assert '"temp"' not in texte
    assert ctx["meteo_actuelle_site"]["temperature_air_C"] == 24.5
    assert ctx["meteo_actuelle_site"]["irradiance_horizontale_W_m2"] == 610.0


def test_contexte_sans_alerte_ni_historique(tmp_path, assistant):
    """Sans journée enregistrée : comparaison indiquée indisponible, aucune alarme."""
    db_path = _base(tmp_path)
    ctx = asyncio.run(_avec_db(db_path, lambda db: assistant._build_context(db, 1)))
    donnees = assistant._context_data(ctx)
    assert donnees["comparaison_reference_7_jours"]["disponible"] is False
    assert donnees["alarmes_onduleur_ouvertes"] == []
    assert donnees["mesures_actuelles"]["message_alarme_onduleur"] is None


def test_code_alarme_inconnu_non_invente(tmp_path, assistant):
    db_path = _base(tmp_path, alertes=[(999, "Alarm code 999 - consulter le manuel")])
    ctx = asyncio.run(_avec_db(db_path, lambda db: assistant._build_context(db, 1)))
    alarme = assistant._context_data(ctx)["alarmes_onduleur_ouvertes"][0]
    assert alarme == {"code": 999, "depuis": alarme["depuis"],
                      "message": "Code d'alarme 999 non répertorié : consulter le manuel Solis"}


@pytest.mark.parametrize("statut", [200, 500])
def test_cle_jamais_dans_les_journaux(tmp_path, assistant, caplog, statut):
    """La clé part dans l'en-tête Authorization, mais n'apparaît ni dans les
    journaux (tous niveaux, httpx compris) ni dans l'erreur renvoyée."""
    from fastapi import HTTPException
    db_path = _base(tmp_path, r_jours=(1.0,))
    entetes = []

    def modele(request):
        entetes.append(request.headers["Authorization"])
        if statut != 200:
            return httpx.Response(statut, json={"error": "panne simulée"})
        return httpx.Response(200, json={"message": {"content": "Production conforme."}})

    caplog.set_level(logging.DEBUG)
    try:
        resultat = _discussion(assistant, db_path, httpx.MockTransport(modele)).reply
    except HTTPException as exc:
        resultat = str(exc.detail)
    assert entetes == [f"Bearer {CLE_TEST}"]
    assert caplog.records, "les journaux devraient contenir au moins la requête httpx"
    assert CLE_TEST not in caplog.text
    assert CLE_TEST not in resultat
