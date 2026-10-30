"""Tests des données des rapports (app.report) : période comparable, jours
valides, alertes. Aucun appel réseau : Open-Meteo et l'heure sont simulés
(« aujourd'hui » = 18/10/2026 à midi, comme dans test_performance)."""
import asyncio, os, sqlite3, sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.reference import JourPerformance, energie_attendue  # noqa: E402
from test_performance import AUJ, TZ_TUNIS, _journee, _ts_local  # noqa: E402

IRR = 6.0                                    # kWh/m² chaque jour (Open-Meteo simulé)


@pytest.fixture
def rapport(monkeypatch):
    """Module app.report, météo et heure simulées ; sys.modules rétabli ensuite
    (d'autres tests y remplacent app.db, app.auth et app.api.inverters)."""
    sauvegarde = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    # import_module passe par sys.modules (« from app import report » pourrait
    # renvoyer le module d'un test précédent, resté en attribut du paquet app)
    import importlib
    report = importlib.import_module("app.report")
    perf = report.perf

    async def fausse_meteo(days):
        return perf.MeteoSite(irr={(AUJ - timedelta(days=k)).isoformat(): IRR for k in range(1, 60)})

    monkeypatch.setattr(perf, "_meteo", fausse_meteo)
    monkeypatch.setattr(perf, "_maintenant", lambda: datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS))
    yield report
    for k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[k]
    sys.modules.update(sauvegarde)


