"""Tests de la comparaison à la référence (logique pure + route FastAPI)."""
import asyncio, os, sqlite3, sys, types
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
from app.reference import (  # noqa: E402
    comparer, couverture_mesures, energie_attendue, etat_jour, facteur_inclinaison,
)

TZ_TUNIS = timezone(timedelta(hours=1))   # Africa/Tunis : UTC+1 toute l'année
EXPR_JOUR_LOCAL = "date(ts, 'unixepoch', '+3600 seconds')"   # date locale d'une mesure (SQLite)

seed = importlib.import_module("scripts.seed_performance_demo")


def _jours_depuis_r(r_series, mois=3):
    """Construit une liste (date, e_mes, None) telle que r = e_mes/e_att = r_series."""
    d0 = date(2026, mois, 1)
    jours = [d0 + timedelta(i) for i in range(len(r_series))]
    # e_att = vraie référence mensuelle utilisée par comparer() (mode sans irradiation)
    return [(d, energie_attendue(d, None)[0] * r, None) for d, r in zip(jours, r_series)]


def test_energie_attendue_mensuelle_juillet():
    e, mode = energie_attendue(date(2026, 7, 15), None)
    assert mode == "mensuel" and abs(e - 1913 / 31) < 0.01        # ≈ 61,7 kWh


def test_energie_attendue_irradiance_exemple_rapport():
    # Exemple du chapitre 3 : H_inc = 7 kWh/m², PR = 0,845 → 63,9 kWh
    h_hor = 7 / facteur_inclinaison(7)
    e, mode = energie_attendue(date(2026, 7, 15), h_hor)
    assert mode == "irradiance" and abs(e - 63.88) < 0.05


def test_alerte_apres_trois_jours_sous_le_seuil():
    d0 = date(2026, 7, 1); ref = 1913 / 31
    facteurs = [1.0, 0.99, 0.98, 0.89, 0.88, 0.87]
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(facteurs)])
    assert res["jours_sous_seuil"] == 3 and res["alerte_performance"] is True
    assert res["jours"][-1]["etat"] == "anomalie"


def test_pas_d_alerte_si_ecart_passager():
    d0 = date(2026, 7, 1); ref = 1913 / 31
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate([1.0, 0.85, 0.99])])
    assert res["alerte_performance"] is False and res["jours"][-1]["etat"] == "normal"


def test_detection_nettoyage_scenario_complet():
    """Après ≥3 jours d'anomalie, une remontée ≥0,08 marque un nettoyage."""
    d0 = date(2026, 7, 1); ref = 1913 / 31
    # 4 jours d'anomalie (0,88→0,86) puis remontée nette à 0,99, puis normal
    facteurs = [1.00, 0.98, 0.88, 0.87, 0.865, 0.86, 0.99, 0.98, 1.00]
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(facteurs)])
    assert res["nettoyage_detecte"] is not None
    # le nettoyage tombe le jour de la remontée (7e jour, index 6)
    assert res["nettoyage_detecte"] == (d0 + timedelta(6)).isoformat()
    # le jour est bien marqué dans le détail
    jour_nettoyage = next(j for j in res["jours"] if j["date"] == res["nettoyage_detecte"])
    assert jour_nettoyage["nettoyage"] is True
    # la période se termine normalement : plus d'alerte active
    assert res["alerte_performance"] is False


def test_scenario_defaut_alerte_avant_nettoyage_et_detection():
    """Le scénario par défaut lève l'alerte avant le jour 25 et détecte le nettoyage."""
    # Variante « avant nettoyage » (jours 1 à 24) → alerte active
    r_stop = seed.applique_bruit(seed.facteurs(stop_before_cleaning=True, sandstorm=False))
    res_stop = comparer(_jours_depuis_r(r_stop))
    assert res_stop["alerte_performance"] is True

    # Scénario complet → nettoyage détecté au jour 25 (index 24 = 5 propres + 19 de baisse)
    facs_full = seed.facteurs(stop_before_cleaning=False, sandstorm=False)
    res_full = comparer(_jours_depuis_r(seed.applique_bruit(facs_full)))
    idx_nettoyage = 5 + 19
    assert res_full["nettoyage_detecte"] == (date(2026, 3, 1) + timedelta(idx_nettoyage)).isoformat()


