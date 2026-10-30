"""
==============================================================================
  SCÉNARIO DE DÉMONSTRATION « POUSSIÈRE / ENCRASSEMENT »  —  DONNÉES FICTIVES
==============================================================================

Ce script insère dans la table `readings` un historique ARTIFICIEL destiné à
montrer la détection de perte lente de performance (encrassement) puis le
retour à la normale après nettoyage. Chaque journée est une série de mesures
toutes les 10 min de 05:00 à 20:00 (heure locale) : elle couvre toute la période
ensoleillée et passe donc le contrôle de complétude de la route /performance.
L'énergie du jour est répartie heure par heure selon l'irradiance horaire
réelle (Open-Meteo) : en méthode horaire, chaque heure a ainsi le même r que la
journée (repli : cloche sin² de 06:30 à 18:00).
Chaque mesure est aussi enregistrée dans
une table `demo_readings` : la route /performance peut ainsi signaler que la
période repose sur des données simulées, et `--delete` les retire proprement.

⚠️  Ces mesures ne proviennent d'AUCUN capteur : elles sont FICTIVES et servent
    uniquement à la démonstration. Ne jamais les présenter comme réelles.

Réalisme :
  - la production ATTENDUE du jour est calculée à partir de l'irradiation RÉELLE
    (Open-Meteo) via les formules de app.reference (PVsyst) ;
  - la production MESURÉE = attendue × facteur d'encrassement × (1 + bruit),
    bruit gaussien déterministe (graine fixe) → résultat identique à chaque
    exécution, jamais r = 1,00 répété ;
  - si Open-Meteo est injoignable : repli sur la moyenne mensuelle PVsyst
    multipliée par une variation météo pseudo-aléatoire déterministe (0,85–1,05).

Profil par défaut (28 jours complets, du plus ancien au plus récent) :
  - jours 1 à 5   : installation propre            (facteur 1,00)
  - jours 6 à 24  : baisse régulière 1,00 → 0,88   (~0,6 %/j, poussière)
  - jour 25       : nettoyage des modules          (0,99)
  - jours 26 à 28 : fonctionnement normal          (0,98 … 1,00)

Options :
  --inverter N            onduleur ciblé (obligatoire)
  --days N                nombre de jours (défaut : durée du scénario)
  --stop-before-cleaning  n'insère que les jours 1 à 24 (alerte active)
  --sandstorm             variante « vent de sable » : chute brutale 1,00 → 0,85
                          en 2 jours, maintien bas, puis nettoyage
  --delete                supprime les mesures de démo (readings + demo_readings)
  --purge-legacy          supprime l'ANCIEN historique de démonstration non marqué :
                          mesures à 18:00:00 UTC pile, e_day renseigné, pv_p / pv_v /
                          ac_v nuls, absentes de demo_readings (voir RAPPORT_CORRECTION.md)
  --purge-simulation-days N
                          supprime la télémétrie (pv_p renseigné) des N derniers jours
                          COMPLETS (date locale Africa/Tunis) produite par l'ancienne
                          simulation, pour repartir sur des journées propres
  --avec-jour-en-cours    avec --purge-simulation-days : inclut aussi la journée en cours
  --yes                   ne pas demander de confirmation avant une suppression

Usage (depuis le dossier backend) :
    python scripts/seed_performance_demo.py --inverter 3
    python scripts/seed_performance_demo.py --inverter 3 --stop-before-cleaning
    python scripts/seed_performance_demo.py --inverter 3 --sandstorm
    python scripts/seed_performance_demo.py --inverter 3 --delete
    python scripts/seed_performance_demo.py --inverter 3 --purge-legacy
    python scripts/seed_performance_demo.py --inverter 3 --purge-simulation-days 2

Le chemin de la base est lu dans DB_PATH (défaut : solar.db), comme le backend.
"""
import argparse
import calendar
import math
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")      # accents + « → » sous Windows
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.performance_horaire import irradiance_horaire  # noqa: E402
from app.reference import PVSYST_MENSUEL, energie_attendue  # noqa: E402

