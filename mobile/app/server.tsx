import { router } from 'expo-router';
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
import { C } from '@/src/colors';
import { defaultServerUrl, getServerUrl, setServerUrl, testServerUrl } from '@/src/server';

type Status = { kind: 'idle' | 'ok' | 'err' | 'busy'; msg?: string };

export default function ServerScreen() {
  const [url, setUrl]       = useState(getServerUrl());
  const [status, setStatus] = useState<Status>({ kind: 'idle' });

  const test = async () => {
    setStatus({ kind: 'busy', msg: 'Test en cours…' });
    try {
      const ok = await testServerUrl(url);
      setStatus(ok
        ? { kind: 'ok',  msg: 'Accessible — le serveur a répondu.' }
        : { kind: 'err', msg: 'Hôte joint, mais /health a échoué.' });
    } catch {
      setStatus({ kind: 'err', msg: 'Adresse injoignable.' });
    }
  };

  const save = async () => {
    try {
      const clean = await setServerUrl(url);
      setUrl(clean);
      setStatus({ kind: 'ok', msg: 'Enregistré.' });
      setTimeout(() => router.back(), 400);
    } catch (e: any) {
      setStatus({ kind: 'err', msg: e.message ?? 'URL invalide' });
    }
  };

  const statusColor =
    status.kind === 'ok'  ? C.green :
    status.kind === 'err' ? C.red   : C.muted;

  return (
    <View style={s.bg}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12}>
          <Text style={s.back}>‹ Retour</Text>
        </TouchableOpacity>
        <Text style={s.title}>Serveur</Text>
        <View style={{ width: 48 }} />
      </View>

      <KeyboardAvoidingView
        style={s.body}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <Text style={s.label}>Adresse du serveur</Text>
        <TextInput
          style={s.input}
          placeholder={defaultServerUrl()}
          placeholderTextColor={C.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          value={url}
          onChangeText={(t) => { setUrl(t); setStatus({ kind: 'idle' }); }}
        />
        <Text style={s.hint}>
          Le téléphone se connecte ici pour les données et le temps réel. Utilisez
          l'IP LAN du PC qui exécute le serveur (ex. http://192.168.1.20:8000),
          ou une URL publique. Le WebSocket utilise le même hôte automatiquement.
        </Text>

        {status.kind !== 'idle' && (
          <View style={s.statusRow}>
            {status.kind === 'busy' && <ActivityIndicator color={C.muted} />}
            <Text style={[s.statusText, { color: statusColor }]}>{status.msg}</Text>
          </View>
        )}

        <View style={s.actions}>
          <TouchableOpacity style={[s.btn, s.btnGhost]} onPress={test} activeOpacity={0.8}>
            <Text style={s.btnGhostText}>Tester la connexion</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={save} activeOpacity={0.85} style={{ flex: 1 }}>
            <LinearGradient colors={['#f59e0b', '#d97706']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.btn}>
              <Text style={s.btnText}>Enregistrer</Text>
            </LinearGradient>
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={() => { setUrl(defaultServerUrl()); setStatus({ kind: 'idle' }); }}>
          <Text style={s.reset}>Réinitialiser ({defaultServerUrl()})</Text>
        </TouchableOpacity>
      </KeyboardAvoidingView>
    </View>
  );
}

const s = StyleSheet.create({
  bg:     { flex: 1, backgroundColor: C.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingTop: 56, paddingBottom: 16, paddingHorizontal: 16,
    backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.border,
  },
  back:  { color: C.primary, fontSize: 16, width: 48 },
  title: { color: C.text, fontSize: 17, fontWeight: '700' },

  body:  { flex: 1, padding: 20, gap: 12 },
  label: { color: C.muted, fontSize: 12, fontWeight: '600', letterSpacing: 0.5 },
  input: {
    backgroundColor: C.surface, borderWidth: 1, borderColor: C.border,
    borderRadius: 12, padding: 14, color: C.text, fontSize: 15,
  },
  hint:  { color: C.muted, fontSize: 12, lineHeight: 18 },

  statusRow:  { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  statusText: { fontSize: 13, flex: 1 },

  actions:   { flexDirection: 'row', gap: 12, marginTop: 8 },
  btn:       { borderRadius: 14, padding: 16, alignItems: 'center' },
  btnText:   { color: '#000', fontWeight: '800', fontSize: 15 },
  btnGhost:  { borderWidth: 1, borderColor: C.border, flex: 1 },
  btnGhostText: { color: C.text, fontWeight: '700', fontSize: 15 },

  reset: { color: C.muted, fontSize: 12, textAlign: 'center', marginTop: 16 },
});
