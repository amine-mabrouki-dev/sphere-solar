"""
Supprime toutes les mesures d'un onduleur pour UNE journée LOCALE (Africa/Tunis).

La journée va de minuit à minuit, heure de Tunisie (UTC+1, pas d'heure d'été).
Le script affiche d'abord le nombre de mesures concernées, la première et la
dernière heure, et la dernière valeur de e_day, puis demande confirmation.

Suppressions :
  - readings : les mesures de la journée ;
  - demo_readings (si la table existe) : les marquages de démonstration associés ;
  - latest_metrics : si la dernière mesure de l'onduleur faisait partie de la
    journée supprimée, la ligne est recalculée à partir de la dernière mesure
    restante (ou supprimée s'il n'en reste aucune).

Le serveur FastAPI et la simulation doivent être arrêtés pendant la suppression.
Le chemin de la base est lu dans DB_PATH, comme le backend (défaut : solar.db).

Usage (depuis le dossier backend) :
    python scripts/supprimer_journee.py --inverter 3 --date 2026-10-17 --dry-run
    python scripts/supprimer_journee.py --inverter 3 --date 2026-10-17 --yes
"""
import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")      # accents sous Windows
except Exception:
    pass

DB_PATH = os.getenv("DB_PATH", "solar.db")
TZ_TUNIS = timezone(timedelta(hours=1), "Africa/Tunis")   # UTC+1 toute l'année

# Colonnes de mesure communes à readings et latest_metrics
CHAMPS = ["pv_v", "pv_i", "pv2_v", "pv2_i", "pv_p", "ac_v", "ac_i", "freq", "e_day", "e_total",
          "batt_v", "batt_i", "batt_soc", "temp", "alarm"]


def champs_presents(con: sqlite3.Connection) -> list[str]:
    """CHAMPS présents dans readings ET latest_metrics (une base pas encore
    migrée n'a pas les colonnes pv2_v / pv2_i)."""
    cols = lambda t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
    communs = cols("readings") & cols("latest_metrics")
    return [c for c in CHAMPS if c in communs]


def bornes_journee_locale(jour: date) -> tuple[int, int]:
    """[début ; fin[ de la journée locale, en horodatages UNIX."""
    debut = datetime(jour.year, jour.month, jour.day, tzinfo=TZ_TUNIS)
    return int(debut.timestamp()), int((debut + timedelta(days=1)).timestamp())


def heure_locale(ts: int) -> str:
    return datetime.fromtimestamp(ts, TZ_TUNIS).strftime("%d/%m/%Y %H:%M:%S")


def table_existe(con: sqlite3.Connection, nom: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,)
    ).fetchone() is not None


def resume(con: sqlite3.Connection, inverter: int, debut: int, fin: int) -> dict:
    """Ce que la suppression toucherait (lecture seule)."""
    n, premier, dernier = con.execute(
        "SELECT COUNT(*), MIN(ts), MAX(ts) FROM readings WHERE inverter_id = ? AND ts >= ? AND ts < ?",
        (inverter, debut, fin),
    ).fetchone()
    e_day = con.execute(
        "SELECT e_day FROM readings WHERE inverter_id = ? AND ts >= ? AND ts < ? AND e_day IS NOT NULL "
        "ORDER BY ts DESC, id DESC LIMIT 1",
        (inverter, debut, fin),
    ).fetchone()
    n_demo = con.execute(
        "SELECT COUNT(*) FROM demo_readings WHERE inverter_id = ? AND ts >= ? AND ts < ?",
        (inverter, debut, fin),
    ).fetchone()[0] if table_existe(con, "demo_readings") else 0
    lm = con.execute("SELECT ts FROM latest_metrics WHERE inverter_id = ?", (inverter,)).fetchone()
    return {
        "mesures": n, "premier": premier, "dernier": dernier,
        "e_day": e_day[0] if e_day else None, "demo": n_demo,
        "latest_touchee": lm is not None and lm[0] is not None and debut <= lm[0] < fin,
    }


