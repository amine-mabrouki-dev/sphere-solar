from typing import List, Optional
from pydantic import BaseModel


# ── MQTT ingest ──────────────────────────────────────────────────────────────

class TelemetryPayload(BaseModel):
    site_id: int
    inv:     str
    ts:      int
    pv_v:    Optional[float] = None
    pv_i:    Optional[float] = None
    pv2_v:   Optional[float] = None   # entrée PV 2 (absente des anciens messages → null)
    pv2_i:   Optional[float] = None
    pv_p:    Optional[float] = None
    ac_v:    Optional[float] = None
    ac_i:    Optional[float] = None
    freq:    Optional[float] = None
    e_day:   Optional[float] = None
    e_total: Optional[float] = None
    batt_v:  Optional[float] = None
    batt_i:  Optional[float] = None
    batt_soc: Optional[int] = None
    temp:    Optional[float] = None
    alarm:   Optional[int]   = None


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


# ── Installations / inverters ─────────────────────────────────────────────────

class InstallationOut(BaseModel):
    id:       int
    name:     str
    location: Optional[str] = None

class InverterOut(BaseModel):
    id:     int
    serial: str
    model:  Optional[str] = None


# ── Metrics ───────────────────────────────────────────────────────────────────

class LatestMetricsOut(BaseModel):
    inverter_id: int
    ts:          Optional[int]   = None
    pv_v:        Optional[float] = None
    pv_i:        Optional[float] = None
    pv2_v:       Optional[float] = None
    pv2_i:       Optional[float] = None
    pv_p:        Optional[float] = None
    ac_v:        Optional[float] = None
    ac_i:        Optional[float] = None
    freq:        Optional[float] = None
    e_day:       Optional[float] = None
    e_total:     Optional[float] = None
    batt_v:      Optional[float] = None
    batt_i:      Optional[float] = None
    batt_soc:    Optional[int]   = None
    temp:        Optional[float] = None
    alarm:       Optional[int]   = None
    updated_at:  Optional[int]   = None

class ReadingOut(BaseModel):
    id:      int
    ts:      int
    pv_v:    Optional[float] = None
    pv_i:    Optional[float] = None
    pv2_v:   Optional[float] = None   # entrée PV 2 (absente des anciens messages → null)
    pv2_i:   Optional[float] = None
    pv_p:    Optional[float] = None
    ac_v:    Optional[float] = None
    ac_i:    Optional[float] = None
    freq:    Optional[float] = None
    e_day:   Optional[float] = None
    e_total: Optional[float] = None
    batt_v:  Optional[float] = None
    batt_i:  Optional[float] = None
    batt_soc: Optional[int] = None
    temp:    Optional[float] = None
    alarm:   Optional[int]   = None


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertOut(BaseModel):
    id:          int
    inverter_id: int
    code:        int
    message:     Optional[str] = None
    raised_at:   int
    cleared_at:  Optional[int] = None


# ── Commands ──────────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    action:       str
    set_interval: Optional[float] = None   # secondes (ex. 0.5)


# ── Assistant / forecast (Ollama) ─────────────────────────────────────────────

class ForecastResponse(BaseModel):
    """Prévision de demain (app.prevision) ; seule l'explication vient du modèle."""
    date:                          str            # demain, JJ/MM
    prevision_kwh:                 float
    fourchette_min_kwh:            float
    fourchette_max_kwh:            float
    marge_pct:                     int            # demi-largeur de la fourchette (%)
    energie_attendue_kwh:          float          # avant la performance actuelle
    irradiation_prevue_kwh_m2:     Optional[float] = None   # None : météo indisponible
    couverture_nuageuse_prevue_pct: Optional[float] = None
    performance_utilisee:          float
    performance_mesuree:           bool
    nb_jours_valides:              int
    source_meteo:                  str
    remarques:                     List[str] = []
    explication:                   str

class ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]

class ChatResponse(BaseModel):
    reply: str


# ── Rapports (GET /installations/{id}/report-data, app.report) ────────────────
# Même format que le type SyntheseRapport de mobile/src/rapport.ts.

class PeriodeRapport(BaseModel):
    type:              str            # "month" ou "year"
    annee:             int
    mois:              Optional[int] = None
    debut:             str            # AAAA-MM-JJ : premier jour de la période
    fin:               str            # AAAA-MM-JJ : dernier jour comparable (dernier
                                      # jour de la période s'il n'y en a aucun)
    libelle:           str            # « Du 1er au 19 octobre 2026 »
    jours_comparables: int            # jours complets passés de la période
    en_cours:          bool
    future:            bool

class JourRapport(BaseModel):
    date:                 str         # AAAA-MM-JJ, heure locale
    onduleur:             str
    etat:                 str
    valide:               bool
    r:                    float
    energie_mesuree_kwh:  float
    energie_attendue_kwh: float
    methode:              str

class AlarmeRapport(BaseModel):
    id:         int
    code:       int
    message:    Optional[str] = None
    raised_at:  int
    cleared_at: Optional[int] = None

class OnduleurRapport(BaseModel):
    id:                   int
    serial:               str
    model:                Optional[str] = None
    energie_produite_kwh: float
    max_power_w:          float
    alertes_performance:  int
    alerts:               List[AlarmeRapport] = []

class InstallationRapport(BaseModel):
    id:       int
    name:     str
    location: Optional[str] = None

class OnduleurInstallation(BaseModel):
    id:     int
    serial: str
    model:  Optional[str] = None

class ResumeRapport(BaseModel):
    max_power_w: float
    avg_temp_c:  Optional[float] = None

class SyntheseRapport(BaseModel):
    """Synthèse d'un mois ou d'une année (onglet Rapports et rapport PDF)."""
    installation:                InstallationRapport
    inverters:                   List[OnduleurInstallation]
    periode:                     PeriodeRapport
    nb_jours_valides:            int
    nb_jours_exclus:             int
    nb_jours_sans_donnees:       int
    energie_produite_kwh:        float
    energie_attendue_kwh:        float
    performance:                 Optional[float] = None   # None : aucun jour valide
    reference_pvsyst_mois_kwh:   float
    co2_evite_kg:                float
    alarmes_onduleur:            int
    alertes_performance:         int
    jours_en_alerte_performance: int
    economies_dt:                float
    arbres_equivalents:          int
    summary:                     ResumeRapport
    inverter_metrics:            List[OnduleurRapport]
    daily_production:            List[JourRapport]
