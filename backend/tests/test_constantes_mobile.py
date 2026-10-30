"""Les constantes PVsyst recopiées côté mobile (mobile/src/pvsyst.ts) doivent
rester identiques à celles du backend (app/reference.py)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.reference import P_CRETE_KWC, PVSYST_MENSUEL  # noqa: E402

PVSYST_TS = os.path.join(os.path.dirname(__file__), "..", "..", "mobile", "src", "pvsyst.ts")


def _source_mobile() -> str:
    with open(PVSYST_TS, encoding="utf-8") as f:
        return f.read()


def test_puissance_crete_identique():
    m = re.search(r"P_CRETE_W\s*=\s*([\d_]+)", _source_mobile())
    assert m, "P_CRETE_W introuvable dans mobile/src/pvsyst.ts"
    assert int(m.group(1).replace("_", "")) == round(P_CRETE_KWC * 1000)


def test_bilans_mensuels_identiques():
    lignes = re.findall(r"^\s*(\d+):\s*\[([^\]]+)\]", _source_mobile(), re.M)
    mobile = {int(mois): tuple(float(v) for v in vals.split(",")) for mois, vals in lignes}
    assert mobile == PVSYST_MENSUEL


SOLAR_SIM_H = os.path.join(os.path.dirname(__file__), "..", "..", "include", "solar_sim.h")


def test_constantes_firmware_identiques():
    """Le simulateur ESP32 (include/solar_sim.h) utilise les mêmes PR, E_Grid et P_crête."""
    with open(SOLAR_SIM_H, encoding="utf-8") as f:
        src = f.read()

    def tableau(nom):
        m = re.search(nom + r"\[12\]\s*=\s*\{([^}]+)\}", src)
        assert m, f"{nom} introuvable dans include/solar_sim.h"
        return [float(v) for v in m.group(1).split(",")]

    assert tableau("PVSYST_PR") == [PVSYST_MENSUEL[m][3] for m in range(1, 13)]
    assert tableau("PVSYST_EGRID_KWH") == [PVSYST_MENSUEL[m][2] * 1000 for m in range(1, 13)]
    m = re.search(r"P_CRETE_W\s*=\s*([\d.]+)", src)
    assert m and float(m.group(1)) == P_CRETE_KWC * 1000
