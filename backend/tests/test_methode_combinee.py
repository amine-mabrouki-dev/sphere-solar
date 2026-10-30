"""Tests de la route /performance avec la méthode combinée (journalière pour les
journées complètes, horaire en cas d'arrêt ou de mesures manquantes).
Open-Meteo est simulé : aucun appel réseau. Journée claire type du 17/10
(app.plan_incline.journee_claire) : 10 heures à au moins 100 W/m² (7 h → 17 h)."""
import os, sqlite3, sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.performance_horaire import HeureMesuree, energie_attendue_de  # noqa: E402
from app.plan_incline import irradiance_inclinee_horaire, journee_claire  # noqa: E402
from test_performance import AUJ, TZ_TUNIS, _ROUTE, _module_route  # noqa: E402

J = AUJ - timedelta(days=1)                      # 17/10/2026, dernier jour complet
G, DIF = journee_claire(J)
G_INC = irradiance_inclinee_horaire(J, G, DIF)
METEO = dict(irr={J.isoformat(): sum(G) / 1000}, horaire={J.isoformat(): G},
             diffuse={J.isoformat(): DIF})


def _ts(d: date, h: int, s: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, h, tzinfo=TZ_TUNIS).timestamp()) + s


def _base(tmp_path, monkeypatch, meteo):
    perf, client = _module_route()
    db_path = tmp_path / "c.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, "
                "pv_p REAL, e_day REAL, alarm INT)")
    con.commit(); con.close()
    _ROUTE["db"] = db_path

    async def fausse_meteo(days): return perf.MeteoSite(**meteo)
    monkeypatch.setattr(perf, "_meteo", fausse_meteo)
    monkeypatch.setattr(perf, "_maintenant", lambda: datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS))
    return client, db_path


def _journee(db_path, d=J, marche=range(24), facteur=1.0, coupure=(), pas_s=10):
    """Télémétrie de type ESP32 toutes les `pas_s` s : production = énergie
    attendue (irradiance inclinée) × facteur aux heures `marche`, 0 W sinon ;
    aucune mesure aux heures `coupure`."""
    con = sqlite3.connect(db_path)
    cumul = 0.0
    for h in range(24):
        e_h = (energie_attendue_de(d.month, HeureMesuree(G[h], 0, None, None, g_inc_wm2=G_INC[h]))
               * facteur if h in marche else 0.0)
        if h not in coupure:
            con.executemany("INSERT INTO readings (inverter_id, ts, pv_p, e_day, alarm) VALUES (1, ?, ?, ?, 0)",
                            [(_ts(d, h, s), e_h * 1000.0, cumul + e_h * s / 3600) for s in range(0, 3600, pas_s)])
        cumul += e_h
    con.commit(); con.close()


def _jour(client):
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    return body, body["jours"][-1]


def test_journee_complete_saine_methode_journaliere(tmp_path, monkeypatch):
    client, db = _base(tmp_path, monkeypatch, METEO)
    _journee(db)
    body, j = _jour(client)
    assert body["mode"] == "combinee"
    assert j["methode"] == "journaliere" and abs(j["r"] - 1.0) < 0.02 and j["etat"] == "normal"
    assert j["disponibilite"] == 100.0 and j["heures_fonctionnement"] == 10
    assert j["heures_soleil_utile"] == 10 and j["heures_arret"] == 0 and j["heures_soleil_total"] == 10
    assert j["heures_donnees_manquantes"] == 0 and j["energie_perdue_arret_kwh"] == 0.0
    # r journalier : énergie du jour ÷ énergie attendue avec l'irradiation journalière
    assert abs(j["energie_attendue_kwh"] - 10.8 * sum(G) / 1000 * (170.2 / 131.2) * 0.880) < 0.02


