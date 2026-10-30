/**
 * Contexte « site » partagé par les onglets d'une installation.
 *
 * Résout une fois l'installation et son onduleur courant (le premier), et tient
 * à jour les compteurs qui alimentent la pastille de l'onglet Alertes
 * (nombre d'alertes ouvertes + alerte de performance). Les onglets lisent ces
 * valeurs via le hook useSite().
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { api } from '@/src/api';
import type { Installation, Inverter } from '@/src/types';

interface SiteValue {
  instId: number;
  installation: Installation | null;
  inverters: Inverter[];
  inverterId: number | null;      // onduleur courant (le premier de l'installation)
  loading: boolean;
  error: string;
  openAlertsCount: number;        // alertes ouvertes (cleared_at nul)
  perfAlert: boolean;             // alerte de performance active
  refreshAlerts: () => void;
}

const SiteContext = createContext<SiteValue | null>(null);

export function useSite(): SiteValue {
  const v = useContext(SiteContext);
  if (!v) throw new Error('useSite doit être utilisé dans un SiteProvider');
  return v;
}

export function SiteProvider({ instId, children }: { instId: number; children: ReactNode }) {
  const [installation, setInstallation] = useState<Installation | null>(null);
  const [inverters, setInverters] = useState<Inverter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openAlertsCount, setOpenAlertsCount] = useState(0);
  const [perfAlert, setPerfAlert] = useState(false);

  const inverterId = inverters[0]?.id ?? null;

  // Chargement de l'installation et de ses onduleurs
  useEffect(() => {
    let actif = true;
    setLoading(true);
    (async () => {
      try {
        const installs = await api.installations();
        const inst = installs.find((i) => i.id === instId) ?? null;
        const invs = await api.inverters(instId);
        if (!actif) return;
        setInstallation(inst);
        setInverters(invs);
        setError('');
      } catch (e: any) {
        if (actif) setError(e?.message ?? 'Erreur de chargement');
      } finally {
        if (actif) setLoading(false);
      }
    })();
    return () => { actif = false; };
  }, [instId]);

  // Compteurs pour la pastille de l'onglet Alertes
  const refreshAlerts = useCallback(async () => {
    if (inverterId == null) return;
    try {
      const open = await api.alerts(inverterId, true);
      setOpenAlertsCount(open?.length ?? 0);
    } catch { /* ignore */ }
    try {
      const perf = await api.performance(inverterId, 7, 'auto');
      setPerfAlert(!!perf?.alerte_performance);
    } catch { /* ignore (422 si pas de journée complète) */ }
  }, [inverterId]);

  useEffect(() => {
    if (inverterId == null) return;
    refreshAlerts();
    const h = setInterval(refreshAlerts, 15_000);   // rafraîchissement toutes les 15 s
    return () => clearInterval(h);
  }, [inverterId, refreshAlerts]);

  const value: SiteValue = {
    instId, installation, inverters, inverterId,
    loading, error, openAlertsCount, perfAlert, refreshAlerts,
  };
  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}
