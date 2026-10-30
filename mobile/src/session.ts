/**
 * Session et messages d'erreur des appels au serveur.
 *
 * Le serveur délivre à la connexion un jeton valable un temps limité
 * (JWT_EXPIRE_MINUTES). Passé ce délai, toute requête répond 401 : l'application
 * oublie alors le jeton et revient à l'écran de connexion avec un message clair,
 * au lieu d'afficher « 401: {"detail":"Invalid or expired token"} ».
 *
 * Imports relatifs uniquement : module testable directement avec Node.
 */

export const MESSAGE_SESSION_EXPIREE = 'Session expirée, reconnectez-vous.';

/** Erreur levée par l'API quand le jeton est refusé (401). */
export class SessionExpiree extends Error {
  constructor() {
    super(MESSAGE_SESSION_EXPIREE);
    this.name = 'SessionExpiree';
  }
}

/** Erreur HTTP du serveur (statut + texte brut de la réponse). */
export class ErreurServeur extends Error {
  constructor(public statut: number, public corps: string) {
    super(`${statut}: ${corps}`);   // format historique, testé par certains écrans (« 422 »)
    this.name = 'ErreurServeur';
  }
}

// Reconnaissance par instanceof OU par le nom : selon la configuration de Babel,
// instanceof peut échouer sur une sous-classe d'Error dans React Native.
export function estErreurSession(e: unknown): e is SessionExpiree {
  return e instanceof SessionExpiree || (e as { name?: string } | null)?.name === 'SessionExpiree';
}
export function estErreurServeur(e: unknown): e is ErreurServeur {
  return e instanceof ErreurServeur || (e as { name?: string } | null)?.name === 'ErreurServeur';
}

/** true si une réponse 401 signifie que la session a expiré. Sur /auth/login,
 *  un 401 veut dire « identifiants incorrects » : ce n'est pas une expiration. */
export function estSessionExpiree(statut: number, chemin: string): boolean {
  return statut === 401 && !chemin.startsWith('/auth/');
}

/** Message lisible pour une erreur de l'assistant (ou de la prévision). */
export function messageErreurAssistant(e: unknown): string {
  if (estErreurSession(e)) return MESSAGE_SESSION_EXPIREE;
  if (estErreurServeur(e)) {
    if (e.statut === 503) return "L'assistant n'est pas configuré sur le serveur (clé Ollama absente).";
    if (e.statut === 502) return "Le service d'intelligence artificielle ne répond pas. Réessayez dans un instant.";
    return 'La requête a échoué. Réessayez.';
  }
  // fetch rejeté : serveur injoignable (Wi-Fi, adresse du serveur, backend arrêté)
  return 'Serveur injoignable. Vérifiez la connexion et réessayez.';
}