def supprimer(con: sqlite3.Connection, inverter: int, debut: int, fin: int) -> dict:
    """Supprime la journée ; recalcule latest_metrics si nécessaire. Une seule transaction."""
    info = resume(con, inverter, debut, fin)
    with con:
        info["supprimees"] = con.execute(
            "DELETE FROM readings WHERE inverter_id = ? AND ts >= ? AND ts < ?", (inverter, debut, fin)
        ).rowcount
        if table_existe(con, "demo_readings"):
            con.execute(
                "DELETE FROM demo_readings WHERE inverter_id = ? AND ts >= ? AND ts < ?",
                (inverter, debut, fin),
            )
        info["latest"] = "inchangée"
        if info["latest_touchee"]:
            champs = champs_presents(con)
            restante = con.execute(
                f"SELECT ts, {', '.join(champs)} FROM readings WHERE inverter_id = ? "
                "ORDER BY ts DESC, id DESC LIMIT 1",
                (inverter,),
            ).fetchone()
            if restante is None:
                con.execute("DELETE FROM latest_metrics WHERE inverter_id = ?", (inverter,))
                info["latest"] = "supprimée (plus aucune mesure)"
            else:
                maj = ", ".join(f"{c} = ?" for c in ["ts"] + champs)
                con.execute(
                    f"UPDATE latest_metrics SET {maj}, updated_at = unixepoch() WHERE inverter_id = ?",
                    (*restante, inverter),
                )
                info["latest"] = f"recalculée depuis la mesure du {heure_locale(restante[0])}"
    return info


def main() -> None:
    p = argparse.ArgumentParser(description="Supprime les mesures d'une journée locale (Africa/Tunis).")
    p.add_argument("--inverter", type=int, required=True, help="identifiant de l'onduleur")
    p.add_argument("--date", required=True, help="journée LOCALE au format AAAA-MM-JJ")
    p.add_argument("--dry-run", action="store_true", help="affiche sans rien supprimer")
    p.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")
    a = p.parse_args()
    try:
        jour = date.fromisoformat(a.date)
    except ValueError:
        p.error("--date attend le format AAAA-MM-JJ")

    debut, fin = bornes_journee_locale(jour)
    chemin = os.path.abspath(DB_PATH)
    if not os.path.exists(chemin):
        raise SystemExit(f"Base introuvable : {chemin}")
    print(f"Base : {chemin}")
    print(f"Onduleur {a.inverter} — journée locale du {jour.strftime('%d/%m/%Y')} "
          f"({heure_locale(debut)} → {heure_locale(fin)}, heure de Tunisie)")

    # Essai à blanc : ouverture en lecture seule, aucune écriture possible
    con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True) if a.dry_run else sqlite3.connect(chemin)
    try:
        info = resume(con, a.inverter, debut, fin)
        print(f"  Mesures concernées : {info['mesures']}")
        if info["mesures"]:
            print(f"  Première mesure    : {heure_locale(info['premier'])}")
            print(f"  Dernière mesure    : {heure_locale(info['dernier'])}")
            print(f"  Dernier e_day      : {info['e_day'] if info['e_day'] is not None else '—'} kWh")
        print(f"  Marquages démo     : {info['demo']}")
        print(f"  latest_metrics     : {'à recalculer' if info['latest_touchee'] else 'non concernée'}")

        if a.dry_run:
            print("Essai à blanc (--dry-run) : rien n'a été supprimé.")
            return
        if info["mesures"] == 0 and info["demo"] == 0:
            print("Rien à supprimer.")
            return
        if not a.yes:
            try:
                ok = input(f"Supprimer ces {info['mesures']} mesure(s) ? [o/N] ").strip().lower() in ("o", "oui")
            except EOFError:
                ok = False
            if not ok:
                print("Suppression annulée.")
                return
        res = supprimer(con, a.inverter, debut, fin)
        print(f"{res['supprimees']} mesure(s) supprimée(s) ; latest_metrics {res['latest']}.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
