/**
 * Session expirée et messages d'erreur de l'assistant.
 * Lancer avec : npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  ErreurServeur, MESSAGE_SESSION_EXPIREE, SessionExpiree, estSessionExpiree, messageErreurAssistant,
} from '../session';

test('401 = session expirée, sauf sur /auth/login (identifiants incorrects)', () => {
  assert.equal(estSessionExpiree(401, '/inverters/3/assistant'), true);
  assert.equal(estSessionExpiree(401, '/installations'), true);
  assert.equal(estSessionExpiree(401, '/auth/login'), false);
  assert.equal(estSessionExpiree(403, '/inverters/3/latest'), false);
  assert.equal(estSessionExpiree(500, '/inverters/3/latest'), false);
});

test('messages lisibles au lieu de « 401: {"detail":…} »', () => {
  assert.equal(messageErreurAssistant(new SessionExpiree()), MESSAGE_SESSION_EXPIREE);
  assert.equal(MESSAGE_SESSION_EXPIREE, 'Session expirée, reconnectez-vous.');
  assert.match(messageErreurAssistant(new ErreurServeur(503, 'Assistant unavailable')), /pas configuré/);
  assert.match(messageErreurAssistant(new ErreurServeur(502, 'LLM provider error')), /ne répond pas/);
  assert.equal(messageErreurAssistant(new ErreurServeur(400, 'x')), 'La requête a échoué. Réessayez.');
  assert.match(messageErreurAssistant(new TypeError('Network request failed')), /Serveur injoignable/);
  for (const e of [new SessionExpiree(), new ErreurServeur(502, '{"detail":"x"}')]) {
    assert.ok(!messageErreurAssistant(e).includes('detail'));
  }
});

test('reconnaissance par le nom si instanceof échoue (classes transformées par Babel)', () => {
  const imitation = Object.assign(new Error('401'), { name: 'SessionExpiree' });
  assert.equal(messageErreurAssistant(imitation), MESSAGE_SESSION_EXPIREE);
  const serveur = Object.assign(new Error('503: x'), { name: 'ErreurServeur', statut: 503 });
  assert.match(messageErreurAssistant(serveur), /pas configuré/);
});

test('le texte des erreurs serveur garde le format « 422: … » (testé par les écrans)', () => {
  const e = new ErreurServeur(422, '{"detail":"Pas encore de journée complète"}');
  assert.ok(e.message.includes('422'));
  assert.ok(e instanceof Error && e.statut === 422);
});
