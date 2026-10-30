"""
Seed the database with the first admin user and the real installation/inverter.

Run from the backend/ directory:

    python -m app.seed

Idempotent: safe to run repeatedly. Re-running never duplicates rows and never
changes an existing admin password.

The SITE_ID and INV_SERIAL constants below MUST match the firmware CONFIG block
in src/main.cpp. If they differ, incoming telemetry will auto-register a second
("auto-registered") inverter instead of attaching to this one.

Admin credentials come from env (fall back to the defaults for local dev):
    SEED_ADMIN_EMAIL     (default: admin@sphere-solar.local)
    SEED_ADMIN_PASSWORD  (default: changeme)
"""

import asyncio
import os

from app.auth import hash_password
from app.db import close_db, init_db, _db_handle

# ── Must match src/main.cpp ──────────────────────────────────────────────────
SITE_ID    = 1
INV_SERIAL = "SOLIS-S5GR3P12K-01"

# ── Installation de démonstration (10,8 kWc, 2 chaînes de 9 modules) ──────────
INSTALLATION_NAME = "Installation résidentielle \u2014 Metlaoui"
INSTALLATION_LOC  = "Metlaoui, Tunisie (34.32 N, 8.40 E)"
INVERTER_MODEL    = "Solis S5-GR3P12K"

ADMIN_EMAIL    = os.getenv("SEED_ADMIN_EMAIL", "admin@sphere-solar.local")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "changeme")


async def seed() -> None:
    await init_db()
    db = _db_handle()

    # 1. Admin user (create only if this exact email is absent) ----------------
    async with db.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)) as cur:
        row = await cur.fetchone()
    if row:
        admin_id = row["id"]
        print(f"= admin exists: {ADMIN_EMAIL} (id={admin_id})")
    else:
        cur = await db.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?,?,'admin')",
            (ADMIN_EMAIL, hash_password(ADMIN_PASSWORD)),
        )
        admin_id = cur.lastrowid
        print(f"+ admin created: {ADMIN_EMAIL} (id={admin_id})")

    # 2. Installation (match by name) ------------------------------------------
    async with db.execute(
        "SELECT id FROM installations WHERE name = ?", (INSTALLATION_NAME,)
    ) as cur:
        row = await cur.fetchone()
    if row:
        inst_id = row["id"]
        print(f"= installation exists: {INSTALLATION_NAME} (id={inst_id})")
    else:
        cur = await db.execute(
            "INSERT INTO installations (name, location, owner_user_id) VALUES (?,?,?)",
            (INSTALLATION_NAME, INSTALLATION_LOC, admin_id),
        )
        inst_id = cur.lastrowid
        print(f"+ installation created: {INSTALLATION_NAME} (id={inst_id})")

    # 3. Inverter (match by serial) --------------------------------------------
    async with db.execute(
        "SELECT id, installation_id FROM inverters WHERE serial = ?", (INV_SERIAL,)
    ) as cur:
        row = await cur.fetchone()
    if row:
        print(f"= inverter exists: {INV_SERIAL} (id={row['id']})")
    else:
        cur = await db.execute(
            "INSERT INTO inverters (installation_id, serial, model) VALUES (?,?,?)",
            (inst_id, INV_SERIAL, INVERTER_MODEL),
        )
        print(f"+ inverter created: {INV_SERIAL} \u2192 {INVERTER_MODEL} (id={cur.lastrowid})")

    await db.commit()
    await close_db()
    print("\nSeed complete. Topics this device will use:")
    print(f"  telemetry : site/{SITE_ID}/inv/{INV_SERIAL}/telemetry")
    print(f"  command   : site/{SITE_ID}/inv/{INV_SERIAL}/cmd")
    print(f"  status    : site/{SITE_ID}/inv/{INV_SERIAL}/status")


if __name__ == "__main__":
    asyncio.run(seed())
