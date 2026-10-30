"""Tests de la méthode horaire : performance (heures de fonctionnement) et
disponibilité. Aucun appel réseau : Open-Meteo est simulé."""
import os, sqlite3, sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.performance_horaire import (  # noqa: E402
    HeureMesuree, bilan_journalier, energie_attendue_heure, etat_heure, mesures_attendues_par_heure,
)
from app.reference import facteur_inclinaison, pr_reference, synthese  # noqa: E402
from test_performance import AUJ, TZ_TUNIS, _ROUTE, _module_route  # noqa: E402

# Irradiance horizontale d'une journée claire d'octobre à Metlaoui (W/m²),
# heure locale [h ; h+1[ : 11 heures à ≥ 100 W/m² (7 h → 18 h), 70 et 60 W/m²
# à l'aube et au crépuscule.
G = [0.0] * 24
for _h, _g in {6: 70, 7: 180, 8: 380, 9: 560, 10: 690, 11: 760, 12: 780,
               13: 740, 14: 640, 15: 480, 16: 300, 17: 120, 18: 60}.items():
    G[_h] = float(_g)

JOUR = date(2026, 10, 15)
N = 7200                        # mesures par heure (ESP32 à 0,5 s)


def _heures(marche=range(24), facteur=1.0, coupure=(), mois=10):
    """24 heures : installation en marche aux heures `marche` (production =
    attendue × facteur), à l'arrêt (0 W) sinon, ESP32 coupé aux heures `coupure`."""
    heures = []
    for h in range(24):
        if h in coupure:
            heures.append(HeureMesuree(G[h], 0, None, None))
            continue
        e = energie_attendue_heure(mois, G[h]) * facteur if h in marche else 0.0
        heures.append(HeureMesuree(G[h], N, e, e * 1000.0))
    return heures


# ── Fonctions pures ──────────────────────────────────────────────────────────

def test_energie_attendue_heure():
    e = energie_attendue_heure(10, 600.0)
    assert abs(e - 10.8 * 0.6 * facteur_inclinaison(10) * pr_reference(10)) < 1e-12
    assert energie_attendue_heure(10, None) == 0.0 and energie_attendue_heure(10, -3.0) == 0.0


