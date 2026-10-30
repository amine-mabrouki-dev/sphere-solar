/**
 * HTML du rapport PDF (imprimé par src/reportGenerator.ts avec expo-print).
 * Sans dépendance Expo : testable sous Node (src/__tests__/rapportHtml.test.ts).
 */
import { dateTunis } from './heure';
import {
  entierFr, ligneJoursExclus, mentionReferencePvsyst, niveauPerformance, nombreFr, performancePct, sousTitrePeriode,
} from './rapport';
import type { JourRapport, SyntheseRapport } from './rapport';

// Mêmes chiffres et mêmes libellés que l'onglet Rapports (src/rapport.ts)
const CLASSE_NIVEAU = { normal: 'excellent', vigilance: 'good', anomalie: 'warning' } as const;
const LIBELLE_ETAT: Record<string, string> = {
  normal: 'Normal', vigilance: 'Vigilance', anomalie: 'Anomalie',
  incoherent: 'À vérifier (exclu)', incomplete: 'Incomplet (exclu)',
  fonctionnement_insuffisant: 'Fonctionnement insuffisant (exclu)',
};

function esc(s: unknown): string {
  if (s === null || s === undefined) return '—';
  return String(s);
}

/** « 2026-10-05 » → « 05/10/2026 » */
function formatDate(iso: string): string {
  const [a, m, j] = iso.split('-');
  return `${j}/${m}/${a}`;
}

function ligneJour(d: JourRapport): string {
  return `
          <tr${d.valide ? '' : ' style="color: #999;"'}>
            <td>${formatDate(d.date)}</td>
            <td>${LIBELLE_ETAT[d.etat] ?? d.etat}</td>
            <td>${nombreFr(d.energie_mesuree_kwh)}</td>
            <td>${nombreFr(d.energie_attendue_kwh)}</td>
            <td>${d.valide ? performancePct(d.r) : '—'}</td>
          </tr>`;
}