def test_scenario_deterministe_et_jamais_un_pile():
    """Deux exécutions identiques (graine fixe) ; jamais r = 1,00 répété."""
    facs = seed.facteurs(False, False)
    r1 = seed.applique_bruit(facs)
    r2 = seed.applique_bruit(facs)
    assert r1 == r2                                   # déterministe
    assert not any(abs(r1[i] - 1.0) < 1e-9 for i in range(len(r1)))   # bruit → jamais exactement 1,00


def test_pas_de_nettoyage_sans_anomalie_prealable():
    """Une remontée de r sans anomalie durable préalable n'est pas un nettoyage."""
    d0 = date(2026, 7, 1); ref = 1913 / 31
    facteurs = [0.91, 0.99, 1.00]          # une seule journée basse, pas 3 consécutives
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(facteurs)])
    assert res["nettoyage_detecte"] is None


def test_r_119_etat_incoherent_sans_nettoyage():
    """r = 1,19 après 4 jours d'anomalie : état incohérent, pas de nettoyage,
    jour exclu de la perte estimée et de la série d'anomalies."""
    d0 = date(2026, 7, 1); ref = 1913 / 31
    facteurs = [1.00, 0.88, 0.87, 0.865, 0.86, 1.19]
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(facteurs)])
    dernier = res["jours"][-1]
    assert dernier["etat"] == "incoherent" and abs(dernier["r"] - 1.19) < 1e-9
    assert dernier["nettoyage"] is False and res["nettoyage_detecte"] is None
    # Le jour incohérent n'interrompt pas la série d'anomalies : alerte maintenue
    assert res["jours_sous_seuil"] == 4 and res["alerte_performance"] is True
    # Perte = uniquement les 4 jours d'anomalie (le 1,00 et le 1,19 ne comptent pas)
    perte_attendue = sum(round(ref, 2) - round(ref * f, 2) for f in [0.88, 0.87, 0.865, 0.86])
    assert abs(res["perte_estimee_kwh"] - round(perte_attendue, 1)) < 0.11


def test_etat_incoherent_seul_et_message():
    d0 = date(2026, 7, 1); ref = 1913 / 31
    res = comparer([(d0, ref * 1.00, None), (d0 + timedelta(1), ref * 1.19, None)])
    assert [j["etat"] for j in res["jours"]] == ["normal", "incoherent"]
    assert res["message"].startswith("Dernier jour : valeur à vérifier")
    assert "conforme" not in res["message"]
    assert res["perte_estimee_kwh"] == 0.0
    # La borne 1,10 elle-même reste valide
    assert etat_jour(1.10) == "normal" and etat_jour(1.1001) == "incoherent"


def test_cas_du_17_10_119_pourcent_apres_jours_normaux():
    """Cas signalé : jours normaux puis 1,19 → incohérent, pas « Normal »,
    pas de nettoyage, synthèse « Dernier jour : valeur à vérifier »."""
    d0 = date(2026, 10, 13); ref = 1618 / 31
    facteurs = [0.99, 0.99, 0.98, 1.00, 1.19]
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(facteurs)])
    assert res["jours"][-1]["etat"] == "incoherent"
    assert res["nettoyage_detecte"] is None and res["alerte_performance"] is False
    assert res["message"].startswith("Dernier jour : valeur à vérifier")
    assert res["perte_estimee_kwh"] == round(sum(round(ref, 2) - round(ref * f, 2) for f in facteurs[:3]), 1)


def test_nettoyage_seulement_dans_la_plage_plausible():
    d0 = date(2026, 7, 1); ref = 1913 / 31
    base = [0.88, 0.87, 0.865, 0.86]
    def nettoyage(apres):
        res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(base + [apres])])
        return res["nettoyage_detecte"]
    assert nettoyage(1.05) is not None      # +0,19 et dans [0,95 ; 1,10] → nettoyage
    assert nettoyage(0.94) is None          # +0,08 mais sous 0,95 → pas un nettoyage
    assert nettoyage(1.15) is None          # saut au-dessus de 1,10 → incohérent


def test_nettoyage_apres_jour_incoherent():
    """Un jour incohérent intercalé est ignoré : le nettoyage reste détecté."""
    d0 = date(2026, 7, 1); ref = 1913 / 31
    facteurs = [0.88, 0.87, 0.865, 1.25, 0.99]
    res = comparer([(d0 + timedelta(i), ref * f, None) for i, f in enumerate(facteurs)])
    assert res["nettoyage_detecte"] == (d0 + timedelta(4)).isoformat()


