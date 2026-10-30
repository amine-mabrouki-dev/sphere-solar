/**
 * Navigation par onglets d'une installation (visible après connexion).
 * Barre fixe en bas : Accueil, Historique, Alertes, Assistant, Rapports.
 * Chaque onglet a son propre en-tête (titre aligné à gauche).
 */
import { Tabs, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { C } from '@/src/colors';
import { SiteProvider, useSite } from '@/src/site';

// Charte graphique de la barre d'onglets
const BAR = '#0B1A30';
const ACTIF = '#E08E0B';
const INACTIF = '#8FA3BF';

type IoniconName = React.ComponentProps<typeof Ionicons>['name'];

// Icône + petit trait orange au-dessus quand l'onglet est actif
function TabIcon({ name, color, focused }: { name: IoniconName; color: string; focused: boolean }) {
  return (
    <View style={{ alignItems: 'center', width: 48 }}>
      <View style={{ height: 3, width: 44, borderRadius: 2, marginBottom: 6, backgroundColor: focused ? ACTIF : 'transparent' }} />
      <Ionicons name={name} size={22} color={color} />
    </View>
  );
}

// Onglet Alertes : pastille rouge s'il existe une alerte ouverte ou de performance
function AlertsIcon({ color, focused }: { color: string; focused: boolean }) {
  const { openAlertsCount, perfAlert } = useSite();
  const pastille = openAlertsCount > 0 || perfAlert;
  return (
    <View style={{ alignItems: 'center', width: 48 }}>
      <View style={{ height: 3, width: 44, borderRadius: 2, marginBottom: 6, backgroundColor: focused ? ACTIF : 'transparent' }} />
      <View>
        <Ionicons name="notifications-outline" size={22} color={color} />
        {pastille && (
          <View style={{
            position: 'absolute', top: -2, right: -4,
            width: 10, height: 10, borderRadius: 5,
            backgroundColor: '#C0392B', borderWidth: 1, borderColor: BAR,
          }} />
        )}
      </View>
    </View>
  );
}

function SiteTabs() {
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: true,
        headerStyle: { backgroundColor: BAR },
        headerTintColor: C.text,
        headerTitleAlign: 'left',
        headerTitleStyle: { color: C.text, fontWeight: '700', fontSize: 20 },
        tabBarStyle: {
          backgroundColor: BAR,
          borderTopColor: 'rgba(255,255,255,0.12)',
          borderTopWidth: 1,
          height: 56 + insets.bottom,
          paddingBottom: insets.bottom > 0 ? insets.bottom : 8,
          paddingTop: 6,
        },
        tabBarActiveTintColor: ACTIF,
        tabBarInactiveTintColor: INACTIF,
        tabBarLabelStyle: { fontSize: 10, marginTop: 0 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Tableau de bord',
          tabBarLabel: 'Accueil',
          tabBarIcon: ({ color, focused }) => <TabIcon name="home-outline" color={color} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="historique"
        options={{
          title: 'Historique',
          tabBarLabel: 'Historique',
          tabBarIcon: ({ color, focused }) => <TabIcon name="stats-chart-outline" color={color} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="alertes"
        options={{
          title: 'Alertes',
          tabBarLabel: 'Alertes',
          tabBarIcon: ({ color, focused }) => <AlertsIcon color={color} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="assistant"
        options={{
          title: 'Assistant',
          tabBarLabel: 'Assistant',
          tabBarIcon: ({ color, focused }) => <TabIcon name="chatbubble-outline" color={color} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="rapports"
        options={{
          title: 'Rapports',
          tabBarLabel: 'Rapports',
          tabBarIcon: ({ color, focused }) => <TabIcon name="document-text-outline" color={color} focused={focused} />,
        }}
      />
    </Tabs>
  );
}

export default function SiteLayout() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const instId = parseInt(id, 10);
  return (
    <SiteProvider instId={instId}>
      <SiteTabs />
    </SiteProvider>
  );
}
