/**
 * En-tête de section réutilisable (charte Sphere Solar).
 * Barre verticale orange de 4 px, titre 15 gras, sous-titre 11, ligne de
 * séparation. 22 px d'espace au-dessus (sauf la première section).
 */
import { type ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { C } from '@/src/colors';

interface Props {
  title: string;
  subtitle?: string;
  first?: boolean;      // true = pas d'espace supérieur (première section)
  barColor?: string;    // couleur de la barre verticale (défaut : orange)
  titleAccessory?: ReactNode;  // élément à droite du titre (ex. InfoBouton)
  children?: ReactNode; // contenu de la section
}

export default function DashboardSection({ title, subtitle, first, barColor, titleAccessory, children }: Props) {
  return (
    <View style={[s.section, first && s.first]}>
      <View style={s.header}>
        <View style={[s.bar, barColor ? { backgroundColor: barColor } : null]} />
        <View style={{ flex: 1 }}>
          <View style={s.titleRow}>
            <Text style={s.title}>{title}</Text>
            {titleAccessory}
          </View>
          {subtitle ? <Text style={s.subtitle}>{subtitle}</Text> : null}
        </View>
      </View>
      <View style={s.separator} />
      {children}
    </View>
  );
}

const s = StyleSheet.create({
  section: { marginTop: 22 },
  first: { marginTop: 8 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14 },
  bar: { width: 4, height: 30, borderRadius: 2, backgroundColor: C.primary },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  title: { color: C.text, fontSize: 15, fontWeight: '700' },
  subtitle: { color: C.muted, fontSize: 11, marginTop: 1 },
  separator: { height: 1, backgroundColor: C.border, marginHorizontal: 14, marginTop: 10, marginBottom: 12 },
});