def test_mesure_23h30_utc_rattachee_au_jour_local_suivant():
    """23:30 UTC le 17/10 = 00:30 le 18/10 à Tunis → jour local 2026-10-18.
    (Le test de la route vérifie que performance._expr_jour_local() renvoie
    bien EXPR_JOUR_LOCAL.)"""
    expr = EXPR_JOUR_LOCAL
    con = sqlite3.connect(":memory:")
    ts = int(datetime(2026, 10, 17, 23, 30, tzinfo=timezone.utc).timestamp())
    assert con.execute(f"SELECT {expr} FROM (SELECT ? AS ts)", (ts,)).fetchone()[0] == "2026-10-18"
    ts2 = int(datetime(2026, 10, 17, 22, 59, tzinfo=timezone.utc).timestamp())   # 23:59 locale
    assert con.execute(f"SELECT {expr} FROM (SELECT ? AS ts)", (ts2,)).fetchone()[0] == "2026-10-17"


# ── Route /performance : infrastructure de test ──────────────────────────────
# Dépendances du projet remplacées par des stubs ; la base SQLite de chaque
# test est désignée par _ROUTE["db"] (le stub get_db la lit à chaque requête).
# L'heure (perf._maintenant) et Open-Meteo (perf._meteo) sont
# simulés : aucun appel réseau.

_ROUTE: dict = {}
AUJ = date(2026, 10, 18)                         # « aujourd'hui » simulé (date locale)


def _module_route():
    if "perf" in _ROUTE:
        return _ROUTE["perf"], _ROUTE["client"]
    import aiosqlite
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    async def get_db():
        db = await aiosqlite.connect(_ROUTE["db"]); db.row_factory = aiosqlite.Row
        try: yield db
        finally: await db.close()
    async def get_current_user(): return {"id": 1, "role": "admin"}
    async def _check_access(i, u, db): return {"id": i}

    pkg = types.ModuleType("app.api"); pkg.__path__ = [os.path.join(os.path.dirname(__file__), "..", "app", "api")]
    sys.modules["app.api"] = pkg
    sys.modules["app.api.inverters"] = types.SimpleNamespace(_check_access=_check_access)
    sys.modules["app.auth"] = types.SimpleNamespace(get_current_user=get_current_user)
    sys.modules["app.db"] = types.SimpleNamespace(get_db=get_db)
    perf = importlib.import_module("app.api.performance")
    app = FastAPI(); app.include_router(perf.router)
    _ROUTE.update(perf=perf, client=TestClient(app))
    return perf, _ROUTE["client"]


def _ts_local(d: date, h: int, mi: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, h, mi, tzinfo=TZ_TUNIS).timestamp())


def _journee(db_path, d: date, e_final: float, trou=None, fin=(19, 0)):
    """Mesures toutes les 5 min de 05:30 à `fin` (heure locale), e_day croissant
    jusqu'à e_final. trou = (h_debut, h_fin) : aucune mesure dans cet intervalle."""
    debut, t_fin = _ts_local(d, 5, 30), _ts_local(d, *fin)
    con = sqlite3.connect(db_path)
    for ts in range(debut, t_fin + 1, 300):
        h = datetime.fromtimestamp(ts, TZ_TUNIS).hour
        if trou and trou[0] <= h < trou[1]:
            continue
        con.execute("INSERT INTO readings (inverter_id, ts, e_day, alarm) VALUES (1, ?, ?, 0)",
                    (ts, e_final * (ts - debut) / (t_fin - debut)))
    con.commit(); con.close()


def _preparer(tmp_path, monkeypatch, maintenant: datetime, meteo=None):
    """Base avec 5 jours complets (r = 1,00 0,98 0,89 0,88 0,87) avant AUJ,
    mesurés toutes les 5 min."""
    perf, client = _module_route()
    db_path = tmp_path / "t.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, e_day REAL, alarm INT)")
    con.commit(); con.close()
    for k, f in zip(range(5, 0, -1), [1.0, 0.98, 0.89, 0.88, 0.87]):
        d = AUJ - timedelta(days=k)
        _journee(db_path, d, energie_attendue(d, None)[0] * f)
    _ROUTE["db"] = db_path

    async def fausse_meteo(days): return perf.MeteoSite(**(meteo or {}))
    monkeypatch.setattr(perf, "_meteo", fausse_meteo)
    monkeypatch.setattr(perf, "_maintenant", lambda: maintenant)
    return perf, client, db_path