def test_marche_9h_15h_methode_horaire(tmp_path, monkeypatch):
    client, db = _base(tmp_path, monkeypatch, METEO)
    _journee(db, marche=range(9, 15))
    body, j = _jour(client)
    assert j["methode"] == "horaire" and abs(j["r"] - 1.0) < 0.02 and j["etat"] == "normal"
    assert j["heures_fonctionnement"] == 6 and j["heures_arret"] == 4 and j["heures_soleil_utile"] == 10
    assert j["disponibilite"] == 60.0
    perdu = sum(energie_attendue_de(J.month, HeureMesuree(G[h], 0, None, None, g_inc_wm2=G_INC[h]))
                for h in (7, 8, 15, 16))
    assert abs(j["energie_perdue_arret_kwh"] - perdu) < 0.05 and perdu > 5
    assert body["alerte_performance"] is False and body["perte_estimee_kwh"] < 0.5


def test_marche_9h_15h_avec_12_pourcent_de_poussiere(tmp_path, monkeypatch):
    client, db = _base(tmp_path, monkeypatch, METEO)
    _journee(db, marche=range(9, 15), facteur=0.88)
    _, j = _jour(client)
    assert j["methode"] == "horaire" and abs(j["r"] - 0.88) < 0.02 and j["etat"] == "anomalie"


def test_3_heures_sans_mesure_methode_horaire_r_non_affecte(tmp_path, monkeypatch):
    client, db = _base(tmp_path, monkeypatch, METEO)
    _journee(db, coupure=(10, 11, 12))
    _, j = _jour(client)
    assert j["methode"] == "horaire" and j["heures_donnees_manquantes"] == 3
    assert abs(j["r"] - 1.0) < 0.02 and j["disponibilite"] == 100.0
    # 7 h mesurées (et en marche) sur 10 h de soleil
    assert j["heures_fonctionnement"] == 7 and j["heures_soleil_utile"] == 7
    assert j["heures_soleil_total"] == 10
    # Avec de la poussière, r reste celui des heures mesurées
    (tmp_path / "bis").mkdir()
    client, db = _base(tmp_path / "bis", monkeypatch, METEO)
    _journee(db, coupure=(10, 11, 12), facteur=0.88)
    _, j = _jour(client)
    assert abs(j["r"] - 0.88) < 0.02


def test_scenario_de_demonstration_une_mesure_par_jour(tmp_path, monkeypatch):
    """Ancien scénario de démo : une seule mesure (19:00, e_day seul) → méthode
    journalière, disponibilité null."""
    client, db = _base(tmp_path, monkeypatch, METEO)
    e_att = 10.8 * sum(G) / 1000 * (170.2 / 131.2) * 0.880
    con = sqlite3.connect(db)
    con.execute("INSERT INTO readings (inverter_id, ts, e_day, alarm) VALUES (1, ?, ?, 0)",
                (_ts(J, 19), 0.97 * e_att))
    con.commit(); con.close()
    _, j = _jour(client)
    assert j["methode"] == "journaliere" and j["disponibilite"] is None
    assert j["heures_fonctionnement"] is None and j["heures_soleil_utile"] is None
    assert j["heures_soleil_total"] is None
    assert abs(j["r"] - 0.97) < 0.01 and j["etat"] == "normal"


def test_open_meteo_horaire_indisponible_methode_journaliere(tmp_path, monkeypatch):
    for meteo in (dict(irr=METEO["irr"]), {}):          # horaire absent ; Open-Meteo absent
        (tmp_path / str(len(meteo))).mkdir()
        client, db = _base(tmp_path / str(len(meteo)), monkeypatch, meteo)
        _journee(db, d=J - timedelta(days=1), pas_s=60)
        _journee(db, marche=range(9, 15), pas_s=60)
        body = client.get("/inverters/1/performance?days=7&mode=auto").json()
        assert body["mode"] == "journaliere" and len(body["jours"]) == 2
        assert all(j["methode"] == "journaliere" and j["disponibilite"] is None for j in body["jours"])