def test_etat_heure():
    assert etat_heure(30.0, N, N, 500.0, 400.0) == "nuit"
    assert etat_heure(None, N, N, 500.0, 400.0) == "nuit"
    assert etat_heure(500.0, N // 2 - 1, N, 3000.0, 3000.0) == "donnees_manquantes"   # < 50 %
    assert etat_heure(500.0, N // 2, N, 3000.0, 3000.0) == "fonctionnement"
    assert etat_heure(500.0, N, N, 59.0, 3000.0) == "arret"                           # < 2 %
    assert etat_heure(500.0, N, N, 60.0, 3000.0) == "fonctionnement"
    # Puissance nulle sous une lumière faible (50 – 100 W/m²) : pas un arrêt constaté
    assert etat_heure(80.0, N, N, 0.0, 700.0) == "faible_ensoleillement"
    assert etat_heure(100.0, N, N, 0.0, 900.0) == "arret"


def test_mesures_attendues_par_heure():
    assert mesures_attendues_par_heure([0, 5569, 5347, 1594]) == 5569   # cadence réelle observée
    assert mesures_attendues_par_heure([6, 6, 1]) == 6                  # démo : une mesure / 10 min
    assert mesures_attendues_par_heure([9000]) == 7200                  # plafond : 0,5 s
    assert mesures_attendues_par_heure([]) == 0


def test_journee_complete_saine():
    j = bilan_journalier(JOUR, _heures())
    assert abs(j.r - 1.0) < 1e-3 and j.etat == "normal" and j.methode == "horaire"
    assert j.disponibilite == 100.0 and j.heures_arret == 0 and j.heures_donnees_manquantes == 0
    assert j.heures_fonctionnement == 13 and j.energie_perdue_arret_kwh == 0.0
    assert abs(j.energie_attendue_kwh - sum(energie_attendue_heure(10, g) for g in G)) < 0.01


def test_marche_de_9h_a_15h_saine():
    """En marche de 9 h à 15 h seulement : r ≈ 1, disponibilité ≈ 55 %
    (6 h sur 11 h), énergie perdue à l'arrêt > 0, pas d'alerte."""
    j = bilan_journalier(JOUR, _heures(marche=range(9, 15)))
    assert abs(j.r - 1.0) < 1e-3 and j.etat == "normal"
    assert j.heures_fonctionnement == 6 and j.heures_arret == 5
    assert abs(j.disponibilite - 54.5) < 0.1
    perdu = sum(energie_attendue_heure(10, G[h]) for h in (7, 8, 15, 16, 17))
    assert j.energie_perdue_arret_kwh > 0 and abs(j.energie_perdue_arret_kwh - perdu) < 0.01
    # Trois jours de suite ainsi : aucune alerte de performance
    res = synthese([bilan_journalier(JOUR + timedelta(i), _heures(marche=range(9, 15)))
                    for i in range(3)])
    assert res["alerte_performance"] is False and res["jours_sous_seuil"] == 0
    assert res["perte_estimee_kwh"] == 0.0 and res["energie_perdue_arret_kwh"] > 0
    assert res["message"] == "Production conforme à la référence."


def test_marche_de_9h_a_15h_avec_12_pourcent_de_poussiere():
    j = bilan_journalier(JOUR, _heures(marche=range(9, 15), facteur=0.88))
    assert abs(j.r - 0.88) < 1e-3 and j.etat == "anomalie"
    assert abs(j.disponibilite - 54.5) < 0.1
    # Trois jours de suite : alerte (règle existante appliquée à r horaire)
    res = synthese([bilan_journalier(JOUR + timedelta(i), _heures(range(9, 15), 0.88))
                    for i in range(3)])
    assert res["alerte_performance"] is True and res["jours_sous_seuil"] == 3


def test_esp32_coupe_3_heures_sans_effet_sur_r():
    j = bilan_journalier(JOUR, _heures(coupure=(10, 11, 12)))
    assert j.heures_donnees_manquantes == 3 and j.heures_fonctionnement == 10
    assert abs(j.r - 1.0) < 1e-3 and j.etat == "normal" and j.disponibilite == 100.0
    # Avec de la poussière, r reste celui des heures mesurées
    j = bilan_journalier(JOUR, _heures(facteur=0.88, coupure=(10, 11, 12)))
    assert abs(j.r - 0.88) < 1e-3


def test_moins_de_3_heures_de_fonctionnement():
    j = bilan_journalier(JOUR, _heures(marche=range(11, 13)))
    assert j.heures_fonctionnement == 2 and j.etat == "fonctionnement_insuffisant"
    # Exclu de l'alerte : ne prolonge ni n'interrompt une série d'anomalies
    jours = [bilan_journalier(JOUR + timedelta(i), _heures(facteur=0.85)) for i in range(3)]
    jours.append(bilan_journalier(JOUR + timedelta(3), _heures(marche=range(11, 13), facteur=1.2)))
    res = synthese(jours)
    assert res["alerte_performance"] is True and res["jours_sous_seuil"] == 3
    assert res["jours"][-1]["etat"] == "fonctionnement_insuffisant"
    assert res["message"].startswith("Production inférieure à 90 %")
    # Seul en dernier jour : message dédié, pas de « conforme »
    res = synthese([bilan_journalier(JOUR, _heures()),
                    bilan_journalier(JOUR + timedelta(1), _heures(marche=range(11, 13)))])
    assert res["message"].startswith("Dernier jour : fonctionnement insuffisant")


def test_heure_sans_puissance_ni_energie_est_manquante():
    heures = _heures()
    heures[12] = HeureMesuree(G[12], N, None, None)       # mesures reçues mais vides
    j = bilan_journalier(JOUR, heures)
    assert j.heures_donnees_manquantes == 1 and abs(j.r - 1.0) < 1e-3


# ── Route /performance (SQLite + Open-Meteo simulé) ──────────────────────────

def _ts_local(d: date, h: int, mi: int = 0, s: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, h, mi, s, tzinfo=TZ_TUNIS).timestamp())


def _base(tmp_path, monkeypatch, horaire, maintenant=datetime(2026, 10, 18, 12, 0, tzinfo=TZ_TUNIS), irr=None):
    perf, client = _module_route()
    db_path = tmp_path / "h.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE readings (id INTEGER PRIMARY KEY, inverter_id INT, ts INT, "
                "pv_p REAL, e_day REAL, alarm INT)")
    con.commit(); con.close()
    _ROUTE["db"] = db_path

    async def fausse_meteo(days): return perf.MeteoSite(horaire=horaire, irr=irr or {})
    monkeypatch.setattr(perf, "_meteo", fausse_meteo)
    monkeypatch.setattr(perf, "_maintenant", lambda: maintenant)
    return perf, client, db_path


def _journee_esp32(db_path, d, marche=range(24), facteur=1.0, coupure=(), pas_s=10):
    """Télémétrie d'une journée toutes les `pas_s` secondes : pv_p constant dans
    l'heure, e_day cumulé depuis minuit ; aucune mesure aux heures `coupure`."""
    con = sqlite3.connect(db_path)
    cumul = 0.0
    for h in range(24):
        e_h = energie_attendue_heure(d.month, G[h]) * facteur if h in marche else 0.0
        for s in range(0, 3600, pas_s):
            if h not in coupure:
                con.execute("INSERT INTO readings (inverter_id, ts, pv_p, e_day, alarm) "
                            "VALUES (1, ?, ?, ?, 0)",
                            (_ts_local(d, h) + s, e_h * 1000.0, cumul + e_h * s / 3600))
        cumul += e_h
    con.commit(); con.close()


