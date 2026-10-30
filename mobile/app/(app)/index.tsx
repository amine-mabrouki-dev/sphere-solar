import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '@/src/auth';
import { api } from '@/src/api';
import { C } from '@/src/colors';
import type { Installation } from '@/src/types';

export default function InstallationsScreen() {
  const { logout } = useAuth();
  const [data, setData]             = useState<Installation[]>([]);
  const [busy, setBusy]             = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError]           = useState('');

  const load = (silent = false) => {
    if (!silent) setBusy(true);
    setError('');
    api.installations()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => { setBusy(false); setRefreshing(false); });
  };

  useEffect(() => { load(); }, []);

  if (busy) {
    return (
      <View style={s.center}>
        <ActivityIndicator color={C.primary} size="large" />
      </View>
    );
  }

  return (
    <View style={s.container}>
      {/* gradient hero header */}
      <LinearGradient colors={['#1e1b4b', '#0f172a']} style={s.hero}>
        <View style={s.heroSun} />
        <Text style={s.heroTitle}>Mes installations</Text>
        <Text style={s.heroSub}>
          {data.length === 0 ? 'Aucune installation' : `${data.length} installation${data.length > 1 ? 's' : ''}`}
        </Text>
        <TouchableOpacity style={s.gearBtn} onPress={() => router.push('/server')} hitSlop={8}>
          <Text style={s.gearText}>⚙</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.signOutBtn} onPress={logout}>
          <Text style={s.signOutText}>Déconnexion</Text>
        </TouchableOpacity>
      </LinearGradient>

      <FlatList
        data={data}
        keyExtractor={i => String(i.id)}
        contentContainerStyle={s.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); load(true); }}
            tintColor={C.primary}
          />
        }
        ListEmptyComponent={
          <View style={s.emptyBox}>
            <Text style={s.emptyIcon}>☀</Text>
            <Text style={s.emptyTitle}>Aucune installation</Text>
            <Text style={s.emptyHint}>
              Démarrez le simulateur Wokwi dans VS Code —{'\n'}
              le premier message de télémétrie enregistre le site.{'\n'}
              Puis tirez vers le bas pour actualiser.
            </Text>
            {error ? <Text style={s.errText}>{error}</Text> : null}
          </View>
        }
        renderItem={({ item }) => (
          <TouchableOpacity
            activeOpacity={0.75}
            onPress={() => router.push({ pathname: '/site/[id]', params: { id: item.id } })}
          >
            <LinearGradient
              colors={['rgba(30,41,59,1)', 'rgba(15,23,42,1)']}
              style={s.card}
            >
              <View style={s.cardAccent} />
              <View style={s.cardBody}>
                <Text style={s.cardName}>{item.name}</Text>
                {item.location
                  ? <Text style={s.cardLoc}>{item.location}</Text>
                  : null}
              </View>
              <Text style={s.arrow}>›</Text>
            </LinearGradient>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  center:    { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: C.bg },

  hero: {
    paddingTop: 20,
    paddingBottom: 28,
    paddingHorizontal: 24,
    position: 'relative',
    overflow: 'hidden',
  },
  heroSun: {
    position: 'absolute', right: -40, top: -40,
    width: 160, height: 160, borderRadius: 80,
    backgroundColor: 'rgba(245,158,11,0.12)',
  },
  heroTitle: { fontSize: 28, fontWeight: '800', color: C.text, marginTop: 8 },
  heroSub:   { fontSize: 13, color: C.muted, marginTop: 4 },
  signOutBtn: { position: 'absolute', top: 24, right: 20 },
  signOutText:{ color: C.muted, fontSize: 13 },
  gearBtn:    { position: 'absolute', top: 20, left: 20 },
  gearText:   { color: C.muted, fontSize: 20 },

  list: { padding: 16, gap: 12 },

  card: {
    borderRadius: 16,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: C.border,
    overflow: 'hidden',
  },
  cardAccent: {
    position: 'absolute', left: 0, top: 0, bottom: 0,
    width: 4, backgroundColor: C.primary, borderTopLeftRadius: 16, borderBottomLeftRadius: 16,
  },
  cardBody: { flex: 1, paddingLeft: 12 },
  cardName: { color: C.text, fontSize: 16, fontWeight: '700' },
  cardLoc:  { color: C.muted, fontSize: 13, marginTop: 3 },
  arrow:    { color: C.muted, fontSize: 22 },

  emptyBox:   { padding: 40, alignItems: 'center', gap: 10 },
  emptyIcon:  { fontSize: 48, marginBottom: 4 },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: '700' },
  emptyHint:  { color: C.muted, fontSize: 14, textAlign: 'center', lineHeight: 22 },
  errText:    { color: C.red, fontSize: 13, textAlign: 'center', marginTop: 4 },
});
