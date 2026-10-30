"""Vraisemblance des énergies horaires : heure « incoherente », jour « incoherent »."""
import os, sqlite3, sys
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.performance_horaire import (  # noqa: E402
    HeureMesuree, appliquer_vraisemblance, bilan_journalier, choisir_methode,
    energie_attendue_de, heure_incoherente, nb_heures_incoherentes,
)
from app.reference import synthese  # noqa: E402
from test_methode_combinee import G, G_INC, J, METEO, _base, _jour, _journee, _ts  # noqa: E402

N = 7200


def _heures(energies=None):
    """Journée claire du 17/10, production = attendue, sauf énergies imposées {heure: kWh}."""
    out = []
    for h in range(24):
        e = energie_attendue_de(J.month, HeureMesuree(G[h], 0, None, None, g_inc_wm2=G_INC[h]))
        e = (energies or {}).get(h, e)
        out.append(HeureMesuree(G[h], N, e, e * 1000.0, g_inc_wm2=G_INC[h]))
    return out


def test_heure_incoherente_seuils():
    assert heure_incoherente(17.7, 2.46, 193.0) is True          # cas réel du 17/10, 16 h
    assert heure_incoherente(11.9, 11.0, 900.0) is True          # > 1,1 × 10,8 kWh
    assert heure_incoherente(11.8, 11.0, 900.0) is False
    assert heure_incoherente(6.1, 2.0, 250.0) is True            # > 3 × attendue, G ≥ 200
    assert heure_incoherente(6.1, 2.0, 150.0) is False           # G < 200 : critère ignoré
    assert heure_incoherente(5.9, 2.0, 250.0) is False
    assert heure_incoherente(None, 2.0, 500.0) is False


def test_17_7_kwh_en_une_heure_jour_incoherent():
    heures = _heures({16: 17.7})
    assert nb_heures_incoherentes(J, heures) == 1
    jour = appliquer_vraisemblance(choisir_methode(bilan_journalier(J, heures), 80.0, sum(G) / 1000), heures)
    assert jour.etat == "incoherent" and jour.heures_incoherentes == 1
    # Exclu de l'alerte, de la perte et du nettoyage comme tout jour « à vérifier »
    res = synthese([jour])
    assert res["perte_estimee_kwh"] == 0.0 and res["jours_sous_seuil"] == 0


def test_jour_sain_non_modifie():
    heures = _heures()
    jour = appliquer_vraisemblance(choisir_methode(bilan_journalier(J, heures), 50.0, sum(G) / 1000), heures)
    assert jour.heures_incoherentes == 0 and jour.etat != "incoherent"


def test_route_saut_de_e_day_jour_incoherent(tmp_path, monkeypatch):
    """Route : saut de 17,7 kWh de e_day pendant l'heure de 16 h → jour « incoherent »,
    même en méthode horaire (installation arrêtée le matin)."""
    client, db = _base(tmp_path, monkeypatch, METEO)
    _journee(db, marche=range(9, 17))
    con = sqlite3.connect(db)
    con.execute("UPDATE readings SET e_day = e_day + 17.7 WHERE ts >= ?", (_ts(J, 16, 1800),))
    con.commit(); con.close()
    _, j = _jour(client)
    assert j["methode"] == "horaire" and j["etat"] == "incoherent" and j["heures_incoherentes"] == 1


# ── Point 3 : conclusion fondée sur les jours valides ────────────────────────

def test_dernier_jour_valide_et_message():
    from datetime import date
    from app.reference import JourPerformance
    def jour(i, r, etat):
        return JourPerformance(date=(date(2026, 10, 12) + timedelta(i)).isoformat(),
                               energie_mesuree_kwh=50 * r, energie_attendue_kwh=50.0,
                               irradiation_kwh_m2=None, mode="irradiance", r=r, etat=etat)
    # 16/10 valide (0,88), puis 17/10 incohérent et 18/10 insuffisant
    res = synthese([jour(3, 0.97, "normal"), jour(4, 0.88, "anomalie"),
                    jour(5, 7.2, "incoherent"), jour(6, 0.72, "fonctionnement_insuffisant")])
    assert res["dernier_jour_valide"] == {"date": "2026-10-16", "r": 0.88, "etat": "anomalie",
                                          "methode": "journaliere"}
    assert res["message_jours_valides"].startswith("Dernier jour valide sous 90 %")
    assert res["message"].startswith("Dernier jour : fonctionnement insuffisant")   # inchangé
    # Aucun jour valide
    res = synthese([jour(5, 7.2, "incoherent"), jour(6, 0.72, "fonctionnement_insuffisant")])
    assert res["dernier_jour_valide"] is None
    assert res["message_jours_valides"] == "Pas encore de journée valide."
    # Alerte : même message que la règle existante
    res = synthese([jour(i, 0.85, "anomalie") for i in range(3)] + [jour(3, 1.3, "incoherent")])
    assert res["alerte_performance"] is True
    assert res["message_jours_valides"] == res["message"]