def _ajouter(db_path, ts, e_day):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO readings (inverter_id, ts, e_day, alarm) VALUES (1, ?, ?, 0)", (ts, e_day))
    con.commit(); con.close()


COUCHER_1745 = dict(couchers={AUJ.isoformat(): time(17, 45)})   # coucher simulé à 17:45


def test_route_performance(tmp_path, monkeypatch):
    """Route complète : jours locaux, Open-Meteo indisponible → mode mensuel."""
    perf, client, db_path = _preparer(tmp_path, monkeypatch, datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS))
    assert perf._expr_jour_local() == EXPR_JOUR_LOCAL
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert len(body["jours"]) == 5 and body["alerte_performance"] is True
    assert body["jours"][0]["mode"] == "mensuel" and abs(body["jours"][0]["r"] - 1.0) < 0.01
    assert all(j["jour_courant"] is False for j in body["jours"])
    assert body["donnees_demonstration"] is False
    assert body["mode"] == "journaliere" and body["jours"][0]["methode"] == "journaliere"

    # Avec des mesures marquées comme démonstration → donnees_demonstration = true
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE demo_readings (inverter_id INT, ts INT, PRIMARY KEY(inverter_id, ts))")
    ts0 = con.execute("SELECT ts FROM readings WHERE inverter_id=1 LIMIT 1").fetchone()[0]
    con.execute("INSERT INTO demo_readings (inverter_id, ts) VALUES (1, ?)", (ts0,))
    con.commit(); con.close()
    assert client.get("/inverters/1/performance?days=7&mode=auto").json()["donnees_demonstration"] is True


def test_15h_avant_coucher_aujourdhui_absent(tmp_path, monkeypatch):
    perf, client, db_path = _preparer(
        tmp_path, monkeypatch, datetime(2026, 10, 18, 15, 0, tzinfo=TZ_TUNIS), COUCHER_1745)
    _ajouter(db_path, _ts_local(AUJ, 14, 55), 31.4)
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert AUJ.isoformat() not in [j["date"] for j in body["jours"]]
    assert body["aujourdhui"] == {"energie_kwh": 31.4, "termine": False, "comparaison_a_partir_de": "18:15"}
    assert body["jours"][-1]["date"] == (AUJ - timedelta(days=1)).isoformat()


def test_19h30_apres_coucher_aujourdhui_compare(tmp_path, monkeypatch):
    perf, client, db_path = _preparer(
        tmp_path, monkeypatch, datetime(2026, 10, 18, 19, 30, tzinfo=TZ_TUNIS), COUCHER_1745)
    ref = energie_attendue(AUJ, None)[0]
    _journee(db_path, AUJ, ref * 0.97, fin=(18, 10))
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    dernier = body["jours"][-1]
    assert dernier["date"] == AUJ.isoformat() and dernier["jour_courant"] is True
    assert abs(dernier["r"] - 0.97) < 0.01 and dernier["etat"] == "normal"
    assert sum(j["jour_courant"] for j in body["jours"]) == 1
    assert body["aujourdhui"]["termine"] is True
    # Les règles valent aussi pour aujourd'hui : 0,97 interrompt la série sous 0,90
    assert body["alerte_performance"] is False


def test_aujourdhui_incoherent_apres_coucher(tmp_path, monkeypatch):
    """Les règles de vraisemblance s'appliquent aussi à la journée du jour."""
    perf, client, db_path = _preparer(
        tmp_path, monkeypatch, datetime(2026, 10, 18, 20, 0, tzinfo=TZ_TUNIS), COUCHER_1745)
    _journee(db_path, AUJ, energie_attendue(AUJ, None)[0] * 1.19, fin=(18, 0))
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert body["jours"][-1]["etat"] == "incoherent" and body["nettoyage_detecte"] is None
    assert body["alerte_performance"] is True       # série 0,89 0,88 0,87 non interrompue