def test_route_horaire_marche_9h_15h_et_coupure_esp32(tmp_path, monkeypatch):
    j1, j2 = AUJ - timedelta(days=2), AUJ - timedelta(days=1)
    perf, client, db_path = _base(tmp_path, monkeypatch, {j1.isoformat(): G, j2.isoformat(): G})
    _journee_esp32(db_path, j1, marche=range(9, 15))          # arrêtée hors 9 h – 15 h
    _journee_esp32(db_path, j2, coupure=(10, 11, 12))         # ESP32 coupé 3 h
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert body["mode"] == "combinee"
    a, b = body["jours"]
    assert a["methode"] == "horaire" and abs(a["r"] - 1.0) < 0.02 and a["etat"] == "normal"
    assert a["heures_fonctionnement"] == 6 and a["heures_arret"] == 5
    assert a["heures_soleil_utile"] == 11
    assert abs(a["disponibilite"] - 54.5) < 0.1 and a["energie_perdue_arret_kwh"] > 0
    assert b["heures_donnees_manquantes"] == 3 and abs(b["r"] - 1.0) < 0.02
    assert b["disponibilite"] == 100.0 and b["etat"] == "normal"
    assert body["alerte_performance"] is False
    assert body["energie_perdue_arret_kwh"] == round(a["energie_perdue_arret_kwh"], 1)


def test_route_horaire_poussiere_12_pourcent(tmp_path, monkeypatch):
    d = AUJ - timedelta(days=1)
    perf, client, db_path = _base(tmp_path, monkeypatch, {d.isoformat(): G})
    _journee_esp32(db_path, d, marche=range(9, 15), facteur=0.88)
    j = client.get("/inverters/1/performance?days=7&mode=auto").json()["jours"][-1]
    assert abs(j["r"] - 0.88) < 0.02 and j["etat"] == "anomalie"


def test_route_sans_horaire_methode_journaliere(tmp_path, monkeypatch):
    """Open-Meteo sans données horaires → méthode journalière, "mode": "journalier"."""
    d = AUJ - timedelta(days=1)
    perf, client, db_path = _base(tmp_path, monkeypatch, {})
    _journee_esp32(db_path, d, pas_s=60)
    body = client.get("/inverters/1/performance?days=7&mode=auto").json()
    assert body["mode"] == "journaliere"
    j = body["jours"][-1]
    assert j["methode"] == "journaliere" and j["disponibilite"] is None
    assert j["heures_fonctionnement"] is None


def test_irradiance_horaire_heure_precedente():
    """Open-Meteo : la valeur datée 10:00 couvre 09:00 – 10:00 (heure locale 9)."""
    perf, _ = _module_route()
    temps = [f"2026-10-18T{h:02d}:00" for h in range(24)] + ["2026-10-19T00:00", "2026-10-19T01:00"]
    valeurs = list(range(24)) + [99, 98]
    horaire = perf.irradiance_horaire({"time": temps, "shortwave_radiation": valeurs})
    assert horaire["2026-10-18"][9] == 10 and horaire["2026-10-18"][23] == 99
    # 17/10 et 19/10 : une seule heure renseignée chacun → jours écartés
    assert "2026-10-17" not in horaire and "2026-10-19" not in horaire


def test_diffuse_horaire_heure_precedente():
    """Diffuse : même décalage. Valeur datée T → heure qui commence à T − 1 h."""
    from app.performance_horaire import diffuse_horaire
    temps = [f"2026-10-18T{h:02d}:00" for h in range(1, 24)] + ["2026-10-19T00:00"]
    hourly = {"time": temps, "diffuse_radiation": [10 * h for h in range(1, 25)]}
    d = diffuse_horaire(hourly)["2026-10-18"]
    assert d[0] == 10 and d[12] == 130 and d[23] == 240     # 13:00 → heure 12 ; 00:00 du 19 → 23
    assert diffuse_horaire({"time": temps}) == {}             # absente : rien


def test_route_horaire_scenario_de_demonstration(tmp_path, monkeypatch):
    """Scénario de démo (une mesure / 10 min, e_day seul, réparti selon
    l'irradiance horaire) : journée complète → méthode journalière, r prévu."""
    import importlib
    seed = importlib.import_module("scripts.seed_performance_demo")
    d = AUJ - timedelta(days=1)
    perf, client, db_path = _base(tmp_path, monkeypatch, {d.isoformat(): G},
                                  irr={d.isoformat(): sum(G) / 1000})
    e_att_jour = sum(energie_attendue_heure(d.month, g) for g in G)
    serie = seed.mesures_journee(d, 0.90 * e_att_jour, G)
    assert max(e for _, e in serie) == round(0.90 * e_att_jour, 2)
    con = sqlite3.connect(db_path)
    con.executemany("INSERT INTO readings (inverter_id, ts, e_day, alarm) VALUES (1, ?, ?, 0)", serie)
    con.commit(); con.close()
    j = client.get("/inverters/1/performance?days=7&mode=auto").json()["jours"][-1]
    assert j["methode"] == "journaliere" and j["heures_donnees_manquantes"] == 0
    assert j["heures_fonctionnement"] == 13 and j["disponibilite"] == 100.0
    assert abs(j["r"] - 0.90) < 0.01
