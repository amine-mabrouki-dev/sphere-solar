"""Tests du script de suppression d'une journée locale (base temporaire)."""
import importlib
import os
import sqlite3
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sj = importlib.import_module("scripts.supprimer_journee")

UTC = timezone.utc


def _ts(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp())


def _base(tmp_path, demo=True):
    con = sqlite3.connect(tmp_path / "t.db")
    cols = ", ".join(f"{c} REAL" for c in sj.CHAMPS)
    con.execute(f"CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, {cols})")
    con.execute(f"CREATE TABLE latest_metrics (inverter_id INT PRIMARY KEY, ts INT, {cols}, "
                "updated_at INT NOT NULL DEFAULT (unixepoch()))")
    if demo:
        con.execute("CREATE TABLE demo_readings (inverter_id INT, ts INT, PRIMARY KEY(inverter_id, ts))")
    return con


def _mesure(con, inv, ts, e_day):
    con.execute("INSERT INTO readings (inverter_id, ts, e_day, pv_p) VALUES (?, ?, ?, 1000)", (inv, ts, e_day))


def test_bornes_journee_locale_tunis():
    debut, fin = sj.bornes_journee_locale(date(2026, 10, 17))
    assert debut == _ts(2026, 10, 16, 23)          # 17/10 00:00 à Tunis = 16/10 23:00 UTC
    assert fin == _ts(2026, 10, 17, 23)            # 18/10 00:00 à Tunis (exclu)


def test_suppression_journee_et_bornes(tmp_path):
    con = _base(tmp_path)
    _mesure(con, 3, _ts(2026, 10, 16, 22, 30), 50.0)   # 16/10 23:30 locale → conservée
    _mesure(con, 3, _ts(2026, 10, 16, 23, 30), 0.0)    # 17/10 00:30 locale → supprimée
    _mesure(con, 3, _ts(2026, 10, 17, 15), 55.1)       # 17/10 16:00 locale → supprimée
    _mesure(con, 3, _ts(2026, 10, 17, 23, 30), 0.0)    # 18/10 00:30 locale → conservée
    _mesure(con, 1, _ts(2026, 10, 17, 15), 40.0)       # autre onduleur → conservée
    con.execute("INSERT INTO demo_readings VALUES (3, ?)", (_ts(2026, 10, 17, 15),))
    con.execute("INSERT INTO latest_metrics (inverter_id, ts, e_day) VALUES (3, ?, 0.0)", (_ts(2026, 10, 17, 23, 30),))
    debut, fin = sj.bornes_journee_locale(date(2026, 10, 17))

    info = sj.resume(con, 3, debut, fin)
    assert info["mesures"] == 2 and info["e_day"] == 55.1 and info["demo"] == 1
    assert info["latest_touchee"] is False          # dernière mesure = 18/10 → latest inchangée

    res = sj.supprimer(con, 3, debut, fin)
    assert res["supprimees"] == 2 and res["latest"] == "inchangée"
    assert con.execute("SELECT COUNT(*) FROM readings WHERE inverter_id = 3 AND ts >= ? AND ts < ?",
                       (debut, fin)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM demo_readings").fetchone()[0] == 0


def test_latest_metrics_recalculee_ou_supprimee(tmp_path):
    con = _base(tmp_path, demo=False)               # demo_readings absente : pas d'erreur
    _mesure(con, 3, _ts(2026, 10, 16, 12), 30.0)
    _mesure(con, 3, _ts(2026, 10, 17, 12), 40.0)
    con.execute("INSERT INTO latest_metrics (inverter_id, ts, e_day) VALUES (3, ?, 40.0)", (_ts(2026, 10, 17, 12),))
    res = sj.supprimer(con, 3, *sj.bornes_journee_locale(date(2026, 10, 17)))
    assert res["latest"].startswith("recalculée")
    assert con.execute("SELECT ts, e_day FROM latest_metrics WHERE inverter_id = 3").fetchone() == \
        (_ts(2026, 10, 16, 12), 30.0)

    # Plus aucune mesure → la ligne latest_metrics disparaît
    res = sj.supprimer(con, 3, *sj.bornes_journee_locale(date(2026, 10, 16)))
    assert res["latest"].startswith("supprimée")
    assert con.execute("SELECT COUNT(*) FROM latest_metrics").fetchone()[0] == 0
