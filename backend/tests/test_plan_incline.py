"""Tests de la conversion horaire vers le plan incliné (app/plan_incline.py)."""
import os, sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import plan_incline as pi  # noqa: E402

RAPPORT_OCTOBRE = 170.2 / 131.2          # GlobInc / GlobHor PVsyst d'octobre


def _midi_solaire(d: date) -> float:
    """Heure locale (UTC+1) du midi solaire à Metlaoui."""
    return 12.0 - (4.0 * (pi.LONGITUDE - 15.0) + pi.equation_du_temps(d)) / 60.0


def test_incidence_nulle_a_midi_solaire_quand_declinaison_egale_latitude_moins_30():
    # Condition géométrique : δ = φ − β et ω = 0 → incidence nulle
    assert abs(pi.cos_incidence(pi.LATITUDE - 30.0, 0.0) - 1.0) < 1e-12
    # Dates où δ ≈ +4,3° : vers le 1er avril et le 11 septembre
    for d in (date(2026, 4, 1), date(2026, 9, 11)):
        assert abs(pi.declinaison(d) - (pi.LATITUDE - 30.0)) < 0.6
        pos = pi.position_soleil(d, _midi_solaire(d))
        assert abs(pos["angle_horaire"]) < 1e-9 and pos["incidence"] < 0.6
    # Le 10 octobre, δ ≈ −7,7° : l'incidence à midi vaut ≈ 12°, pas 0
    d = date(2026, 10, 10)
    assert 11.0 < pi.position_soleil(d, _midi_solaire(d))["incidence"] < 13.0


def test_position_soleil_coherente():
    d = date(2026, 6, 21)
    pos = pi.position_soleil(d, _midi_solaire(d))
    assert abs(pos["hauteur"] - (90 - pi.LATITUDE + 23.45)) < 0.2      # ≈ 79,1° au solstice
    assert pi.position_soleil(d, 0.5)["hauteur"] < 0                     # nuit
    assert abs(pi.equation_du_temps(date(2026, 11, 3)) - 16.4) < 0.6     # maximum de novembre


def test_journee_claire_octobre_rapport_pvsyst_a_2_pourcent():
    """Grâce au calage : Σ G_inc horaire ÷ Σ G ≈ 170,2 / 131,2 à 2 % près pour
    une journée claire du milieu d'octobre."""
    for jour in range(12, 19):
        d = date(2026, 10, jour)
        g, dif = pi.journee_claire(d)
        inc = pi.irradiance_inclinee_horaire(d, g, dif)
        assert abs(sum(inc) / sum(g) / RAPPORT_OCTOBRE - 1) < 0.02, d
    # Le 15 (journée de calage) : égalité
    d = date(2026, 10, 15)
    g, dif = pi.journee_claire(d)
    assert abs(sum(pi.irradiance_inclinee_horaire(d, g, dif)) / sum(g) - RAPPORT_OCTOBRE) < 1e-9


def test_jamais_negatif_et_zero_la_nuit():
    d0 = date(2026, 1, 1)
    for k in range(0, 365, 7):
        d = d0 + timedelta(days=k)
        g, dif = pi.journee_claire(d)
        inc = pi.irradiance_inclinee_horaire(d, g, dif)
        assert all(v >= 0 for v in inc)
        assert inc[0] == 0 and inc[2] == 0 and inc[23] == 0          # nuit
    # Valeurs absentes ou incohérentes d'Open-Meteo
    d = date(2026, 10, 15)
    assert pi.irradiance_inclinee_horaire(d, [None] * 24, [None] * 24) == [0.0] * 24
    assert pi.irradiance_inclinee_isotrope(-3.0, 0.0, d, 12.5) == 0.0
    # Diffuse supérieure à la globale : bornée, pas de directe négative
    assert pi.irradiance_inclinee_isotrope(100.0, 150.0, d, 12.5) >= 0


def test_soleil_bas_composante_directe_ignoree_et_rapport_borne():
    d = date(2026, 10, 15)
    # Instant où le soleil est entre 0 et 5° (lever) : seulement diffuse + albédo
    h = next(x / 20 for x in range(100, 180) if 0 < pi.position_soleil(d, x / 20)["hauteur"] < 5)
    attendu = 50 * (1 + pi.math.cos(pi.math.radians(30))) / 2 \
        + 80 * pi.ALBEDO * (1 - pi.math.cos(pi.math.radians(30))) / 2
    assert abs(pi.irradiance_inclinee_isotrope(80.0, 50.0, d, h) - attendu) < 1e-9
    # Rapport cos(incidence)/cos(zénith) limité à 5 : G_inc ≤ 5 × G + G
    for x in range(24):
        assert pi.irradiance_inclinee_isotrope(100.0, 0.0, d, x + 0.5) <= 5 * 100.0 + 100.0


def test_methode_horaire_utilise_l_irradiance_inclinee():
    """Avec g_inc_wm2, l'énergie attendue d'une heure vaut 10,8 × G_inc/1000 × PR ;
    sans (diffuse absente), l'ancien calcul G × GlobInc/GlobHor est gardé."""
    from app.performance_horaire import HeureMesuree, energie_attendue_de
    from app.reference import facteur_inclinaison, pr_reference
    h = HeureMesuree(500.0, 7200, 5.0, 5000.0, g_inc_wm2=650.0)
    assert abs(energie_attendue_de(10, h) - 10.8 * 0.65 * pr_reference(10)) < 1e-12
    h.g_inc_wm2 = None
    assert abs(energie_attendue_de(10, h) - 10.8 * 0.5 * facteur_inclinaison(10) * pr_reference(10)) < 1e-12
