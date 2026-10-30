import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { api } from './api';
import { htmlRapport } from './rapportHtml';
import { lireSynthese, MESSAGE_INDISPONIBLE } from './rapport';

export async function generateComprehensiveReport(
  installationId: number,
  period: 'month' | 'year' = 'month',
  year?: number,
  month?: number
) {
  try {
    // Réponse vérifiée : un format inattendu donne un message clair, pas un plantage
    const reportData = lireSynthese(await api.reportData(installationId, period, year, month));
    if (!reportData) throw new Error(MESSAGE_INDISPONIBLE);

    const html = htmlRapport(reportData, period, year, month);

    const { uri } = await Print.printToFileAsync({ html });
    if (!(await Sharing.isAvailableAsync())) {
      return uri;
    }
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf' });
    return uri;
  } catch (error: any) {
    console.error('Report generation error:', error);
    throw new Error(`Échec de la génération du rapport : ${error?.message || 'erreur inconnue'}`);
  }
}
