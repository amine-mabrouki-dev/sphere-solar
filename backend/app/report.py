"""
Données des rapports (synthèse de l'onglet Rapports et rapport PDF), pour un
mois ou une année.

Période comparable : seuls les jours complets passés de la période sont retenus
(la journée en cours est exclue, comme dans la comparaison à la référence).
Chaque jour est comparé à la référence par la même fonction que la route
/performance (app.api.performance.jours_compares : PVsyst + irradiation du
jour, méthode journalière ou horaire). Puis :
  - énergie produite = Σ énergie mesurée des jours VALIDES (normal, vigilance,
    anomalie) ; les jours incohérents, incomplets ou à fonctionnement
    insuffisant sont comptés à part (nb_jours_exclus) ;
  - énergie attendue = Σ énergie attendue de ces MÊMES jours valides ;
  - performance = énergie produite ÷ énergie attendue ;
  - la production PVsyst du mois (ou de l'année) entier n'est donnée qu'à titre
    indicatif (reference_pvsyst_mois_kwh).
Alertes : alarmes de l'onduleur (table alerts) et alertes de performance
(r < 0,90 pendant 3 jours valides consécutifs), comptées séparément.
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.api import performance as perf
from app.reference import ETATS_EXCLUS, JOURS_CONSECUTIFS, PVSYST_MENSUEL, SEUIL_R, JourPerformance

STEG_TARIFF = 0.250          # DT/kWh (exemple)
CO2_FACTOR = 0.50            # kg CO2 par kWh (valeur du rapport de PFE)
TREES_PER_KG_CO2 = 1 / 21    # un arbre absorbe ~21 kg de CO2 par an

# Jours repris avant le début de la période pour compter une alerte de
# performance commencée juste avant (elle exige 3 jours valides consécutifs).
JOURS_AVANT_PERIODE = 10


def bornes_periode(period: str, year: int, month: int, today: date) -> Tuple[date, date, date]:
    """(premier jour, lendemain du dernier jour de la période, lendemain du
    dernier jour COMPARABLE). Le dernier jour comparable est la veille
    d'aujourd'hui pour la période en cours ; aucun jour pour une période future."""
    if period == "month":
        debut = date(year, month, 1)
        fin_periode = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    else:
        debut, fin_periode = date(year, 1, 1), date(year + 1, 1, 1)
    fin = max(debut, min(fin_periode, today))
    return debut, fin_periode, fin


MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"]


def _jour_fr(d: date, avec_mois: bool = True, avec_annee: bool = True) -> str:
    """« 1er octobre 2026 », « 19 octobre », « 1er »."""
    morceaux = ["1er" if d.day == 1 else str(d.day)]
    if avec_mois:
        morceaux.append(MOIS_FR[d.month - 1])
    if avec_annee:
        morceaux.append(str(d.year))
    return " ".join(morceaux)


def libelle_periode(period: str, debut: date, fin_periode: date, fin: date, today: date) -> str:
    """Libellé de la période comparable : « Du 1er au 19 octobre 2026 »,
    « Le 1er octobre 2026 », « Du 1er janvier au 19 octobre 2026 » ; sans jour
    comparable : « Novembre 2026 (période à venir) » ou « Octobre 2026 (aucune
    journée complète pour le moment) »."""
    if fin > debut:
        dernier = fin - timedelta(days=1)
        if dernier == debut:
            return f"Le {_jour_fr(debut)}"
        meme_mois = (debut.year, debut.month) == (dernier.year, dernier.month)
        return f"Du {_jour_fr(debut, avec_mois=not meme_mois, avec_annee=False)} au {_jour_fr(dernier)}"
    nom = (f"{MOIS_FR[debut.month - 1].capitalize()} {debut.year}" if period == "month"
           else f"Année {debut.year}")
    if today < debut:
        return f"{nom} (période à venir)"
    return f"{nom} (aucune journée complète pour le moment)"


def reference_pvsyst_kwh(period: str, month: int) -> float:
    """Production PVsyst du mois entier (ou de l'année entière), en kWh."""
    mois = [month] if period == "month" else range(1, 13)
    return sum(PVSYST_MENSUEL[m][2] * 1000.0 for m in mois)


def episodes_alerte(jours: List[JourPerformance], debut_iso: str) -> Tuple[int, int]:
    """(alertes de performance, jours en alerte) pendant la période commençant à
    debut_iso. Règle de la comparaison : alerte dès le 3e jour valide consécutif
    sous 0,90 ; les jours exclus ne prolongent ni n'interrompent une série. Une
    alerte commencée avant la période compte si elle y est encore active."""
    consecutifs, episode = 0, 0
    episodes, jours_alerte = set(), 0
    for j in jours:
        if j.etat in ETATS_EXCLUS:
            continue
        consecutifs = consecutifs + 1 if j.r < SEUIL_R else 0
        if consecutifs == JOURS_CONSECUTIFS:
            episode += 1
        if consecutifs >= JOURS_CONSECUTIFS and j.date >= debut_iso:
            episodes.add(episode)
            jours_alerte += 1
    return len(episodes), jours_alerte


async def get_report_data(
    db,
    installation_id: int,
    period: str = "month",  # "month" ou "year"
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    today = perf._maintenant().date()          # date locale du site
    year = year or today.year
    month = month or today.month

    async with db.execute(
        "SELECT id, name, location, owner_user_id FROM installations WHERE id = ?",
        (installation_id,)
    ) as cur:
        inst = await cur.fetchone()
    if not inst:
        return None

    async with db.execute(
        "SELECT id, serial, model FROM inverters WHERE installation_id = ?",
        (installation_id,)
    ) as cur:
        inverters = [dict(r) for r in await cur.fetchall()]

    debut, fin_periode, fin = bornes_periode(period, year, month, today)
    debut_iso = debut.isoformat()
    debut_ts, fin_periode_ts = perf._minuit_local_ts(debut), perf._minuit_local_ts(fin_periode)
    debut_analyse = debut - timedelta(days=JOURS_AVANT_PERIODE)
    nb_jours_calendaires = (fin - debut).days

    # Météo Open-Meteo (irradiation, lever et coucher du soleil) : un seul appel.
    # Open-Meteo ne fournit que les 92 derniers jours ; au-delà, la référence
    # mensuelle PVsyst s'applique, comme dans la comparaison.
    meteo = await perf._meteo((today - debut_analyse).days) if fin > debut else perf.MeteoSite()

    energie_produite = energie_attendue = 0.0
    nb_valides = nb_exclus = nb_sans_donnees = 0
    alertes_perf = jours_alerte = 0
    jours_rapport: List[Dict[str, Any]] = []
    inverter_metrics = []
    max_power_w, somme_temp, nb_temp = 0.0, 0.0, 0

    for inv in inverters:
        detail = (await perf.jours_compares(db, inv["id"], debut_analyse,
                                            perf._minuit_local_ts(fin), meteo)
                  if fin > debut else [])
        jours = [j for j in detail if j.date >= debut_iso]
        valides = [j for j in jours if j.etat not in ETATS_EXCLUS]
        e_inv = sum(j.energie_mesuree_kwh for j in valides)
        energie_produite += e_inv
        energie_attendue += sum(j.energie_attendue_kwh for j in valides)
        nb_valides += len(valides)
        nb_exclus += len(jours) - len(valides)
        nb_sans_donnees += nb_jours_calendaires - len(jours)
        n_alertes, n_jours = episodes_alerte(detail, debut_iso)
        alertes_perf += n_alertes
        jours_alerte += n_jours
        jours_rapport += [{
            "date": j.date, "onduleur": inv["serial"], "etat": j.etat, "valide": j.etat not in ETATS_EXCLUS,
            "r": j.r, "energie_mesuree_kwh": j.energie_mesuree_kwh,
            "energie_attendue_kwh": j.energie_attendue_kwh, "methode": j.methode,
        } for j in jours]

        async with db.execute(
            "SELECT MAX(pv_p), COUNT(temp), AVG(temp) FROM readings "
            "WHERE inverter_id = ? AND ts >= ? AND ts < ?",
            (inv["id"], debut_ts, fin_periode_ts)
        ) as cur:
            p_max, n_t, t_moy = await cur.fetchone()
        max_power_w = max(max_power_w, float(p_max or 0))
        if n_t:
            somme_temp += t_moy * n_t
            nb_temp += n_t

        # Alarmes de l'onduleur levées pendant la période (aujourd'hui compris)
        async with db.execute(
            "SELECT id, code, message, raised_at, cleared_at FROM alerts "
            "WHERE inverter_id = ? AND raised_at >= ? AND raised_at < ? ORDER BY raised_at DESC",
            (inv["id"], debut_ts, fin_periode_ts)
        ) as cur:
            alarmes = [dict(a) for a in await cur.fetchall()]

        inverter_metrics.append({
            "id": inv["id"], "serial": inv["serial"], "model": inv["model"],
            "energie_produite_kwh": round(e_inv, 1),
            "max_power_w": round(float(p_max or 0), 1),
            "alerts": alarmes,
            "alertes_performance": n_alertes,
        })

    performance = energie_produite / energie_attendue if energie_attendue > 0 else None
    co2 = energie_produite * CO2_FACTOR
    jours_rapport.sort(key=lambda j: (j["date"], j["onduleur"]))

    return {
        "installation": dict(inst),
        "inverters": inverters,
        "periode": {
            "type": period,
            "annee": year,
            "mois": month if period == "month" else None,
            "debut": debut_iso,
            # dernier jour comparable ; s'il n'y en a aucun (période à venir ou
            # 1er jour du mois en cours), dernier jour de la période
            "fin": ((fin if fin > debut else fin_periode) - timedelta(days=1)).isoformat(),
            "libelle": libelle_periode(period, debut, fin_periode, fin, today),
            "jours_comparables": nb_jours_calendaires,
            "en_cours": debut <= today < fin_periode,
            "future": today < debut,
        },
        "nb_jours_valides": nb_valides,
        "nb_jours_exclus": nb_exclus,
        "nb_jours_sans_donnees": nb_sans_donnees,
        "energie_produite_kwh": round(energie_produite, 1),
        "energie_attendue_kwh": round(energie_attendue, 1),
        "performance": round(performance, 3) if performance is not None else None,
        "reference_pvsyst_mois_kwh": round(reference_pvsyst_kwh(period, month), 1),
        "co2_evite_kg": round(co2, 1),
        "alarmes_onduleur": sum(len(m["alerts"]) for m in inverter_metrics),
        "alertes_performance": alertes_perf,
        "jours_en_alerte_performance": jours_alerte,
        "economies_dt": round(energie_produite * STEG_TARIFF, 2),
        "arbres_equivalents": int(round(co2 * TREES_PER_KG_CO2)),
        "summary": {
            "max_power_w": round(max_power_w, 1),
            "avg_temp_c": round(somme_temp / nb_temp, 1) if nb_temp else None,
        },
        "inverter_metrics": inverter_metrics,
        "daily_production": jours_rapport,
    }
