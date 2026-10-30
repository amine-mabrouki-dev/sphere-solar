import os
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "solar.db")

_db: aiosqlite.Connection | None = None


async def get_db():
    yield _db


def _db_handle() -> aiosqlite.Connection:
    """Return the live connection (for scripts/tasks outside the request cycle)."""
    if _db is None:
        raise RuntimeError("DB not initialised — call init_db() first")
    return _db


async def init_db():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA busy_timeout=5000")
    await _create_tables()
    await migrer(_db)
    await _db.commit()


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


# Colonnes ajoutées après la création des tables : ajoutées aux bases
# existantes par ALTER TABLE … ADD COLUMN (les données sont conservées,
# les anciennes lignes ont la valeur NULL).
COLONNES_AJOUTEES = {
    "readings":       [("pv2_v", "REAL"), ("pv2_i", "REAL")],   # entrée PV 2
    "latest_metrics": [("pv2_v", "REAL"), ("pv2_i", "REAL")],
}


async def migrer(db: aiosqlite.Connection) -> list[str]:
    """Ajoute les colonnes manquantes. Sans effet si elles existent déjà.
    Retourne la liste « table.colonne » des colonnes ajoutées."""
    ajoutees = []
    for table, colonnes in COLONNES_AJOUTEES.items():
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            existantes = {r[1] for r in await cur.fetchall()}
        for nom, type_sql in colonnes:
            if nom not in existantes:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {nom} {type_sql}")
                ajoutees.append(f"{table}.{nom}")
    return ajoutees


async def _create_tables():
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'viewer',
            created_at    INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS installations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            location      TEXT,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            created_at    INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS inverters (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            installation_id INTEGER NOT NULL REFERENCES installations(id),
            serial          TEXT UNIQUE NOT NULL,
            model           TEXT,
            created_at      INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            inverter_id INTEGER NOT NULL REFERENCES inverters(id),
            ts          INTEGER NOT NULL,
            pv_v        REAL, pv_i REAL, pv_p REAL,
            pv2_v       REAL, pv2_i REAL,
            ac_v        REAL, ac_i REAL, freq REAL,
            e_day       REAL, e_total REAL,
            batt_v      REAL, batt_i REAL, batt_soc INTEGER,
            temp        REAL, alarm INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_readings_inverter_ts
            ON readings(inverter_id, ts);

        CREATE TABLE IF NOT EXISTS latest_metrics (
            inverter_id INTEGER PRIMARY KEY REFERENCES inverters(id),
            ts          INTEGER,
            pv_v        REAL, pv_i REAL, pv_p REAL,
            pv2_v       REAL, pv2_i REAL,
            ac_v        REAL, ac_i REAL, freq REAL,
            e_day       REAL, e_total REAL,
            batt_v      REAL, batt_i REAL, batt_soc INTEGER,
            temp        REAL, alarm INTEGER,
            updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            inverter_id INTEGER NOT NULL REFERENCES inverters(id),
            code        INTEGER NOT NULL,
            message     TEXT,
            raised_at   INTEGER NOT NULL,
            cleared_at  INTEGER
        );
    """)
