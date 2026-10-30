import React, { createContext, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { api, onSessionExpiree } from './api';
import { loadServerUrl } from './server';
import { MESSAGE_SESSION_EXPIREE } from './session';

interface AuthState {
  token: string | null;
  loading: boolean;
  // Message à afficher sur l'écran de connexion (ex. « Session expirée… »), sinon null
  messageSession: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({} as AuthState);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [messageSession, setMessageSession] = useState<string | null>(null);

  useEffect(() => {
    // Load the saved backend URL first, then the stored session token.
    loadServerUrl()
      .then(() => SecureStore.getItemAsync('jwt'))
      .then(t => setToken(t))
      .finally(() => setLoading(false));
  }, []);

  // Jeton refusé par le serveur (401) : api.ts l'a déjà effacé ; sans jeton,
  // la navigation revient à l'écran de connexion, qui affiche le message.
  useEffect(() => {
    onSessionExpiree(() => {
      setMessageSession(MESSAGE_SESSION_EXPIREE);
      setToken(null);
    });
    return () => onSessionExpiree(null);
  }, []);

  const login = async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    await SecureStore.setItemAsync('jwt', access_token);
    setMessageSession(null);
    setToken(access_token);
  };

  const logout = async () => {
    await SecureStore.deleteItemAsync('jwt');
    setMessageSession(null);
    setToken(null);
  };

  return (
    <AuthContext.Provider value={{ token, loading, messageSession, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
