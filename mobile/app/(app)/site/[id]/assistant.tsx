/**
 * Onglet Assistant.
 * - Prévision de demain (POST /forecast, calculée par le serveur) : valeur ≈ kWh,
 *   fourchette, soleil prévu et performance récente, explication, bouton Actualiser.
 * - Assistant de supervision (POST /assistant) : conversation, bulles,
 *   suggestions, zone de saisie. Réponses nettoyées du Markdown.
 * - Si ouvert depuis une alerte (param ask), la question est préremplie et envoyée.
 */
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { messageErreurAssistant } from '@/src/session';
import { C } from '@/src/colors';
import { detailPrevision, fourchettePrevision, MENTION_PREVISION, valeurPrevision } from '@/src/prevision';
import { useSite } from '@/src/site';
import DashboardSection from '@/app/components/DashboardSection';
import type { ChatMsg, Forecast } from '@/src/types';

const ACCUEIL: ChatMsg = {
  role: 'assistant',
  content:
    "Bonjour ! Je suis votre assistant de supervision. Posez-moi vos questions sur " +
    "la production, les alertes ou l'entretien de votre installation.",
};

const SUGGESTIONS = ['Faut-il nettoyer les modules ?', 'Explique la dernière alerte'];

// Nettoie les réponses du modèle (supprime le Markdown, listes en lignes lisibles)
function nettoyer(texte: string): string {
  return texte
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^\s*[-*]\s+/gm, '• ')
    .replace(/\|/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export default function AssistantScreen() {
  const { ask } = useLocalSearchParams<{ ask?: string }>();
  const { inverterId } = useSite();
  const invId = inverterId;
  const insets = useSafeAreaInsets();

  const [messages, setMessages] = useState<ChatMsg[]>([ACCUEIL]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [fcBusy, setFcBusy] = useState(false);
  const [fcError, setFcError] = useState('');

  const scrollRef = useRef<ScrollView>(null);
  const scrollDown = () => setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);

  // Prévision de demain
  const chargerPrevision = async () => {
    if (invId == null || fcBusy) return;
    setFcBusy(true);
    setFcError('');
    try {
      setForecast(await api.forecast(invId));
    } catch (e: any) {
      setFcError("Prévision indisponible pour le moment.");
    } finally {
      setFcBusy(false);
    }
  };

  useEffect(() => {
    if (invId != null) chargerPrevision();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invId]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || busy || invId == null) return;
    setError('');
    const next = [...messages, { role: 'user', content } as ChatMsg];
    setMessages(next);
    setInput('');
    setBusy(true);
    scrollDown();
    try {
      const history = next.filter((m, i) => !(i === 0 && m === ACCUEIL));
      const { reply } = await api.assistant(invId, history);
      setMessages([...next, { role: 'assistant', content: reply }]);
    } catch (e: unknown) {
      // Échec : la question n'a pas reçu de réponse. On la retire de la
      // conversation (sinon elle s'empile à chaque nouvel essai et repart dans
      // l'historique envoyé) et on la remet dans la zone de saisie.
      setMessages(messages);
      setInput(content);
      setError(messageErreurAssistant(e));
    } finally {
      setBusy(false);
      scrollDown();
    }
  };

  // Ouvert depuis une alerte : poser la question automatiquement (une fois)
  const askedRef = useRef(false);
  useEffect(() => {
    if (ask && invId != null && !askedRef.current) {
      askedRef.current = true;
      send(ask);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask, invId]);

  return (
    <KeyboardAvoidingView
      style={s.bg}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <ScrollView ref={scrollRef} style={s.scroll} contentContainerStyle={s.content} onContentSizeChange={scrollDown}>
        {/* Prévision de demain */}
        <DashboardSection first title="Prévision de demain" subtitle={forecast ? `Production du ${forecast.date}` : undefined}>
          <View style={s.card}>
            {fcBusy ? (
              <ActivityIndicator color={C.primary} />
            ) : fcError ? (
              <Text style={s.muted}>{fcError}</Text>
            ) : forecast ? (
              <>
                <Text style={s.fcValue}>{valeurPrevision(forecast)}</Text>
                <Text style={s.fcRange}>{fourchettePrevision(forecast)}</Text>
                <Text style={s.fcDetail}>{detailPrevision(forecast)}</Text>
                <Text style={s.fcRationale} numberOfLines={4}>{nettoyer(forecast.explication)}</Text>
                <Text style={s.fcMention}>{MENTION_PREVISION}</Text>
              </>
            ) : (
              <Text style={s.muted}>—</Text>
            )}
            <TouchableOpacity style={s.fcBtn} onPress={chargerPrevision} disabled={fcBusy} activeOpacity={0.85}>
              <Text style={s.fcBtnTxt}>Actualiser la prévision</Text>
            </TouchableOpacity>
          </View>
        </DashboardSection>

        {/* Conversation */}
        <DashboardSection title="Assistant de supervision" subtitle="Questions sur votre installation">
          <View style={s.gutter}>
            {messages.map((m, i) => (
              <View key={i} style={[s.bubbleRow, m.role === 'user' ? s.rowRight : s.rowLeft]}>
                <View style={[s.bubble, m.role === 'user' ? s.userBubble : s.aiBubble]}>
                  <Text style={m.role === 'user' ? s.userText : s.aiText}>
                    {m.role === 'user' ? m.content : nettoyer(m.content)}
                  </Text>
                </View>
              </View>
            ))}
            {busy && (
              <View style={[s.bubbleRow, s.rowLeft]}>
                <View style={[s.bubble, s.aiBubble]}><ActivityIndicator color={C.muted} /></View>
              </View>
            )}
            {error ? <Text style={s.error}>{error}</Text> : null}
          </View>
        </DashboardSection>

        {/* Suggestions */}
        <View style={s.suggestRow}>
          {SUGGESTIONS.map((sug) => (
            <TouchableOpacity key={sug} style={s.suggestChip} onPress={() => send(sug)} disabled={busy} activeOpacity={0.85}>
              <Text style={s.suggestTxt}>{sug}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* Zone de saisie */}
      <View style={[s.inputBar, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <TextInput
          style={s.input}
          placeholder="Posez votre question…"
          placeholderTextColor={C.muted}
          value={input}
          onChangeText={setInput}
          multiline
          onSubmitEditing={() => send(input)}
        />
        <TouchableOpacity onPress={() => send(input)} disabled={busy || !input.trim()} activeOpacity={0.85}>
          <View style={[s.sendBtn, (busy || !input.trim()) && s.sendBtnOff]}>
            <Text style={s.sendTxt}>↑</Text>
          </View>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  bg: { flex: 1, backgroundColor: C.bg },
  scroll: { flex: 1 },
  content: { paddingBottom: 20 },
  gutter: { paddingHorizontal: 14, gap: 10 },
  muted: { color: C.muted, fontSize: 13 },

  card: { marginHorizontal: 14, backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 },
  fcValue: { color: C.text, fontSize: 26, fontWeight: '800' },
  fcRange: { color: C.text, fontSize: 14, fontWeight: '600', marginTop: 2 },
  fcDetail: { color: C.muted, fontSize: 13, marginTop: 8 },
  fcMention: { color: C.muted, fontSize: 11, fontStyle: 'italic', marginTop: 8 },
  fcRationale: { color: C.muted, fontSize: 13, marginTop: 10, lineHeight: 18 },
  fcBtn: { marginTop: 14, borderWidth: 1, borderColor: C.primary, borderRadius: 10, height: 38, alignItems: 'center', justifyContent: 'center' },
  fcBtnTxt: { color: C.primary, fontSize: 13, fontWeight: '700' },

  bubbleRow: { flexDirection: 'row' },
  rowLeft: { justifyContent: 'flex-start' },
  rowRight: { justifyContent: 'flex-end' },
  bubble: { maxWidth: '85%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
  userBubble: { backgroundColor: C.primary, borderBottomRightRadius: 4 },
  aiBubble: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderBottomLeftRadius: 4 },
  userText: { color: '#1A1A1A', fontSize: 15, lineHeight: 21, fontWeight: '500' },
  aiText: { color: C.text, fontSize: 15, lineHeight: 21 },
  error: { color: C.red, fontSize: 13, textAlign: 'center', marginTop: 4 },

  suggestRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: 14, marginTop: 14 },
  suggestChip: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8 },
  suggestTxt: { color: C.primary, fontSize: 13, fontWeight: '600' },

  inputBar: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: C.border, backgroundColor: C.surface },
  input: { flex: 1, maxHeight: 120, backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10, color: C.text, fontSize: 15 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: C.primary },
  sendBtnOff: { backgroundColor: C.border },
  sendTxt: { color: '#1A1A1A', fontSize: 20, fontWeight: '800' },
});