try:
    import httpx
except Exception:                                  # pragma: no cover
    httpx = None

DB_PATH = os.getenv("DB_PATH", "solar.db")
# Série intrajournalière (heure locale) : de 05:00 à 20:00, une mesure toutes les
# 10 min ; la production suit une cloche sin² de 06:30 à 18:00.
DEBUT_SERIE_H, FIN_SERIE_H, PAS_SERIE_MIN = 5.0, 20.0, 10
DEBUT_PROD_H, FIN_PROD_H = 6.5, 18.0
GRAINE = 20260101          # graine fixe → scénario reproductible
BRUIT_SIGMA = 0.015        # écart-type du bruit (1,5 %)
BRUIT_MAX = 0.03           # borne du bruit (±3 %)
LAT, LON = 34.3264, 8.4050
DECALAGE_LOCAL_S = 3600    # Africa/Tunis : UTC+1 toute l'année (pas d'heure d'été)

# Ancien historique de démonstration, inséré avant le marquage demo_readings :
# 18:00:00 UTC exactement, e_day renseigné, aucune grandeur électrique.
CONDITION_LEGACY = (
    "ts % 86400 = 64800 "
    "AND e_day IS NOT NULL "
    "AND COALESCE(pv_p, 0) = 0 AND COALESCE(pv_v, 0) = 0 AND COALESCE(ac_v, 0) = 0 "
    "AND NOT EXISTS (SELECT 1 FROM demo_readings d "
    "                WHERE d.inverter_id = readings.inverter_id AND d.ts = readings.ts)"
)

BANNIERE = (
    "============================================================\n"
    "  DONNÉES FICTIVES — SCÉNARIO DE DÉMONSTRATION « POUSSIÈRE »\n"
    "  (ne représentent aucune mesure réelle)\n"
    "============================================================"
)


# ── Facteurs d'encrassement (du plus ancien au plus récent) ───────────────────

def facteurs(stop_before_cleaning: bool, sandstorm: bool) -> list[float]:
    if sandstorm:
        # Vent de sable : propre, chute 1,00→0,85 en 2 jours, maintien bas, nettoyage, normal
        return [1.00, 1.00, 1.00, 0.92, 0.85, 0.85, 0.86, 0.99, 0.98, 1.00]
    propre = [1.00, 1.00, 1.00, 1.00, 1.00]                      # jours 1 à 5
    # jours 6 à 24 : baisse linéaire régulière de ~0,99 à 0,87 (marge sous 0,90)
    n_baisse = 19
    baisse = [round(0.99 - i * (0.99 - 0.87) / (n_baisse - 1), 4) for i in range(n_baisse)]
    if stop_before_cleaning:
        return propre + baisse                                   # jours 1 à 24
    nettoyage = [0.99]                                           # jour 25
    normal_fin = [0.99, 0.98, 1.00]                              # jours 26 à 28
    return propre + baisse + nettoyage + normal_fin


def applique_bruit(facteurs_liste: list[float], graine: int = GRAINE) -> list[float]:
    """r réalisé = facteur × (1 + bruit). Bruit gaussien déterministe (graine fixe),
    borné à ±3 %. Comme r = E_mes/E_att, cette suite est exactement la suite des r."""
    rng = random.Random(graine)
    return [f * (1 + max(-BRUIT_MAX, min(BRUIT_MAX, rng.gauss(0.0, BRUIT_SIGMA)))) for f in facteurs_liste]


def jours_scenario(n: int, maintenant: datetime | None = None) -> list[date]:
    """Les n derniers jours locaux complets (Africa/Tunis), du plus ancien au plus récent."""
    maintenant = maintenant or datetime.now(timezone.utc)
    aujourdhui = (maintenant + timedelta(seconds=DECALAGE_LOCAL_S)).date()
    return [aujourdhui - timedelta(days=k) for k in range(n, 0, -1)]