export function htmlRapport(
  reportData: SyntheseRapport,
  period: 'month' | 'year' = 'month',
  year?: number,
  month?: number,
): string {
  const inst = reportData.installation;
  // Le nom de l'installation contient le nom du client : il n'apparaît pas
  // dans le rapport, remplacé par un libellé neutre.
  const NOM_SITE = 'Installation PV — Metlaoui';
  const d = reportData;
  const s: Partial<SyntheseRapport["summary"]> = reportData.summary ?? {};
  const inverters = reportData.inverter_metrics || [];
  // Mois : tous les jours ; année : les 31 derniers jours comparés
  const daily = (reportData.daily_production || []).slice(-31);
  const niveau = niveauPerformance(d.performance);
  const nbAlarmes = d.alarmes_onduleur;
  // Rythme journalier sur les jours valides, pour les estimations annuelles
  const parJour = d.nb_jours_valides > 0 ? 365 / d.nb_jours_valides : 0;

  const periodLabel = period === 'month' 
    ? `${String(month || new Date().getMonth() + 1).padStart(2, '0')}/${year || new Date().getFullYear()}`
    : String(year || new Date().getFullYear());

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    color: #333;
    background: #f5f5f5;
    line-height: 1.6;
  }
  .page { page-break-after: always; }
  .container { max-width: 210mm; margin: 0 auto; background: white; }
  
  /* ─── Header & Cover ─── */
  .cover {
    background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
    color: white;
    padding: 40px;
    text-align: center;
    border-bottom: 8px solid #fbbf24;
  }
  .cover h1 { font-size: 32px; margin-bottom: 10px; }
  .cover .subtitle { font-size: 18px; opacity: 0.9; margin-bottom: 30px; }
  .cover .meta { font-size: 12px; opacity: 0.8; }
  
  /* ─── KPI Cards ─── */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
    padding: 30px;
    background: #f8f9fa;
  }
  .kpi-card {
    background: white;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    page-break-inside: avoid;
  }
  .kpi-value { font-size: 28px; font-weight: bold; color: #1e40af; margin: 10px 0; }
  .kpi-label { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi-unit { font-size: 12px; color: #999; }
  .kpi-note { font-size: 10px; color: #666; margin-top: 6px; }
  .kpi-exclus { padding: 0 30px 20px; font-size: 12px; color: #666; background: #f8f9fa; }
  
  /* ─── Sections ─── */
  .section {
    padding: 30px;
    border-bottom: 1px solid #e5e7eb;
  }
  .section h2 {
    font-size: 18px;
    color: #1e3a8a;
    margin-bottom: 15px;
    border-bottom: 3px solid #fbbf24;
    padding-bottom: 10px;
  }
  .section h3 { font-size: 14px; color: #1e40af; margin-top: 15px; margin-bottom: 8px; }
  
  /* ─── Info Grid ─── */
  .info-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
    margin-bottom: 20px;
  }
  .info-item { background: #f9fafb; padding: 15px; border-radius: 6px; border-left: 4px solid #fbbf24; }
  .info-label { font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 4px; }
  .info-value { font-size: 16px; font-weight: bold; color: #1e3a8a; }
  
  /* ─── Performance Badge ─── */
  .performance-badge {
    display: inline-block;
    padding: 10px 20px;
    border-radius: 20px;
    font-weight: bold;
    margin: 10px 0;
  }
  .excellent { background: #dcfce7; color: #166534; }
  .good { background: #fef3c7; color: #92400e; }
  .warning { background: #fee2e2; color: #991b1b; }
  
  /* ─── Tables ─── */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
  }
  th {
    background: #1e3a8a;
    color: white;
    padding: 12px;
    text-align: left;
    font-size: 12px;
    text-transform: uppercase;
    border: none;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid #e5e7eb;
    font-size: 11px;
  }
  tr:nth-child(even) { background: #f9fafb; }
  
  /* ─── Chart/Graph placeholder ─── */
  .chart-placeholder {
    background: #f3f4f6;
    border: 2px dashed #d1d5db;
    border-radius: 8px;
    padding: 40px;
    text-align: center;
    color: #999;
    margin: 20px 0;
  }
  
  /* ─── Alerts/Issues ─── */
  .alert-box {
    border-left: 4px solid #ef4444;
    background: #fef2f2;
    padding: 15px;
    margin: 10px 0;
    border-radius: 4px;
  }
  .alert-box.warning {
    border-left-color: #f59e0b;
    background: #fffbeb;
  }
  .alert-box.success {
    border-left-color: #10b981;
    background: #f0fdf4;
  }
  
  /* ─── Checklist ─── */
  .checklist { list-style: none; }
  .checklist li { padding: 8px 0; padding-left: 25px; position: relative; }
  .checklist li:before {
    content: '✓';
    position: absolute;
    left: 0;
    color: #10b981;
    font-weight: bold;
  }
  
  /* ─── Footer ─── */
  .footer {
    background: #1f2937;
    color: white;
    padding: 20px;
    font-size: 10px;
    text-align: center;
    margin-top: 40px;
  }
  
  /* ─── Page Break ─── */
  @page { size: A4; margin: 10mm; }
  </style>
</head>
<body>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- PAGE 1: COVER & KPI SUMMARY                                         -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="cover">
  <h1>📊 Rapport Solar PV</h1>
  <div class="subtitle">${NOM_SITE}</div>
  <div class="meta">
    <div>Période : ${periodLabel} — ${sousTitrePeriode(d)}</div>
    <div>Rapport généré: ${dateTunis()}</div>
  </div>
  </div>

  <div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Énergie produite</div>
    <div class="kpi-value">${nombreFr(d.energie_produite_kwh)}</div>
    <div class="kpi-unit">kWh</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Énergie attendue (même période)</div>
    <div class="kpi-value">${nombreFr(d.energie_attendue_kwh)}</div>
    <div class="kpi-unit">kWh</div>
    <div class="kpi-note">${mentionReferencePvsyst(d)}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Performance</div>
    <div class="kpi-value">${performancePct(d.performance)}</div>
    <div class="kpi-unit">mesurée ÷ attendue</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">CO₂ évité</div>
    <div class="kpi-value">${nombreFr(d.co2_evite_kg, 0)}</div>
    <div class="kpi-unit">kg (0,50 kg/kWh)</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Alarmes onduleur</div>
    <div class="kpi-value">${entierFr(nbAlarmes)}</div>
    <div class="kpi-unit">levées</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Alertes de performance</div>
    <div class="kpi-value">${entierFr(d.alertes_performance)}</div>
    <div class="kpi-unit">r &lt; 90 % pendant 3 jours</div>
  </div>
  </div>
  <div class="kpi-exclus">${ligneJoursExclus(d.nb_jours_exclus)}</div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- PAGE 2: INFORMATIONS GÉNÉRALES & PERFORMANCES                        -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="section">
  <h2>1️⃣ Informations Générales</h2>
  <div class="info-grid">
    <div class="info-item">
      <div class="info-label">Site</div>
      <div class="info-value">${NOM_SITE}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Adresse</div>
      <div class="info-value">${esc(inst?.location)}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Nombre d'onduleurs</div>
      <div class="info-value">${inverters.length}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Puissance instantanée max</div>
      <div class="info-value">${nombreFr((s.max_power_w ?? NaN) / 1000, 1)} kW</div>
    </div>
    ${inverters.length > 0 ? `
    <div class="info-item">
      <div class="info-label">Onduleur principal</div>
      <div class="info-value">${esc(inverters[0].model || inverters[0].serial)}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Température moyenne</div>
      <div class="info-value">${nombreFr(s.avg_temp_c, 1)} °C</div>
    </div>
    ` : ''}
  </div>
  </div>

  <div class="section">
  <h2>2️⃣ Résumé des Performances</h2>
  <div class="info-grid">
    <div class="info-item">
      <div class="info-label">Énergie produite</div>
      <div class="info-value">${nombreFr(d.energie_produite_kwh)} kWh</div>
    </div>
    <div class="info-item">
      <div class="info-label">Énergie attendue (même période)</div>
      <div class="info-value">${nombreFr(d.energie_attendue_kwh)} kWh</div>
    </div>
    <div class="info-item">
      <div class="info-label">Jours valides</div>
      <div class="info-value">${entierFr(d.nb_jours_valides)}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Jours exclus</div>
      <div class="info-value">${entierFr(d.nb_jours_exclus)}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Puissance maximale atteinte</div>
      <div class="info-value">${nombreFr(s.max_power_w, 0)} W</div>
    </div>
  </div>
  <p style="font-size: 12px; color: #666;">${ligneJoursExclus(d.nb_jours_exclus)}.
    ${mentionReferencePvsyst(d)} (à titre indicatif).</p>
  </div>

  <div class="section">
  <h2>3️⃣ Performance de la période</h2>
  <p style="margin-bottom: 10px;">Énergie produite ÷ énergie attendue (PVsyst et irradiation du jour), sur les mêmes jours valides.</p>
  <div class="performance-badge ${niveau ? CLASSE_NIVEAU[niveau] : 'good'}">
    Performance : ${performancePct(d.performance)}
  </div>
  <p style="margin-top: 10px; font-size: 12px; color: #666;">
    ${niveau === 'normal'
      ? '✓ Production conforme à la référence (au moins 95 %)'
      : niveau === 'vigilance'
      ? '→ Production légèrement inférieure à la référence (90 à 95 %) : à surveiller'
      : niveau === 'anomalie'
      ? '⚠ Production inférieure à 90 % de la référence : vérification ou nettoyage conseillé'
      : 'Aucun jour valide sur la période.'}
  </p>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- PAGE 3: ÉCONOMIES & IMPACT ENVIRONNEMENTAL                            -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="section">
  <h2>4️⃣ Économies Financières (STEG)</h2>
  <p style="margin-bottom: 20px; font-size: 12px; color: #666;">
    Calcul basé sur le tarif STEG: 0.250 DT/kWh
  </p>
  <div class="info-grid">
    <div class="info-item">
      <div class="info-label">Gain sur la période (jours valides)</div>
      <div class="info-value">${nombreFr(d.economies_dt, 2)} DT</div>
    </div>
    <div class="info-item">
      <div class="info-label">À taux actuel (annualisé)</div>
      <div class="info-value">${nombreFr(d.economies_dt * parJour, 2)} DT</div>
    </div>
  </div>
  <div class="alert-box success">
    <strong>💰 ROI:</strong> À ce rythme, votre installation se rentabilise en ${d.economies_dt > 0 && parJour > 0 ? Math.round(15000 / (d.economies_dt * parJour)) : "—"} ans
  </div>
  </div>

  <div class="section">
  <h2>5️⃣ Impact Environnemental</h2>
  <div class="info-grid">
    <div class="info-item">
      <div class="info-label">CO₂ évité</div>
      <div class="info-value">${nombreFr(d.co2_evite_kg, 0)} kg</div>
    </div>
    <div class="info-item">
      <div class="info-label">Équivalent en arbres</div>
      <div class="info-value">${entierFr(d.arbres_equivalents)} 🌳</div>
    </div>
    <div class="info-item">
      <div class="info-label">Équivalent en km voiture</div>
      <div class="info-value">${entierFr(d.co2_evite_kg * 4)} km</div>
    </div>
    <div class="info-item">
      <div class="info-label">Annualisé (estimation)</div>
      <div class="info-value">${nombreFr(d.co2_evite_kg * parJour, 0)} kg/an</div>
    </div>
  </div>
  <div class="alert-box success">
    <strong>🌍 Bravo!</strong> Vous contribuez à un environnement plus propre.
  </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- PAGE 4: HISTORIQUE DE PRODUCTION & ALERTES                            -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="section">
  <h2>6️⃣ Historique de Production</h2>
  <p style="font-size: 12px; color: #666; margin-bottom: 15px;">
    Jours complets de la période, comparés à la référence. Les jours exclus (en gris) ne
    comptent ni dans l'énergie produite ni dans l'énergie attendue.
  </p>
  ${daily.length > 0 ? `
  <table>
    <thead><tr><th>Date</th><th>État</th><th>Mesurée (kWh)</th><th>Attendue (kWh)</th><th>Performance</th></tr></thead>
    <tbody>${daily.map(ligneJour).join('')}
    </tbody>
  </table>
  ` : '<p style="text-align: center; color: #999; padding: 20px;">Aucune journée complète sur la période</p>'}
  </div>

  <div class="section">
  <h2>8️⃣ Historique des Alertes</h2>
  <div class="alert-box ${d.alertes_performance > 0 ? 'warning' : 'success'}">
    <strong>Alertes de performance :</strong> ${entierFr(d.alertes_performance)}
    ${d.alertes_performance > 0 ? `(${entierFr(d.jours_en_alerte_performance)} jours en alerte : production inférieure à 90 % de la référence pendant au moins 3 jours)` : ''}
  </div>
  <h3>Alarmes onduleur : ${entierFr(nbAlarmes)}</h3>
  ${nbAlarmes > 0 ? `
  <table>
    <thead><tr><th>Date</th><th>Onduleur</th><th>Code</th><th>Message</th><th>Statut</th></tr></thead>
    <tbody>
      ${inverters.flatMap((inv: any) => 
        (inv.alerts ?? []).map((a: any) => `
          <tr>
            <td>${a.raised_at ? dateTunis(new Date(a.raised_at * 1000)) : '—'}</td>
            <td>${esc(inv.serial)}</td>
            <td><strong>[${a.code}]</strong></td>
            <td>${esc(a.message)}</td>
            <td>${a.cleared_at ? '✓ Résolu' : '⚠ Ouvert'}</td>
          </tr>
        `)
      ).join('')}
    </tbody>
  </table>
  ` : `<div class="alert-box success"><strong>✓</strong> Aucune alarme de l'onduleur pendant cette période.</div>`}
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- PAGE 5: RECOMMANDATIONS & SIGNATURE                                   -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="section">
  <h2>🔧 Recommandations de Maintenance</h2>
  <ul class="checklist">
    <li>Nettoyage des modules lorsque l'alerte de performance est active</li>
    <li>Contrôle des connexions DC et AC</li>
    <li>Vérification de l'onduleur et du disjoncteur</li>
    <li>Inspection des câbles et conduits</li>
    <li>Test des protections contre les surcharges</li>
  </ul>
  </div>

  <div class="section">
  <h2>📋 Diagnostic Automatique</h2>
  <div class="alert-box success">
    <strong>Performance de la période :</strong> ${performancePct(d.performance)}
  </div>
  ${nbAlarmes === 0 && d.alertes_performance === 0
    ? '<div class="alert-box success"><strong>✓</strong> Aucune alarme onduleur ni alerte de performance</div>'
    : '<div class="alert-box warning"><strong>⚠</strong> Vérification technique recommandée</div>'}
  <p style="margin-top: 15px; font-size: 12px;">
    Diagnostic établi à partir de la comparaison à la référence (PVsyst et irradiation du jour)
    et des alarmes de l'onduleur.
  </p>
  </div>

  <div class="section">
  <h2>✍️ Signature Technique</h2>
  <div class="info-grid">
    <div class="info-item">
      <div class="info-label">Installateur</div>
      <div class="info-value">Sphere Solar</div>
    </div>
    <div class="info-item">
      <div class="info-label">Date du rapport</div>
      <div class="info-value">${dateTunis()}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Version</div>
      <div class="info-value">1.0 - Complet</div>
    </div>
    <div class="info-item">
      <div class="info-label">Système</div>
      <div class="info-value">SolAR Monitor</div>
    </div>
  </div>
  </div>

  <div class="footer">
  <p>Ce rapport a été généré automatiquement par le système de monitoring SolAR.</p>
  <p>Pour toute question ou assistance, contactez Sphere Solar.</p>
  <p style="margin-top: 10px; opacity: 0.7;">© 2026 Sphere Solar - Tous droits réservés</p>
  </div>
</div>

</body>
</html>`;
}
