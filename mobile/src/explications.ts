/**
 * Explication de la comparaison à la référence (icône « i » de l'accueil et de
 * l'onglet Historique).
 */
export const INFO_PRODUCTION_REFERENCE = {
  titre: 'Production du jour et référence',
  paragraphes: [
    "Elle compare l'énergie produite à l'énergie attendue d'après PVsyst et la météo réelle du site.",
    'La performance compare la production aux heures où l\'installation fonctionnait. La disponibilité indique combien de temps elle a fonctionné pendant qu\'il y avait du soleil.',
    "C'est la performance qui détecte les pertes lentes, comme la poussière : une alerte est levée après 3 jours sous 90 %.",
    "La journée en cours n'est pas comptée : elle n'est pas terminée.",
  ],
  calcul: 'Performance = énergie mesurée ÷ énergie attendue (journée entière si l\'installation a '
    + 'fonctionné tout le temps du soleil, sinon sur les heures de fonctionnement) · '
    + 'Disponibilité = heures de fonctionnement ÷ heures de soleil utile',
};
