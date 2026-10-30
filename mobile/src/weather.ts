/**
 * Hook météo du site (Metlaoui) via Open-Meteo.
 *
 * Expose les conditions courantes — dont l'irradiance (W/m², horizontale et dans le plan des modules)
 * utilisée pour la performance instantanée et la carte météo. Même source que WeatherWidget, mais
 * réutilisable par plusieurs écrans. Rafraîchissement toutes les 60 s.
 */
import { useEffect, useState } from 'react';
import { heuresVersEpochMs, valeurA, type Serie15 } from './serie15';

const URL =
  'https://api.open-meteo.com/v1/forecast?latitude=34.3264&longitude=8.4050' +
  '&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,' +
  'shortwave_radiation,global_tilted_irradiance,precipitation_probability,is_day' +
  // Séries 15 min du jour → irradiance estimée à l'instant présent
  '&minutely_15=shortwave_radiation,global_tilted_irradiance&forecast_days=1' +
  // Plan des modules : 30° plein sud (azimut 0 = sud chez Open-Meteo)
  '&tilt=30&azimuth=0&timezone=Africa/Tunis';

export interface SiteWeather {
  irradiance: number;      // W/m² (shortwave_radiation, plan horizontal, valeur « current »)
  irradianceInclinee: number | null;  // W/m² dans le plan des modules (30°, sud), « current »
  serieHorizontale: Serie15 | null;   // séries 15 min du jour (null si absentes)
  serieInclinee: Serie15 | null;
  temperature: number;     // °C
  humidity: number;        // %
  windSpeed: number;       // km/h
  weatherCode: number;
  isDay: boolean;
}

/** Description météo courte en français d'après le code WMO Open-Meteo. */
export function describeWeather(code: number, isDay: boolean): string {
  if (code === 0) return isDay ? 'Ciel dégagé' : 'Nuit claire';
  if (code === 1 || code === 2) return isDay ? 'Peu nuageux' : 'Nuit peu nuageuse';
  if (code === 3) return 'Couvert';
  if (code === 45 || code === 48) return 'Brouillard';
  if (code >= 51 && code <= 57) return 'Bruine';
  if (code >= 61 && code <= 67) return 'Pluie';
  if (code >= 71 && code <= 77) return 'Neige';
  if (code >= 80 && code <= 82) return 'Averses';
  if (code >= 95) return 'Orage';
  return isDay ? 'Ensoleillé' : 'Nuit claire';
}

/**
 * Irradiance estimée à l'instant `instantMs` (horizontale et dans le plan des
 * modules), interpolée sur les séries 15 min ; repli sur la valeur « current ».
 */
export function irradianceA(
  w: SiteWeather | null,
  instantMs: number = Date.now(),
): { horizontale: number | null; inclinee: number | null } {
  if (!w) return { horizontale: null, inclinee: null };
  const h = w.serieHorizontale ? valeurA(w.serieHorizontale, instantMs) : null;
  const i = w.serieInclinee ? valeurA(w.serieInclinee, instantMs) : null;
  return { horizontale: h ?? w.irradiance, inclinee: i ?? w.irradianceInclinee };
}

export function useSiteWeather() {
  const [weather, setWeather] = useState<SiteWeather | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let actif = true;

    const charger = async () => {
      try {
        const res = await fetch(URL);
        if (!res.ok) throw new Error(`${res.status}`);
        const json = await res.json();
        const cur = json.current ?? {};
        const m15 = json.minutely_15;
        const fins = Array.isArray(m15?.time)
          ? heuresVersEpochMs(m15.time, Number(json.utc_offset_seconds ?? 3600))
          : null;
        const serie = (cle: string): Serie15 | null =>
          fins && Array.isArray(m15?.[cle]) ? { finsMs: fins, valeurs: m15[cle] } : null;
        if (!actif) return;
        setWeather({
          irradiance: Number(cur.shortwave_radiation ?? 0),
          irradianceInclinee: cur.global_tilted_irradiance != null
            ? Number(cur.global_tilted_irradiance) : null,
          serieHorizontale: serie('shortwave_radiation'),
          serieInclinee: serie('global_tilted_irradiance'),
          temperature: Number(cur.temperature_2m ?? 0),
          humidity: Number(cur.relative_humidity_2m ?? 0),
          windSpeed: Number(cur.wind_speed_10m ?? 0),
          weatherCode: Number(cur.weather_code ?? 0),
          isDay: Number(cur.is_day ?? 1) === 1,
        });
        setError('');
      } catch (e: any) {
        if (actif) setError(String(e?.message || 'météo indisponible'));
      } finally {
        if (actif) setLoading(false);
      }
    };

    charger();
    const h = setInterval(charger, 60_000);   // rafraîchissement 1 min
    return () => { actif = false; clearInterval(h); };
  }, []);

  return { weather, loading, error };
}
