import React from 'react';
import { View, Text, StyleSheet, Platform, type ViewStyle } from 'react-native';
import { C } from '@/src/colors';

// pleineLargeur : tuile « total » sur toute la ligne (option explicite, et non
// plus déduite du libellé : un libellé contenant « total » reste une tuile normale)
type TileItem = { label: string; value: string | null; unit?: string; valueStyle?: any; pleineLargeur?: boolean };

export default function LiveReadings({ tiles, cols = 3 }: { tiles: TileItem[]; cols?: number }) {
  const basis = (cols === 2 ? '48%' : cols === 4 ? '22.5%' : '31%') as ViewStyle['flexBasis'];
  // 4 colonnes : tuiles étroites (~75 px), valeur et marges réduites pour que
  // « 230,1 V » tienne sur une ligne ; même style sinon
  const compact = cols >= 4;

  return (
    <View style={styles.wrapper}>
      <View style={styles.grid}>
        {tiles.map((t, i) => {
          const isTotal = t.pleineLargeur === true;
          const containerStyle = isTotal
            ? [styles.totalCard, styles.spanFull]
            : [styles.card, compact && styles.cardCompact, { flexBasis: basis, maxWidth: basis }];
          const valueStyle = isTotal
            ? [styles.totalValue, t.valueStyle]
            : [styles.value, compact && styles.valueCompact, t.valueStyle];
          const unitStyle = isTotal ? styles.totalUnit : styles.unit;

          return (
            <View key={i} style={containerStyle}>
              {/* 2 lignes au plus : « Courant PV (chaîne 1) » n'est pas tronqué */}
              <Text style={styles.label} numberOfLines={2}>{t.label}</Text>
              <View style={isTotal ? styles.totalRow : styles.valueRow}>
                <Text style={valueStyle} numberOfLines={1} adjustsFontSizeToFit>{t.value ?? '—'}</Text>
                {t.unit ? <Text style={[unitStyle, compact && styles.unitCompact]}>{t.unit}</Text> : null}
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { paddingHorizontal: 12, marginBottom: 16 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10 },

  card: {
    flexBasis: '31%',
    backgroundColor: C.surface,
    borderRadius: 28,
    paddingVertical: 16,
    paddingHorizontal: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: C.border,
    marginBottom: 10,
    minHeight: 120,
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 6, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 },
    }),
  },
  totalCard: {
    flexBasis: '100%',
    backgroundColor: C.surface,
    borderRadius: 28,
    padding: 18,
    alignItems: 'flex-start',
    borderWidth: 1,
    borderColor: C.border,
    marginBottom: 10,
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 6, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 },
    }),
  },
  spanFull: { width: '100%' },

  // Hauteur de 2 lignes pour toutes les tuiles : les valeurs restent alignées
  label: { color: C.muted, fontSize: 11, lineHeight: 14, minHeight: 28, textAlign: 'center', marginBottom: 6, letterSpacing: 0.4, fontWeight: '600', textTransform: 'uppercase' },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  value: { color: C.text, fontSize: 24, fontWeight: '800' },
  unit: { color: C.muted, fontSize: 12, marginLeft: 4 },

  // Variante 4 colonnes
  cardCompact: { paddingHorizontal: 4, borderRadius: 22 },
  valueCompact: { fontSize: 18 },
  unitCompact: { fontSize: 10, marginLeft: 1 },

  totalRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', width: '100%' },

  totalValue: { color: C.text, fontSize: 28, fontWeight: '800' },
  totalUnit: { color: C.muted, fontSize: 12, marginLeft: 6 },
});
