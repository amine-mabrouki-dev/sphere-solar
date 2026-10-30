"""
Diagnostic de la comparaison « production mesurée / référence » — LECTURE SEULE.

Copie la base (chemin lu dans DB_PATH, comme le backend ; défaut : solar.db)
vers un fichier temporaire, puis liste, pour chaque onduleur et pour les
30 derniers jours (date LOCALE Africa/Tunis, UTC+1) :
  - le nombre de mesures,
  - la dernière et la plus grande valeur de e_day,
  - le nombre de mesures marquées dans demo_readings,
  - le nombre de lignes de l'ANCIEN historique de démonstration : mesures à
    18:00:00 UTC exactement, e_day renseigné, pv_p / pv_v / ac_v nuls (NULL ou 0)
    — insérées sans marquage demo_readings,
  - le nombre de mesures de télémétrie (simulation ESP32 : pv_p renseigné).

La base principale n'est jamais modifiée.

Usage (depuis le dossier backend) :
    python scripts/diagnostic_comparaison.py
    python scripts/diagnostic_comparaison.py --inverter 3 --days 30
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")      # accents sous Windows
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.reference import PVSYST_MENSUEL  # noqa: E402

DB_PATH = os.getenv("DB_PATH", "solar.db")
DECALAGE_S = 3600                                  # Africa/Tunis : UTC+1, pas d'heure d'été
JOUR_LOCAL = f"date(ts, 'unixepoch', '+{DECALAGE_S} seconds')"

# Ancien historique de démonstration non marqué (voir RAPPORT_CORRECTION.md)
CONDITION_LEGACY = (
    "ts % 86400 = 64800 "                          # 18:00:00 UTC exactement
    "AND e_day IS NOT NULL "
    "AND COALESCE(pv_p, 0) = 0 AND COALESCE(pv_v, 0) = 0 AND COALESCE(ac_v, 0) = 0"
)


def copie_base(chemin: str) -> str:
    """Copie cohérente (API de sauvegarde SQLite, WAL inclus), en lecture seule."""
    if not os.path.exists(chemin):
        raise SystemExit(f"Base introuvable : {os.path.abspath(chemin)}")
    dossier = tempfile.mkdtemp(prefix="diag_solar_")
    cible = os.path.join(dossier, "copie.db")
    src = sqlite3.connect(f"file:{os.path.abspath(chemin)}?mode=ro", uri=True)
    dst = sqlite3.connect(cible)
    src.backup(dst)
    src.close(); dst.close()
    return cible


def table_existe(con: sqlite3.Connection, nom: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,)
    ).fetchone() is not None


def main() -> None:
    p = argparse.ArgumentParser(description="Diagnostic (lecture seule) de la comparaison à la référence.")
    p.add_argument("--inverter", type=int, default=None, help="onduleur (défaut : tous)")
    p.add_argument("--days", type=int, default=30)
    a = p.parse_args()

    copie = copie_base(DB_PATH)
    con = sqlite3.connect(copie)
    try:
        print(f"Base analysée : {os.path.abspath(DB_PATH)} (copie : {copie})")
        demo = table_existe(con, "demo_readings")
        print(f"Table demo_readings : {'présente' if demo else 'ABSENTE'}")

        onduleurs = con.execute(
            "SELECT inv.id, inv.serial, inv.installation_id, inst.name "
            "FROM inverters inv LEFT JOIN installations inst ON inst.id = inv.installation_id "
            "ORDER BY inv.id"
        ).fetchall()
        print("\nOnduleurs :")
        for i, serial, inst, nom in onduleurs:
            dernier = con.execute("SELECT MAX(ts) FROM readings WHERE inverter_id=?", (i,)).fetchone()[0]
            vu = (datetime.fromtimestamp(dernier, timezone.utc) + timedelta(seconds=DECALAGE_S)
                  ).strftime("%d/%m/%Y %H:%M") if dernier else "jamais"
            print(f"  #{i}  {serial}  installation {inst} ({nom})  — dernière mesure : {vu} (heure locale)")

        aujourdhui = (datetime.now(timezone.utc) + timedelta(seconds=DECALAGE_S)).date()
        debut = aujourdhui - timedelta(days=a.days)
        debut_ts = int(datetime(debut.year, debut.month, debut.day, tzinfo=timezone.utc).timestamp()) - DECALAGE_S

        cibles = [o for o in onduleurs if a.inverter is None or o[0] == a.inverter]
        for i, serial, *_ in cibles:
            demo_col = (
                "SUM(CASE WHEN EXISTS (SELECT 1 FROM demo_readings d "
                "WHERE d.inverter_id = r.inverter_id AND d.ts = r.ts) THEN 1 ELSE 0 END)"
                if demo else "0"
            )
            lignes = con.execute(
                f"""
                SELECT {JOUR_LOCAL} AS j,
                       COUNT(*),
                       (SELECT e_day FROM readings r2
                         WHERE r2.inverter_id = r.inverter_id AND r2.e_day IS NOT NULL
                           AND date(r2.ts, 'unixepoch', '+{DECALAGE_S} seconds')
                             = date(r.ts, 'unixepoch', '+{DECALAGE_S} seconds')
                         ORDER BY r2.ts DESC, r2.rowid DESC LIMIT 1),
                       MAX(e_day),
                       {demo_col},
                       SUM(CASE WHEN {CONDITION_LEGACY} THEN 1 ELSE 0 END),
                       SUM(CASE WHEN pv_p IS NOT NULL THEN 1 ELSE 0 END)
                FROM readings r
                WHERE inverter_id = ? AND ts >= ?
                GROUP BY j ORDER BY j
                """,
                (i, debut_ts),
            ).fetchall()
            print(f"\nOnduleur #{i} ({serial}) — {a.days} derniers jours (date locale)")
            print("  jour        mesures  e_day dernier  e_day max  réf. mens.  max/réf  démo  ancien hist.  télémétrie")
            for j, n, dernier, emax, nd, nl, nt in lignes:
                d = datetime.fromisoformat(j).date()
                ref = PVSYST_MENSUEL[d.month][2] * 1000 / 31 if d.month in (1, 3, 5, 7, 8, 10, 12) else \
                    PVSYST_MENSUEL[d.month][2] * 1000 / (28 if d.month == 2 else 30)
                ratio = f"{emax / ref:6.2f}" if emax is not None else "     —"
                encours = "  (jour en cours)" if d == aujourdhui else ""
                print(f"  {j}  {n:7d}  {dernier if dernier is not None else '—':>13}  "
                      f"{emax if emax is not None else '—':>9}  {ref:10.1f}  {ratio}  {nd:4d}  {nl:12d}  {nt:10d}{encours}")

            total_legacy = con.execute(
                f"SELECT COUNT(*), MIN(ts), MAX(ts) FROM readings WHERE inverter_id = ? AND {CONDITION_LEGACY}",
                (i,),
            ).fetchone()
            if total_legacy[0]:
                fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%d/%m/%Y")
                print(f"  → Ancien historique de démonstration (toutes dates) : {total_legacy[0]} ligne(s), "
                      f"du {fmt(total_legacy[1])} au {fmt(total_legacy[2])}")
            else:
                print("  → Aucune ligne d'ancien historique de démonstration.")
    finally:
        con.close()
        shutil.rmtree(os.path.dirname(copie), ignore_errors=True)


if __name__ == "__main__":
    main()