def part_produite(minute: float, g_horaire: list | None = None) -> float:
    """Part (0 → 1) de l'énergie du jour produite à `minute` (heure locale).
    Avec l'irradiance horaire du jour (24 valeurs W/m²) : cumul de l'irradiance
    des heures DEBUT_SERIE_H à FIN_SERIE_H, linéaire dans l'heure. Sinon : cloche
    sin² entre DEBUT_PROD_H et FIN_PROD_H."""
    if g_horaire:
        poids = [max(0.0, g_horaire[h] or 0.0) if DEBUT_SERIE_H <= h < FIN_SERIE_H else 0.0
                 for h in range(24)]
        total = sum(poids)
        if total > 0:
            h, frac = int(minute // 60), (minute % 60) / 60
            return (sum(poids[:min(h, 24)]) + (poids[h] * frac if h < 24 else 0.0)) / total
    x = min(1.0, max(0.0, (minute / 60 - DEBUT_PROD_H) / (FIN_PROD_H - DEBUT_PROD_H)))
    return x - math.sin(2 * math.pi * x) / (2 * math.pi)


def mesures_journee(d: date, e_jour: float, g_horaire: list | None = None) -> list[tuple[int, float]]:
    """Série (ts, e_day) du jour local d : e_day croît selon part_produite et vaut
    e_jour en fin de journée."""
    minuit = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - DECALAGE_LOCAL_S
    out = []
    for minute in range(int(DEBUT_SERIE_H * 60), int(FIN_SERIE_H * 60) + 1, PAS_SERIE_MIN):
        out.append((minuit + minute * 60, round(e_jour * part_produite(minute, g_horaire), 2)))
    return out


# ── Irradiation réelle (Open-Meteo) ───────────────────────────────────────────

def irradiation_reelle(jours: list[date]) -> tuple[dict[str, float], dict[str, list]]:
    """Irradiation horizontale réelle par date ISO : journalière (kWh/m² ;
    shortwave_radiation_sum est en MJ/m², ÷3,6) et horaire (24 valeurs W/m²,
    heures locales). Repli ({}, {}) si échec."""
    if httpx is None or not jours:
        return {}, {}
    plus_ancien = min(jours)
    nb = (max(jours) - plus_ancien).days + 1
    try:
        if nb <= 92:
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
                   f"&daily=shortwave_radiation_sum&hourly=shortwave_radiation&timezone=Africa/Tunis"
                   f"&past_days={min(nb + 1, 92)}&forecast_days=1")
        else:
            url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}"
                   f"&daily=shortwave_radiation_sum&hourly=shortwave_radiation&timezone=Africa/Tunis"
                   f"&start_date={plus_ancien.isoformat()}&end_date={max(jours).isoformat()}")
        with httpx.Client(timeout=10) as client:
            resp = client.get(url)
            resp.raise_for_status()
            donnees = resp.json()
    except Exception as exc:
        print(f"[avertissement] Open-Meteo injoignable ({exc}) — repli sur la moyenne mensuelle PVsyst.")
        return {}, {}
    daily = donnees.get("daily", {})
    out: dict[str, float] = {}
    for d, mj in zip(daily.get("time", []), daily.get("shortwave_radiation_sum", [])):
        if mj is not None:
            out[d] = mj / 3.6
    return out, irradiance_horaire(donnees.get("hourly", {}))


def attendue_repli(d: date) -> float:
    """Repli déterministe : moyenne mensuelle PVsyst × variation météo 0,85–1,05."""
    base = PVSYST_MENSUEL[d.month][2] * 1000.0 / calendar.monthrange(d.year, d.month)[1]
    var = random.Random(GRAINE ^ d.toordinal()).uniform(0.85, 1.05)
    return base * var


# ── Programme principal ───────────────────────────────────────────────────────

