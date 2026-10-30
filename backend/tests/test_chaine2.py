"""Entrée PV 2 : messages avec et sans pv2_v / pv2_i, migration de la base."""
import asyncio, os, sqlite3, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aiosqlite  # noqa: E402

from app.schemas import LatestMetricsOut, ReadingOut, TelemetryPayload  # noqa: E402

MESSAGE = {"site_id": 1, "inv": "SIM-0001", "ts": 1792400000,
           "pv_v": 371.2, "pv_i": 10.8, "pv_p": 8000.0, "e_day": 12.5}


def test_message_avec_et_sans_chaine_2():
    p = TelemetryPayload(**MESSAGE, pv2_v=369.0, pv2_i=10.9)
    assert p.pv2_v == 369.0 and p.pv2_i == 10.9
    p = TelemetryPayload(**MESSAGE)                       # ancien firmware
    assert p.pv2_v is None and p.pv2_i is None
    p = TelemetryPayload(**MESSAGE, pv2_v=None, pv2_i=None)   # lecture Modbus échouée
    assert p.pv2_v is None
    # Réponses /latest et /history
    assert LatestMetricsOut(inverter_id=3, pv2_v=369.0, pv2_i=0.0).pv2_i == 0.0
    assert ReadingOut(id=1, ts=1, pv2_v=369.0).pv2_i is None


# Schéma d'avant l'entrée PV 2 (bases existantes)
ANCIEN_SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'viewer', created_at INTEGER);
CREATE TABLE readings (id INTEGER PRIMARY KEY AUTOINCREMENT, inverter_id INTEGER NOT NULL,
  ts INTEGER NOT NULL, pv_v REAL, pv_i REAL, pv_p REAL, ac_v REAL, ac_i REAL, freq REAL,
  e_day REAL, e_total REAL, batt_v REAL, batt_i REAL, batt_soc INTEGER, temp REAL, alarm INTEGER);
CREATE TABLE latest_metrics (inverter_id INTEGER PRIMARY KEY, ts INTEGER, pv_v REAL, pv_i REAL,
  pv_p REAL, ac_v REAL, ac_i REAL, freq REAL, e_day REAL, e_total REAL, batt_v REAL, batt_i REAL,
  batt_soc INTEGER, temp REAL, alarm INTEGER, updated_at INTEGER NOT NULL DEFAULT (unixepoch()));
INSERT INTO users (email, password_hash) VALUES ('a@b', 'x');
INSERT INTO readings (inverter_id, ts, pv_v, pv_i, e_day) VALUES (1, 100, 370, 10, 5.5);
INSERT INTO latest_metrics (inverter_id, ts, pv_v, pv_i) VALUES (1, 100, 370, 10);
"""


def test_migration_sans_perte_et_ingestion(tmp_path, monkeypatch):
    """Base existante : init_db ajoute pv2_v / pv2_i (ALTER TABLE), garde les
    données ; le worker enregistre ensuite les messages avec et sans chaîne 2."""
    db_path = tmp_path / "ancienne.db"
    con = sqlite3.connect(db_path); con.executescript(ANCIEN_SCHEMA); con.commit(); con.close()

    import app.db as appdb
    monkeypatch.setattr(appdb, "DB_PATH", str(db_path))

    async def scenario():
        await appdb.init_db()
        try:
            db = appdb._db_handle()
            # Une deuxième migration ne fait rien
            assert await appdb.migrer(db) == []
            from app import mqtt_worker
            await mqtt_worker._handle_telemetry(db, TelemetryPayload(**MESSAGE, pv2_v=369.0, pv2_i=0.0))
            await mqtt_worker._handle_telemetry(db, TelemetryPayload(**{**MESSAGE, "ts": MESSAGE["ts"] + 1}))
            await db.commit()
        finally:
            await appdb.close_db()

    asyncio.run(scenario())
    con = sqlite3.connect(db_path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(readings)")]
    assert "pv2_v" in cols and "pv2_i" in cols
    assert "pv2_v" in [r[1] for r in con.execute("PRAGMA table_info(latest_metrics)")]
    # Données existantes conservées, chaîne 2 nulle pour elles
    assert con.execute("SELECT pv_v, pv_i, e_day, pv2_v FROM readings WHERE ts = 100").fetchone() == (370, 10, 5.5, None)
    # Message avec chaîne 2 puis message sans : valeurs, puis NULL
    lignes = con.execute("SELECT pv2_v, pv2_i FROM readings WHERE ts >= ? ORDER BY ts", (MESSAGE["ts"],)).fetchall()
    assert lignes == [(369.0, 0.0), (None, None)]
    con.close()


def test_migration_idempotente_base_neuve(tmp_path, monkeypatch):
    import app.db as appdb
    monkeypatch.setattr(appdb, "DB_PATH", str(tmp_path / "neuve.db"))

    async def scenario():
        await appdb.init_db()
        try:
            return await appdb.migrer(appdb._db_handle())
        finally:
            await appdb.close_db()
    assert asyncio.run(scenario()) == []          # colonnes déjà dans CREATE TABLE


def test_routes_latest_et_history_renvoient_la_chaine_2(tmp_path, monkeypatch):
    """GET /inverters/{id}/latest et /history renvoient pv2_v et pv2_i (et null
    pour une mesure d'un ancien firmware). Vrais modules app.api.inverters,
    app.auth et app.db (rétablis s'ils ont été remplacés par un autre test)."""
    import importlib
    for nom in ("app.api", "app.api.inverters", "app.auth", "app.db"):
        monkeypatch.delitem(sys.modules, nom, raising=False)
    appdb = importlib.import_module("app.db")
    inverters = importlib.import_module("app.api.inverters")
    auth = importlib.import_module("app.auth")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Base au schéma complet (init_db), puis une installation, un onduleur et des mesures
    db_path = tmp_path / "routes.db"
    monkeypatch.setattr(appdb, "DB_PATH", str(db_path))
    asyncio.run(appdb.init_db()); asyncio.run(appdb.close_db())
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (email, password_hash, role) VALUES ('a@b', 'x', 'admin')")
    con.execute("INSERT INTO installations (name, owner_user_id) VALUES ('site-1', 1)")
    con.execute("INSERT INTO inverters (installation_id, serial) VALUES (1, 'SIM')")
    con.execute("INSERT INTO readings (inverter_id, ts, pv_v, pv_i, pv2_v, pv2_i) VALUES (1, 100, 370, 10.8, 368.2, 10.9)")
    con.execute("INSERT INTO readings (inverter_id, ts, pv_v, pv_i) VALUES (1, 200, 371, 10.7)")   # ancien firmware
    con.execute("INSERT INTO latest_metrics (inverter_id, ts, pv_v, pv_i, pv2_v, pv2_i) VALUES (1, 100, 370, 10.8, 368.2, 0.0)")
    con.commit(); con.close()

    async def db_test():
        db = await aiosqlite.connect(db_path); db.row_factory = aiosqlite.Row
        try: yield db
        finally: await db.close()

    app = FastAPI(); app.include_router(inverters.router)
    app.dependency_overrides[auth.get_current_user] = lambda: {"id": 1, "role": "admin"}
    app.dependency_overrides[appdb.get_db] = db_test
    client = TestClient(app)

    latest = client.get("/inverters/1/latest").json()
    assert latest["pv2_v"] == 368.2 and latest["pv2_i"] == 0.0
    hist = client.get("/inverters/1/history").json()
    assert [(r["ts"], r["pv2_v"], r["pv2_i"]) for r in hist] == [(200, None, None), (100, 368.2, 10.9)]