def test_open_meteo_indisponible_repli_19h(tmp_path, monkeypatch):
    # Sans Open-Meteo, coucher de repli 19:00 → comparaison à partir de 19:30
    perf, client, db_path = _preparer(
        tmp_path, monkeypatch, datetime(2026, 10, 18, 19, 20, tzinfo=TZ_TUNIS))
    _ajouter(db_path, _ts_local(AUJ, 18, 0), 40.0)
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert body["aujourdhui"] == {"energie_kwh": 40.0, "termine": False, "comparaison_a_partir_de": "19:30"}
    assert AUJ.isoformat() not in [j["date"] for j in body["jours"]]

    monkeypatch.setattr(perf, "_maintenant", lambda: datetime(2026, 10, 18, 19, 31, tzinfo=TZ_TUNIS))
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert body["jours"][-1]["date"] == AUJ.isoformat() and body["jours"][-1]["jour_courant"] is True
    assert perf.fin_de_production(AUJ, {}).strftime("%H:%M") == "19:30"


def test_route_mesure_23h30_utc_jour_local_suivant(tmp_path, monkeypatch):
    """Une mesure à 23:30 UTC est rattachée au jour local suivant (00:30 à Tunis)."""
    perf, client, db_path = _preparer(tmp_path, monkeypatch, datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS))
    j6 = AUJ - timedelta(days=6)
    veille = j6 - timedelta(days=1)
    ts_2330_utc = int(datetime(veille.year, veille.month, veille.day, 23, 30, tzinfo=timezone.utc).timestamp())
    _ajouter(db_path, ts_2330_utc, energie_attendue(j6, None)[0])
    dates = [j["date"] for j in client.get("/inverters/1/performance?days=7&mode=auto").json()["jours"]]
    assert dates[0] == j6.isoformat() and veille.isoformat() not in dates and len(dates) == 6


# ── Journées incomplètes (acquisition interrompue) ───────────────────────────

LEVER, COUCHER = _ts_local(AUJ, 7), _ts_local(AUJ, 18)


def test_couverture_journee_complete():
    complet, trou_max, taux = couverture_mesures(range(LEVER, COUCHER + 1, 60), LEVER, COUCHER)
    assert complet is True and trou_max == 60 and taux == 1.0


def test_couverture_trois_heures_sans_mesure_a_midi():
    ts = [t for t in range(LEVER, COUCHER + 1, 60) if not _ts_local(AUJ, 11) < t < _ts_local(AUJ, 14)]
    complet, trou_max, taux = couverture_mesures(ts, LEVER, COUCHER)
    assert complet is False and trou_max == 3 * 3600
    assert abs(taux - 8 / 11) < 1e-9                  # 3 h perdues sur 11 h


def test_couverture_regles_30_min_et_80_pourcent():
    pas = list(range(LEVER, COUCHER + 1, 60))
    # Une absence de 31 min suffit à rendre la journée incomplète
    debut_trou = LEVER + 3600
    assert couverture_mesures([t for t in pas if not debut_trou < t < debut_trou + 31 * 60],
                              LEVER, COUCHER)[0] is False
    # Absences de 25 min chaque heure : aucune > 30 min, mais 11 × 25 min > 20 % de 11 h
    gardes = [t for t in pas if (t - LEVER) % 3600 == 0 or (t - LEVER) % 3600 >= 25 * 60]
    complet, trou_max, taux = couverture_mesures(gardes, LEVER, COUCHER)
    assert complet is False and trou_max <= 30 * 60 and taux < 0.80
    # Aucune mesure : incomplète ; démarrage 20 min après le lever : complète
    assert couverture_mesures([], LEVER, COUCHER)[0] is False
    assert couverture_mesures(range(LEVER + 20 * 60, COUCHER + 1, 60), LEVER, COUCHER)[0] is True


def test_comparer_jour_incomplet_exclu_de_l_analyse():
    """Un jour incomplet n'est ni compté sous le seuil, ni dans la perte, ni un nettoyage."""
    d0 = date(2026, 7, 1); ref = 1913 / 31
    jours = [(d0 + timedelta(i), ref * f, None) for i, f in enumerate([0.88, 0.87, 0.865, 0.86])]
    jours.append((d0 + timedelta(4), ref * 0.99, None, False))       # remontée… mais incomplète
    res = comparer(jours)
    dernier = res["jours"][-1]
    assert dernier["etat"] == "incomplete" and abs(dernier["r"] - 0.99) < 1e-9
    assert res["nettoyage_detecte"] is None and dernier["nettoyage"] is False
    assert res["jours_sous_seuil"] == 4 and res["alerte_performance"] is True
    perte = sum(round(ref, 2) - round(ref * f, 2) for f in [0.88, 0.87, 0.865, 0.86])
    assert abs(res["perte_estimee_kwh"] - round(perte, 1)) < 0.11

    # Jour incomplet très bas en dernier : ni « sous le seuil », ni perte
    res = comparer([(d0, ref, None), (d0 + timedelta(1), ref * 0.40, None, False)])
    assert res["jours_sous_seuil"] == 0 and res["perte_estimee_kwh"] == 0.0
    assert res["message"].startswith("Dernier jour : données incomplètes")