def ensure_demo_table(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS demo_readings ("
        "inverter_id INTEGER, ts INTEGER, PRIMARY KEY(inverter_id, ts))"
    )


# ── Purges (ancien historique, anciennes journées simulées) ───────────────────

def compter_legacy(con: sqlite3.Connection, inverter: int) -> int:
    ensure_demo_table(con)
    return con.execute(
        f"SELECT COUNT(*) FROM readings WHERE inverter_id = ? AND {CONDITION_LEGACY}", (inverter,)
    ).fetchone()[0]


def purger_legacy(con: sqlite3.Connection, inverter: int) -> int:
    ensure_demo_table(con)
    return con.execute(
        f"DELETE FROM readings WHERE inverter_id = ? AND {CONDITION_LEGACY}", (inverter,)
    ).rowcount


def bornes_jours_complets(n: int, avec_jour_en_cours: bool = False,
                          maintenant: datetime | None = None) -> tuple[int, int, date, date]:
    """[début ; fin[ en timestamps couvrant les n derniers jours complets (date locale),
    plus la journée en cours si demandé. Retourne aussi le premier et le dernier jour."""
    maintenant = maintenant or datetime.now(timezone.utc)
    aujourdhui = (maintenant + timedelta(seconds=DECALAGE_LOCAL_S)).date()
    premier = aujourdhui - timedelta(days=n)
    dernier = aujourdhui if avec_jour_en_cours else aujourdhui - timedelta(days=1)
    minuit = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - DECALAGE_LOCAL_S
    return minuit(premier), minuit(dernier + timedelta(days=1)), premier, dernier


CONDITION_TELEMETRIE = "inverter_id = ? AND ts >= ? AND ts < ? AND pv_p IS NOT NULL"


def compter_simulation(con: sqlite3.Connection, inverter: int, debut: int, fin: int) -> int:
    return con.execute(
        f"SELECT COUNT(*) FROM readings WHERE {CONDITION_TELEMETRIE}", (inverter, debut, fin)
    ).fetchone()[0]


def purger_simulation(con: sqlite3.Connection, inverter: int, debut: int, fin: int) -> int:
    return con.execute(
        f"DELETE FROM readings WHERE {CONDITION_TELEMETRIE}", (inverter, debut, fin)
    ).rowcount


def confirmer(question: str, oui: bool) -> bool:
    if oui:
        return True
    try:
        return input(f"{question} [o/N] ").strip().lower() in ("o", "oui", "y", "yes")
    except EOFError:
        return False


def purges(con: sqlite3.Connection, a: argparse.Namespace) -> None:
    if a.purge_legacy:
        n = compter_legacy(con, a.inverter)
        print(f"Ancien historique de démonstration (onduleur {a.inverter}) : {n} ligne(s) "
              f"à 18:00:00 UTC, e_day seul, non marquées.")
        if n and confirmer(f"Supprimer ces {n} ligne(s) ?", a.yes):
            supprimees = purger_legacy(con, a.inverter)
            con.commit()
            print(f"  → {supprimees} ligne(s) supprimée(s).")
        elif n:
            print("  → Suppression annulée.")

    if a.purge_simulation_days is not None:
        debut, fin, premier, dernier = bornes_jours_complets(a.purge_simulation_days, a.avec_jour_en_cours)
        n = compter_simulation(con, a.inverter, debut, fin)
        print(f"Télémétrie simulée (onduleur {a.inverter}) du {premier.strftime('%d/%m/%Y')} "
              f"au {dernier.strftime('%d/%m/%Y')} (dates locales) : {n} mesure(s).")
        if n and confirmer(f"Supprimer ces {n} mesure(s) ?", a.yes):
            supprimees = purger_simulation(con, a.inverter, debut, fin)
            con.commit()
            print(f"  → {supprimees} mesure(s) supprimée(s).")
        elif n:
            print("  → Suppression annulée.")


def main() -> None:
    print(BANNIERE)

    p = argparse.ArgumentParser(description="Insère un scénario d'encrassement FICTIF.")
    p.add_argument("--inverter", type=int, required=True)
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--stop-before-cleaning", action="store_true")
    p.add_argument("--sandstorm", action="store_true")
    p.add_argument("--delete", action="store_true")
    p.add_argument("--purge-legacy", action="store_true")
    p.add_argument("--purge-simulation-days", type=int, default=None, metavar="N")
    p.add_argument("--avec-jour-en-cours", action="store_true")
    p.add_argument("--yes", action="store_true")
    a = p.parse_args()
    if a.purge_simulation_days is not None and a.purge_simulation_days < 1:
        p.error("--purge-simulation-days attend un nombre de jours ≥ 1")
    if a.avec_jour_en_cours and a.purge_simulation_days is None:
        p.error("--avec-jour-en-cours s'utilise avec --purge-simulation-days")

    con = sqlite3.connect(DB_PATH)
    ensure_demo_table(con)

    # ── Purges ──────────────────────────────────────────────────────────────────
    if a.purge_legacy or a.purge_simulation_days is not None:
        print(f"Base : {os.path.abspath(DB_PATH)}")
        purges(con, a)
        con.close()
        return

    # ── Suppression ─────────────────────────────────────────────────────────────
    if a.delete:
        n = con.execute(
            "DELETE FROM readings WHERE inverter_id = ? AND ts IN "
            "(SELECT ts FROM demo_readings WHERE inverter_id = ?)",
            (a.inverter, a.inverter),
        ).rowcount
        con.execute("DELETE FROM demo_readings WHERE inverter_id = ?", (a.inverter,))
        con.commit()
        con.close()
        print(f"{n} mesure(s) FICTIVE(s) de démonstration supprimée(s).")
        return

    # ── Préparation des facteurs et des jours ──────────────────────────────────
    facs = facteurs(a.stop_before_cleaning, a.sandstorm)
    if a.days:
        if a.days <= len(facs):
            facs = facs[-a.days:]
        else:
            facs = [1.00] * (a.days - len(facs)) + facs

    dates = jours_scenario(len(facs))
    irr, horaire = irradiation_reelle(dates)
    mode_global = "irradiance" if irr else "mensuel (repli)"

    rng = random.Random(GRAINE)      # bruit déterministe, en ordre chronologique
    nb_mesures = 0
    for d, f in zip(dates, facs):
        h = irr.get(d.isoformat())
        if h is not None:
            e_att, _ = energie_attendue(d, h)        # formule PVsyst + irradiation réelle
        else:
            e_att = attendue_repli(d)                # repli mensuel × variation
        bruit = max(-BRUIT_MAX, min(BRUIT_MAX, rng.gauss(0.0, BRUIT_SIGMA)))
        e_mes = round(e_att * f * (1 + bruit), 2)
        for ts, e_day in mesures_journee(d, e_mes, horaire.get(d.isoformat())):
            con.execute(
                "INSERT INTO readings (inverter_id, ts, e_day, alarm) VALUES (?, ?, ?, 0)",
                (a.inverter, ts, e_day),
            )
            con.execute(
                "INSERT OR REPLACE INTO demo_readings (inverter_id, ts) VALUES (?, ?)",
                (a.inverter, ts),
            )
            nb_mesures += 1
        print(f"  {d.strftime('%d/%m/%Y')}  facteur {f:.2f}  →  e_day = {e_mes:6.2f} kWh "
              f"(attendue {e_att:5.2f} kWh)")
    con.commit()
    con.close()

    variante = ("sandstorm" if a.sandstorm
                else "sans nettoyage (alerte active)" if a.stop_before_cleaning
                else "complet (avec nettoyage)")
    print(f"\n{len(facs)} journée(s) FICTIVE(s) insérée(s) ({nb_mesures} mesures) — "
          f"scénario {variante}, référence « {mode_global} ».")
    print("Rappel : données de DÉMONSTRATION, ne représentent aucune mesure réelle.")


if __name__ == "__main__":
    main()
