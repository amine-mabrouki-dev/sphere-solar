import * as SecureStore from 'expo-secure-store';
import { getServerUrl } from './server';
import { ErreurServeur, SessionExpiree, estSessionExpiree } from './session';
import type { Alert, ChatMsg, EnergyPoint, Forecast, Installation, Inverter, LatestMetrics, Performance, Reading } from './types';

async function headers(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const token = await SecureStore.getItemAsync('jwt');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

// Appelé quand le serveur refuse le jeton (session expirée) : AuthProvider
// l'enregistre pour revenir à l'écran de connexion.
let surSessionExpiree: (() => void) | null = null;
export function onSessionExpiree(cb: (() => void) | null): void {
  surSessionExpiree = cb;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${getServerUrl()}${path}`, {
    ...init,
    headers: await headers(init.headers as Record<string, string>),
  });
  if (!res.ok) {
    // Jeton expiré ou invalide : on l'oublie et on prévient l'application
    if (estSessionExpiree(res.status, path)) {
      await SecureStore.deleteItemAsync('jwt').catch(() => {});
      surSessionExpiree?.();
      throw new SessionExpiree();
    }
    const msg = await res.text().catch(() => res.statusText);
    throw new ErreurServeur(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    req<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  installations: () => req<Installation[]>('/installations'),

  reportData: (instId: number, period: 'month' | 'year' = 'month', year?: number, month?: number) => {
    const q = new URLSearchParams({ period });
    if (year)  q.set('year',  String(year));
    if (month) q.set('month', String(month));
    return req<any>(`/installations/${instId}/report-data?${q}`);
  },

  inverters: (instId: number) =>
    req<Inverter[]>(`/installations/${instId}/inverters`),

  latest: (invId: number) =>
    req<LatestMetrics>(`/inverters/${invId}/latest`),

  history: (invId: number, opts: { from?: number; to?: number; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.from)  q.set('from',  String(opts.from));
    if (opts.to)    q.set('to',    String(opts.to));
    if (opts.limit) q.set('limit', String(opts.limit));
    return req<Reading[]>(`/inverters/${invId}/history?${q}`);
  },

  energy: (invId: number, period: 'day' | 'month', opts: { from?: number; to?: number } = {}) => {
    const q = new URLSearchParams({ period });
    if (opts.from) q.set('from', String(opts.from));
    if (opts.to)   q.set('to',   String(opts.to));
    return req<EnergyPoint[]>(`/inverters/${invId}/energy?${q}`);
  },

  alerts: (invId: number, open?: boolean) => {
    const q = open !== undefined ? `?open=${open}` : '';
    return req<Alert[]>(`/inverters/${invId}/alerts${q}`);
  },

  performance: (invId: number, days = 14, mode: 'auto' | 'irradiance' | 'mensuel' = 'auto') =>
    req<Performance>(`/inverters/${invId}/performance?days=${days}&mode=${mode}`),

  forecast: (invId: number) =>
    req<Forecast>(`/inverters/${invId}/forecast`, { method: 'POST' }),

  assistant: (invId: number, messages: ChatMsg[]) =>
    req<{ reply: string }>(`/inverters/${invId}/assistant`, {
      method: 'POST',
      body: JSON.stringify({ messages }),
    }),

  dismissAlert: (invId: number, alertId: number) =>
    req<{ status: string }>(`/inverters/${invId}/alerts/${alertId}/dismiss`, {
      method: 'POST',
    }),
};

export const wsUrl = (): string =>
  getServerUrl().replace(/^http/, 'ws');