def test_route_journee_avec_3h_sans_mesure_incomplete(tmp_path, monkeypatch):
    """3 heures sans mesure à midi → « incomplete » ; journée complète → comparée."""
    perf, client, db_path = _preparer(tmp_path, monkeypatch, datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS))
    j6 = AUJ - timedelta(days=6)
    _journee(db_path, j6, energie_attendue(j6, None)[0] * 0.60, trou=(11, 14))
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    par_date = {j["date"]: j for j in body["jours"]}
    assert par_date[j6.isoformat()]["etat"] == "incomplete"
    assert abs(par_date[j6.isoformat()]["r"] - 0.60) < 0.01
    # Les 5 journées complètes restent comparées normalement
    veille = par_date[(AUJ - timedelta(days=1)).isoformat()]
    assert veille["etat"] == "anomalie" and abs(veille["r"] - 0.87) < 0.01
    assert par_date[(AUJ - timedelta(days=5)).isoformat()]["etat"] == "normal"
    assert body["jours_sous_seuil"] == 3 and body["alerte_performance"] is True
    # La journée incomplète (r = 0,60) ne gonfle pas la perte estimée
    perte_complets = 0.0
    for k, f in zip(range(5, 0, -1), [1.0, 0.98, 0.89, 0.88, 0.87]):
        e_att = energie_attendue(AUJ - timedelta(days=k), None)[0]
        perte_complets += round(e_att, 2) - round(e_att * f, 2)
    assert abs(body["perte_estimee_kwh"] - round(perte_complets, 1)) < 0.11


def test_route_lever_coucher_open_meteo(tmp_path, monkeypatch):
    """La période contrôlée suit le lever et le coucher d'Open-Meteo."""
    perf, client, db_path = _preparer(tmp_path, monkeypatch, datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS))
    j6 = AUJ - timedelta(days=6)
    # Mesures de 05:30 à 16:00 seulement : incomplète avec le repli 07:00 – 18:00
    # (2 h sans mesure), complète si le soleil se couche à 16:10 (valeur de test).
    _journee(db_path, j6, energie_attendue(j6, None)[0], fin=(16, 0))

    def etat():
        jours = client.get("/inverters/1/performance?days=7&mode=auto").json()["jours"]
        return {j["date"]: j for j in jours}[j6.isoformat()]["etat"]

    assert etat() == "incomplete"

    async def meteo(days):
        return perf.MeteoSite(couchers={j6.isoformat(): time(16, 10)}, levers={j6.isoformat(): time(6, 5)})
    monkeypatch.setattr(perf, "_meteo", meteo)
    assert etat() == "normal"
    assert perf.periode_ensoleillee(j6, {}, {}) == (_ts_local(j6, 7), _ts_local(j6, 18))


def test_scenario_demo_journees_completes():
    """Le scénario de démonstration insère des journées complètes : 10 min de
    05:00 à 20:00, e_day croissant jusqu'à l'énergie du jour."""
    d = date(2026, 6, 21)                                   # lever ≈ 05:30, coucher ≈ 19:45
    serie = seed.mesures_journee(d, 60.0)
    ts = [t for t, _ in serie]
    assert couverture_mesures(ts, _ts_local(d, 5, 30), _ts_local(d, 19, 45))[0] is True
    assert couverture_mesures(ts, _ts_local(d, 7), _ts_local(d, 18))[0] is True
    e = [v for _, v in serie]
    assert e == sorted(e) and e[0] == 0.0 and max(e) == 60.0
    assert seed.jours_scenario(2, datetime(2026, 10, 18, 23, 30, tzinfo=timezone.utc)) == [
        date(2026, 10, 17), date(2026, 10, 18)]            # 00:30 le 19/10 à Tunis
