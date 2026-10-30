import { useEffect, useRef, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { wsUrl } from './api';
import type { LatestMetrics } from './types';

export interface WSResult {
  data:   LatestMetrics | null;
  isLive: boolean;          // true while WS messages arrive within 10 s
}

export function useInverterWS(inverterId: number | null): WSResult {
  const [data, setData]     = useState<LatestMetrics | null>(null);
  const [lastMs, setLastMs] = useState<number>(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!inverterId) return;
    let alive = true;

    async function connect() {
      const token = await SecureStore.getItemAsync('jwt');
      if (!token || !alive) return;

      const ws = new WebSocket(`${wsUrl()}/ws?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.onopen = () => ws.send(JSON.stringify({ subscribe: [inverterId] }));

      ws.onmessage = (e) => {
        console.log('WS message reçu:', e.data); // ← ajoute cette ligne
        try {
          const msg = JSON.parse(e.data as string) as LatestMetrics;
          if (msg.inverter_id === inverterId) {
            // Reset e_day if the day has changed since the last reading
            // Use UTC dates to avoid timezone issues
            if (msg.ts && msg.e_day != null) {
              const lastReadingUTC = new Date(msg.ts * 1000).toISOString().split('T')[0];
              const currentUTC = new Date().toISOString().split('T')[0];
              console.log(`Last reading date (UTC): ${lastReadingUTC}, Current date (UTC): ${currentUTC}`);
              if (lastReadingUTC !== currentUTC) {
                console.log(`Day changed! Resetting e_day from ${msg.e_day} to null`);
                msg.e_day = null;  // Reset to None so it shows as "—"
              }
            }
            setData(msg);
            setLastMs(Date.now());   // timestamp of last received message
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => { if (alive) setTimeout(connect, 3000); };
    }

    connect();
    return () => {
      alive = false;
      wsRef.current?.close();
    };
  }, [inverterId]);

  return { data, isLive: Date.now() - lastMs < 10_000 };
}
