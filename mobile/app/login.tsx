import { Redirect, router } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '@/src/auth';
import { estErreurServeur } from '@/src/session';
import { C } from '@/src/colors';

export default function LoginScreen() {
  const { token, login, messageSession } = useAuth();
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [busy, setBusy]         = useState(false);

  if (token) return <Redirect href="/(app)" />;

  const submit = async () => {
    if (!email || !password) { setError('Email et mot de passe requis'); return; }
    setBusy(true);
    setError('');
    try {
      await login(email.trim(), password);
      router.replace('/(app)');
    } catch (e: any) {
      // 401 sur /auth/login : identifiants refusés ; sinon serveur injoignable ou autre erreur
      setError(estErreurServeur(e) && e.statut === 401
        ? 'Email ou mot de passe incorrect.'
        : estErreurServeur(e) ? `Connexion impossible (${e.statut}).`
        : 'Serveur injoignable. Vérifiez la connexion et l’adresse du serveur.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <LinearGradient colors={['#020617', '#0f172a', '#1e1b4b']} style={s.bg}>
      {/* decorative sun */}
      <View style={s.sunRing3} />
      <View style={s.sunRing2} />
      <View style={s.sunRing1} />
      <View style={s.sun} />

      <KeyboardAvoidingView
        style={s.kav}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={s.card}>
          <Text style={s.logo}>☀ Sphere Solar</Text>
          <Text style={s.subtitle}>Supervision solaire</Text>
          {/* Retour ici après un jeton refusé (401) : « Session expirée, reconnectez-vous. » */}
          {messageSession && !error ? <Text style={s.sessionText}>{messageSession}</Text> : null}

          <View style={s.fieldGroup}>
            <Text style={s.label}>Email</Text>
            <TextInput
              style={s.input}
              placeholder="you@example.com"
              placeholderTextColor={C.muted}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              value={email}
              onChangeText={setEmail}
            />
          </View>

          <View style={s.fieldGroup}>
            <Text style={s.label}>Mot de passe</Text>
            <TextInput
              style={s.input}
              placeholder="••••••••"
              placeholderTextColor={C.muted}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              onSubmitEditing={submit}
            />
          </View>

          {error ? <Text style={s.errorText}>{error}</Text> : null}

          <TouchableOpacity onPress={submit} disabled={busy} activeOpacity={0.85}>
            <LinearGradient
              colors={['#f59e0b', '#d97706']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={s.btn}
            >
              {busy
                ? <ActivityIndicator color="#000" />
                : <Text style={s.btnText}>Se connecter →</Text>}
            </LinearGradient>
          </TouchableOpacity>

          <TouchableOpacity onPress={() => router.push('/server')} hitSlop={8}>
            <Text style={s.serverLink}>⚙ Réglages du serveur</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  bg:  { flex: 1, justifyContent: 'center' },
  kav: { flex: 1, justifyContent: 'center', padding: 24 },

  // decorative sun rings
  sun:      { position: 'absolute', top: 80, alignSelf: 'center', width: 80,  height: 80,  borderRadius: 40,  backgroundColor: '#f59e0b44' },
  sunRing1: { position: 'absolute', top: 56, alignSelf: 'center', width: 128, height: 128, borderRadius: 64,  backgroundColor: '#f59e0b22' },
  sunRing2: { position: 'absolute', top: 32, alignSelf: 'center', width: 176, height: 176, borderRadius: 88,  backgroundColor: '#f59e0b11' },
  sunRing3: { position: 'absolute', top:  8, alignSelf: 'center', width: 224, height: 224, borderRadius: 112, backgroundColor: '#f59e0b08' },

  card: {
    backgroundColor: 'rgba(30,41,59,0.85)',
    borderRadius: 24,
    padding: 28,
    gap: 16,
    borderWidth: 1,
    borderColor: 'rgba(245,158,11,0.2)',
    marginTop: 160,
  },
  logo:     { fontSize: 26, fontWeight: '800', color: C.primary, textAlign: 'center' },
  subtitle: { fontSize: 13, color: C.muted, textAlign: 'center', marginBottom: 4 },

  fieldGroup: { gap: 6 },
  label:      { color: C.muted, fontSize: 12, fontWeight: '600', letterSpacing: 0.5 },
  input: {
    backgroundColor: 'rgba(15,23,42,0.8)',
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 12,
    padding: 14,
    color: C.text,
    fontSize: 15,
  },

  errorText: { color: C.red, fontSize: 13, textAlign: 'center' },
  sessionText: { color: C.primary, fontSize: 13, textAlign: 'center', marginBottom: 12 },

  btn:     { borderRadius: 14, padding: 16, alignItems: 'center' },
  btnText: { color: '#000', fontWeight: '800', fontSize: 15, letterSpacing: 0.3 },
  serverLink: { color: C.muted, fontSize: 13, textAlign: 'center', marginTop: 4 },
});