def _base(tmp_path, jours=(), alarmes=()):
    """Installation 1, onduleur 1. jours : (date, r[, trou]) — journée complète
    mesurée toutes les 5 min telle que r = r ; trou = (h1, h2) sans mesures.
    alarmes : dates (datetime locales) d'alarmes onduleur."""
    db_path = tmp_path / "r.db"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE installations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, owner_user_id INT);
        CREATE TABLE inverters (id INTEGER PRIMARY KEY, installation_id INT, serial TEXT, model TEXT);
        CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, pv_p REAL,
            e_day REAL, temp REAL, alarm INT);
        CREATE TABLE alerts (id INTEGER PRIMARY KEY, inverter_id INT, code INT, message TEXT,
            raised_at INT, cleared_at INT);
        INSERT INTO installations VALUES (1, 'Client', 'Metlaoui', 1);
        INSERT INTO inverters VALUES (1, 1, 'SOLIS-TEST-01', 'Solis S5-GR3P12K');
    """)
    for dt in alarmes:
        con.execute("INSERT INTO alerts (inverter_id, code, message, raised_at) VALUES (1, 301, 'x', ?)",
                    (int(dt.timestamp()),))
    con.commit(); con.close()
    for d, r, *trou in jours:
        _journee(db_path, d, energie_attendue(d, IRR)[0] * r, trou=trou[0] if trou else None)
    return db_path


def _rapport(report, db_path, period="month", year=2026, month=10):
    import aiosqlite

    async def run():
        db = await aiosqlite.connect(db_path); db.row_factory = aiosqlite.Row
        try:
            return await report.get_report_data(db, 1, period, year, month)
        finally:
            await db.close()
    return asyncio.run(run())


def _oct(j):
    return date(2026, 10, j)


def test_mois_partiel_reference_sur_les_memes_jours_que_la_production(tmp_path, rapport):
    """Octobre en cours (aujourd'hui 18/10) : 5 jours mesurés (13 → 17/10) et une
    matinée le 18/10. La référence porte sur ces 5 jours, pas sur le mois entier ;
    la journée en cours est exclue des deux sommes."""
    db_path = _base(tmp_path, jours=[(_oct(j), 0.90) for j in range(13, 18)])
    con = sqlite3.connect(db_path)                   # matinée d'aujourd'hui : 12 kWh
    con.execute("INSERT INTO readings (inverter_id, ts, e_day, alarm) VALUES (1, ?, 12.0, 0)",
                (_ts_local(AUJ, 11),))
    con.commit(); con.close()

    d = _rapport(rapport, db_path)
    attendue = sum(energie_attendue(_oct(j), IRR)[0] for j in range(13, 18))
    assert d["periode"]["debut"] == "2026-10-01" and d["periode"]["fin"] == "2026-10-17"
    assert d["periode"]["en_cours"] is True
    assert d["nb_jours_valides"] == 5 and d["nb_jours_exclus"] == 0
    assert d["nb_jours_sans_donnees"] == 12          # 1 → 12/10
    assert d["energie_attendue_kwh"] == round(attendue, 1)
    assert d["energie_produite_kwh"] == pytest.approx(0.90 * attendue, abs=0.2)
    assert d["performance"] == pytest.approx(0.90, abs=0.002)
    assert d["reference_pvsyst_mois_kwh"] == 1618.0                       # à titre indicatif
    assert d["energie_attendue_kwh"] < d["reference_pvsyst_mois_kwh"] / 3
    assert d["co2_evite_kg"] == round(d["energie_produite_kwh"] * 0.50, 1)
    assert [j["date"] for j in d["daily_production"]][-1] == "2026-10-17"


def test_jours_incoherents_et_incomplets_exclus_des_deux_sommes(tmp_path, rapport):
    db_path = _base(tmp_path, jours=[(_oct(14), 0.97), (_oct(15), 1.30), (_oct(16), 0.97, (9, 13)),
                                     (_oct(17), 0.92)])
    d = _rapport(rapport, db_path)
    etats = {j["date"][8:]: j["etat"] for j in d["daily_production"]}
    assert etats == {"14": "normal", "15": "incoherent", "16": "incomplete", "17": "vigilance"}
    valides = [j for j in d["daily_production"] if j["valide"]]
    assert d["nb_jours_valides"] == 2 and d["nb_jours_exclus"] == 2
    assert d["energie_produite_kwh"] == round(sum(j["energie_mesuree_kwh"] for j in valides), 1)
    assert d["energie_attendue_kwh"] == round(sum(j["energie_attendue_kwh"] for j in valides), 1)
    assert d["performance"] == pytest.approx(0.945, abs=0.003)


def test_alertes_de_performance_comptees_separement_des_alarmes(tmp_path, rapport):
    """4 jours sous 0,90 puis un jour normal : une alerte de performance (2 jours
    en alerte). Une alarme onduleur en octobre, une en septembre (non comptée)."""
    jours = [(_oct(j), 0.85) for j in range(10, 14)] + [(_oct(14), 1.0)]
    db_path = _base(tmp_path, jours=jours, alarmes=[datetime(2026, 10, 12, 10, tzinfo=TZ_TUNIS),
                                                    datetime(2026, 9, 28, 10, tzinfo=TZ_TUNIS)])
    d = _rapport(rapport, db_path)
    assert d["alertes_performance"] == 1
    assert d["jours_en_alerte_performance"] == 2
    assert d["alarmes_onduleur"] == 1


def test_alerte_commencee_le_mois_precedent(tmp_path, rapport):
    """29/09, 30/09 et 01/10 sous 0,90 : l'alerte se déclenche le 01/10 ; elle
    compte en octobre, pas en septembre (2 jours seulement)."""
    jours = [(date(2026, 9, 29), 0.85), (date(2026, 9, 30), 0.85), (_oct(1), 0.85), (_oct(2), 1.0)]
    db_path = _base(tmp_path, jours=jours)
    octobre, septembre = _rapport(rapport, db_path), _rapport(rapport, db_path, month=9)
    assert (octobre["alertes_performance"], octobre["jours_en_alerte_performance"]) == (1, 1)
    assert septembre["alertes_performance"] == 0
    assert septembre["periode"]["en_cours"] is False and septembre["periode"]["fin"] == "2026-09-30"
    assert septembre["reference_pvsyst_mois_kwh"] == 1708.0


def _valide(d):
    """La synthèse respecte le schéma de la route (app.schemas.SyntheseRapport)."""
    from app.schemas import SyntheseRapport
    return SyntheseRapport.model_validate(d)


def test_mois_en_cours_periode_et_libelle(tmp_path, rapport):
    d = _rapport(rapport, _base(tmp_path, jours=[(_oct(j), 1.0) for j in range(1, 18)]))
    p = _valide(d).periode
    assert (p.debut, p.fin, p.libelle) == ("2026-10-01", "2026-10-17", "Du 1er au 17 octobre 2026")
    assert p.jours_comparables == 17 and p.en_cours and not p.future
    assert d["nb_jours_valides"] == 17


def test_mois_passe_sans_donnees(tmp_path, rapport):
    """Août 2026, aucune mesure : période valide, valeurs à zéro, performance null."""
    d = _rapport(rapport, _base(tmp_path, jours=[(_oct(17), 1.0)]), month=8)
    p = _valide(d).periode
    assert (p.debut, p.fin, p.libelle) == ("2026-08-01", "2026-08-31", "Du 1er au 31 août 2026")
    assert p.jours_comparables == 31 and not p.en_cours and not p.future
    assert (d["nb_jours_valides"], d["nb_jours_exclus"], d["nb_jours_sans_donnees"]) == (0, 0, 31)
    assert (d["energie_produite_kwh"], d["energie_attendue_kwh"], d["co2_evite_kg"]) == (0, 0, 0)
    assert d["performance"] is None and d["daily_production"] == []
    assert d["reference_pvsyst_mois_kwh"] == 1873.0


def test_mois_futur_aucun_jour(tmp_path, rapport):
    d = _rapport(rapport, _base(tmp_path, jours=[(_oct(17), 1.0)]), month=11)
    p = _valide(d).periode
    assert (p.debut, p.fin, p.libelle) == ("2026-11-01", "2026-11-30", "Novembre 2026 (période à venir)")
    assert p.future and p.jours_comparables == 0
    assert (d["nb_jours_valides"], d["energie_produite_kwh"], d["energie_attendue_kwh"]) == (0, 0, 0)
    assert d["performance"] is None


def test_annee_en_cours(tmp_path, rapport):
    d = _rapport(rapport, _base(tmp_path, jours=[(_oct(16), 1.0), (_oct(17), 1.0)]), period="year")
    p = _valide(d).periode
    assert (p.debut, p.fin) == ("2026-01-01", "2026-10-17")
    assert p.libelle == "Du 1er janvier au 17 octobre 2026" and p.mois is None
    assert d["nb_jours_valides"] == 2
    assert d["reference_pvsyst_mois_kwh"] == 19631.0                      # année entière


def test_libelles_particuliers(rapport):
    lib = rapport.libelle_periode
    assert lib("month", _oct(1), date(2026, 11, 1), _oct(2), _oct(2)) == "Le 1er octobre 2026"
    assert lib("month", _oct(1), date(2026, 11, 1), _oct(1), _oct(1)) ==         "Octobre 2026 (aucune journée complète pour le moment)"
    assert lib("year", date(2027, 1, 1), date(2028, 1, 1), date(2027, 1, 1), AUJ) ==         "Année 2027 (période à venir)"


def test_route_report_data_au_format_du_schema(tmp_path, monkeypatch, rapport):
    """GET /installations/{id}/report-data : periode = {debut, fin, libelle, ...}
    (vrais modules app.api.installations, app.auth et app.db)."""
    import importlib
    import aiosqlite
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    for nom in ("app.api.installations", "app.auth", "app.db"):
        monkeypatch.delitem(sys.modules, nom, raising=False)
    installations = importlib.import_module("app.api.installations")
    auth, appdb = importlib.import_module("app.auth"), importlib.import_module("app.db")
    db_path = _base(tmp_path, jours=[(_oct(j), 1.0) for j in range(14, 18)])

    async def db_test():
        db = await aiosqlite.connect(db_path); db.row_factory = aiosqlite.Row
        try: yield db
        finally: await db.close()

    app = FastAPI(); app.include_router(installations.router)
    app.dependency_overrides[auth.get_current_user] = lambda: {"id": 1, "role": "admin"}
    app.dependency_overrides[appdb.get_db] = db_test
    client = TestClient(app)
    for q, libelle in [("period=month&year=2026&month=10", "Du 1er au 17 octobre 2026"),
                       ("period=month&year=2026&month=8", "Du 1er au 31 août 2026"),
                       ("period=year&year=2026", "Du 1er janvier au 17 octobre 2026")]:
        rep = client.get(f"/installations/1/report-data?{q}")
        assert rep.status_code == 200
        corps = rep.json()
        assert "period" not in corps and "kpis" not in corps
        assert corps["periode"]["libelle"] == libelle
        assert set(corps["periode"]) >= {"debut", "fin", "libelle"}


# ── Logique pure ──────────────────────────────────────────────────────────────

def _j(jour, r, etat):
    return JourPerformance(date=f"2026-10-{jour:02d}", energie_mesuree_kwh=0, energie_attendue_kwh=0,
                           irradiation_kwh_m2=None, mode="irradiance", r=r, etat=etat)


def test_episodes_jour_exclu_n_interrompt_pas_la_serie(rapport):
    jours = [_j(1, 0.8, "anomalie"), _j(2, 0.8, "anomalie"), _j(3, 7.0, "incoherent"),
             _j(4, 0.8, "anomalie"), _j(5, 0.8, "anomalie"), _j(6, 1.0, "normal"),
             _j(7, 0.8, "anomalie"), _j(8, 0.8, "anomalie"), _j(9, 0.8, "anomalie")]
    assert rapport.episodes_alerte(jours, "2026-10-01") == (2, 3)


def test_bornes_periode(rapport):
    assert rapport.bornes_periode("month", 2026, 10, AUJ) == (_oct(1), date(2026, 11, 1), AUJ)
    assert rapport.bornes_periode("month", 2026, 9, AUJ)[2] == _oct(1)
    assert rapport.bornes_periode("month", 2026, 11, AUJ)[2] == date(2026, 11, 1)   # aucun jour
