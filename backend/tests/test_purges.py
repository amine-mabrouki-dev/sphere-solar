"""Tests des options --purge-legacy et --purge-simulation-days (base temporaire)."""
import importlib
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
seed = importlib.import_module("scripts.seed_performance_demo")

UTC = timezone.utc


def _ts(d: date, h: int, m: int = 0, s: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, h, m, s, tzinfo=UTC).timestamp())


def _base(tmp_path):
    con = sqlite3.connect(tmp_path / "t.db")
    con.execute("CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, "
                "pv_v REAL, pv_p REAL, ac_v REAL, e_day REAL, alarm INT)")
    seed.ensure_demo_table(con)
    return con


def _ajoute(con, inv, ts, e_day, pv_p=None, pv_v=None, ac_v=None):
    con.execute("INSERT INTO readings (inverter_id, ts, pv_v, pv_p, ac_v, e_day, alarm) "
                "VALUES (?, ?, ?, ?, ?, ?, 0)", (inv, ts, pv_v, pv_p, ac_v, e_day))


def test_purge_legacy_ne_supprime_que_l_ancien_historique(tmp_path):
    con = _base(tmp_path)
    d = date(2026, 10, 10)
    _ajoute(con, 3, _ts(d, 18), 45.9)                         # ancien historique ×2
    _ajoute(con, 3, _ts(d, 18), 45.9)
    _ajoute(con, 3, _ts(d, 18, 0, 1), 45.9)                   # 18:00:01 → conservé
    _ajoute(con, 3, _ts(d, 18), 45.9, pv_p=0.0, pv_v=0.0, ac_v=0.0)   # nuls = 0 → ancien historique
    _ajoute(con, 3, _ts(d, 18), 30.0, pv_p=1200.0, pv_v=350.0, ac_v=230.0)  # télémétrie → conservée
    _ajoute(con, 1, _ts(d, 18), 45.9)                         # autre onduleur → conservé
    marque = _ts(d - timedelta(days=1), 18)                   # démo marquée → --delete, pas ici
    _ajoute(con, 3, marque, 50.0)
    con.execute("INSERT INTO demo_readings (inverter_id, ts) VALUES (3, ?)", (marque,))

    assert seed.compter_legacy(con, 3) == 3
    assert seed.purger_legacy(con, 3) == 3
    restants = con.execute("SELECT inverter_id, ts, e_day FROM readings ORDER BY id").fetchall()
    assert (3, marque, 50.0) in restants and len(restants) == 4
    assert seed.compter_legacy(con, 3) == 0


def test_bornes_jours_complets_en_date_locale():
    # 18/10 à 23:30 UTC = 19/10 00:30 à Tunis : le jour en cours est le 19/10
    maintenant = datetime(2026, 10, 18, 23, 30, tzinfo=UTC)
    debut, fin, premier, dernier = seed.bornes_jours_complets(2, False, maintenant)
    assert (premier, dernier) == (date(2026, 10, 17), date(2026, 10, 18))
    assert debut == _ts(date(2026, 10, 16), 23)               # 17/10 00:00 locale
    assert fin == _ts(date(2026, 10, 18), 23)                 # 19/10 00:00 locale (exclu)
    _, fin2, _, dernier2 = seed.bornes_jours_complets(2, True, maintenant)
    assert dernier2 == date(2026, 10, 19) and fin2 == _ts(date(2026, 10, 19), 23)


def test_purge_simulation_jours_complets_uniquement(tmp_path):
    con = _base(tmp_path)
    maintenant = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    debut, fin, *_ = seed.bornes_jours_complets(1, False, maintenant)   # 17/10 local
    _ajoute(con, 3, _ts(date(2026, 10, 17), 10), 20.0, pv_p=5000.0)    # 17/10 → supprimée
    _ajoute(con, 3, _ts(date(2026, 10, 16), 22, 30), 50.0, pv_p=0.0)   # 16/10 23:30 locale → conservée
    _ajoute(con, 3, _ts(date(2026, 10, 16), 23, 30), 0.0, pv_p=0.0)    # 17/10 00:30 locale → supprimée
    _ajoute(con, 3, _ts(date(2026, 10, 18), 10), 20.0, pv_p=5000.0)    # jour en cours → conservée
    _ajoute(con, 3, _ts(date(2026, 10, 17), 18), 45.0)                 # sans pv_p (non télémétrie) → conservée
    _ajoute(con, 1, _ts(date(2026, 10, 17), 10), 20.0, pv_p=5000.0)    # autre onduleur → conservée
    assert seed.compter_simulation(con, 3, debut, fin) == 2
    assert seed.purger_simulation(con, 3, debut, fin) == 2
    assert con.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 4


def test_confirmation(monkeypatch):
    assert seed.confirmer("?", True) is True
    monkeypatch.setattr("builtins.input", lambda _q: "o")
    assert seed.confirmer("?", False) is True
    monkeypatch.setattr("builtins.input", lambda _q: "")
    assert seed.confirmer("?", False) is False
