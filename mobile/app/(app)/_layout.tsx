import { Redirect, Stack } from 'expo-router';
import { ActivityIndicator, View } from 'react-native';
import { useAuth } from '@/src/auth';
import { C } from '@/src/colors';

export default function AppLayout() {
  const { token, loading } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator color={C.primary} size="large" />
      </View>
    );
  }

  if (!token) return <Redirect href="/login" />;

  return (
    <Stack
      screenOptions={{
        headerStyle:      { backgroundColor: C.surface },
        headerTintColor:  C.primary,
        headerTitleStyle: { color: C.text, fontWeight: '600' },
        contentStyle:     { backgroundColor: C.bg },
      }}
    >
      <Stack.Screen name="index"                   options={{ title: 'Installations' }} />
      <Stack.Screen name="site/[id]"               options={{ headerShown: false }} />
    </Stack>
  );
}
