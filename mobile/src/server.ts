import * as SecureStore from 'expo-secure-store';

// Runtime-configurable backend URL. The build-time EXPO_PUBLIC_API_URL is only
// the initial default; the user can override it on the Server screen (#8), and
// the value persists on the device.

const KEY = 'server_url';
const DEFAULT = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

let current = DEFAULT;

/** Load the saved URL into memory. Call once at app startup before any request. */
export async function loadServerUrl(): Promise<string> {
  try {
    const v = await SecureStore.getItemAsync(KEY);
    if (v) current = v;
  } catch { /* ignore — fall back to default */ }
  return current;
}

/** Current backend base URL (no trailing slash). Read at call time, not import time. */
export function getServerUrl(): string {
  return current;
}

export function defaultServerUrl(): string {
  return DEFAULT;
}

/** Validate, normalise and persist a new backend URL. Throws on bad input. */
export async function setServerUrl(url: string): Promise<string> {
  const clean = url.trim().replace(/\/+$/, '');
  if (!/^https?:\/\/.+/i.test(clean)) {
    throw new Error('URL must start with http:// or https://');
  }
  current = clean;
  await SecureStore.setItemAsync(KEY, clean);
  return clean;
}

/** Quick reachability check against the backend /health endpoint. */
export async function testServerUrl(url: string): Promise<boolean> {
  const base = url.trim().replace(/\/+$/, '');
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 5000);
  try {
    const res = await fetch(`${base}/health`, { signal: ctrl.signal });
    return res.ok;
  } finally {
    clearTimeout(t);
  }
}
