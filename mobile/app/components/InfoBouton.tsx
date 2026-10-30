/**
 * Petite icône « i » qui ouvre une explication en bas de l'écran.
 * Fenêtre modale React Native (aucune dépendance ajoutée) : titre, paragraphes,
 * ligne de calcul en petit, bouton « Compris ». Un appui hors de la fenêtre ou
 * le bouton retour Android la ferment aussi.
 */
import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { C } from '@/src/colors';

interface Props {
  titre: string;
  paragraphes: string[];
  calcul?: string;        // ligne de calcul affichée en petit
}

export default function InfoBouton({ titre, paragraphes, calcul }: Props) {
  const [ouvert, setOuvert] = useState(false);
  const insets = useSafeAreaInsets();
  const fermer = () => setOuvert(false);

  return (
    <>
      <TouchableOpacity
        onPress={() => setOuvert(true)}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel={`Explication : ${titre}`}
      >
        <Ionicons name="information-circle-outline" size={16} color={C.muted} />
      </TouchableOpacity>

      <Modal visible={ouvert} transparent animationType="slide" onRequestClose={fermer}>
        <Pressable style={s.fond} onPress={fermer} accessibilityLabel="Fermer">
          {/* Pressable interne : un appui dans la fenêtre ne la ferme pas */}
          <Pressable style={[s.feuille, { paddingBottom: 20 + insets.bottom }]} onPress={() => {}}>
            <View style={s.poignee} />
            <Text style={s.titre}>{titre}</Text>
            {paragraphes.map((p) => (
              <Text key={p} style={s.paragraphe}>{p}</Text>
            ))}
            {calcul ? <Text style={s.calcul}>{calcul}</Text> : null}
            <TouchableOpacity style={s.bouton} onPress={fermer} accessibilityRole="button">
              <Text style={s.boutonTxt}>Compris</Text>
            </TouchableOpacity>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  fond: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.55)' },
  feuille: {
    backgroundColor: C.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: C.border,
    paddingHorizontal: 20,
    paddingTop: 10,
  },
  poignee: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: C.border, marginBottom: 14 },
  titre: { color: C.text, fontSize: 17, fontWeight: '800', marginBottom: 10 },
  paragraphe: { color: C.text, fontSize: 14, lineHeight: 20, marginBottom: 8 },
  calcul: {
    color: C.muted, fontSize: 12, fontStyle: 'italic', marginTop: 4,
    paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border,
  },
  bouton: { backgroundColor: C.primary, borderRadius: 12, paddingVertical: 13, alignItems: 'center', marginTop: 18 },
  boutonTxt: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
});
