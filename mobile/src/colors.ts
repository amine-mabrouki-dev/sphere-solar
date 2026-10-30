// Charte graphique Sphere Solar (identique sur tous les écrans)
export const C = {
  // Surfaces
  bg: '#07152B',          // fond d'écran
  surface: '#0F2238',     // cartes
  card: '#0F2238',
  border: '#1E3550',      // bordure des cartes

  // Accent & sémantique
  primary: '#E08E0B',     // orange (accent / boutons / mesuré)
  accent: '#3B82F6',
  bottomBar: '#0B1A30',   // barre d'onglets

  // Texte
  text: '#FFFFFF',
  muted: '#8FA3BF',       // texte secondaire

  // États
  green: '#2E8B57',       // normal
  yellow: '#E08E0B',      // vigilance (orange)
  red: '#C0392B',         // anomalie / alertes
  ref: '#7A8BA3',         // gris de référence (production attendue)

  // Overlays
  cardOverlay: 'rgba(255,255,255,0.06)',
} as const;
