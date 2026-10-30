// Test natif du modèle de simulation PV (g++ -std=c++17 -Iinclude test/test_solar_sim.cpp)
#include "solar_sim.h"
#include <cassert>
#include <cstdio>

int main() {
  using namespace solar;

  // Nuit : aucune production
  assert(dayFactor(0.0) == 0.0);
  assert(dayFactor(5.0) == 0.0);
  assert(dayFactor(23.0) == 0.0);
  assert(dayFactor(LEVER) == 0.0 && dayFactor(COUCHER) == 0.0);

  // Midi : production maximale (proche de 1)
  assert(dayFactor(12.0) > 0.95);

  // Montée le matin : croissance monotone de 6 h à 12 h
  double prev = -1.0;
  for (double h = 6.5; h <= 12.0; h += 0.5) {
    double v = dayFactor(h);
    assert(v > prev);
    prev = v;
  }

  // Symétrie autour de midi
  assert(std::abs(dayFactor(9.0) - dayFactor(15.0)) < 1e-9);

  // Encrassement : réduit la production, bornes respectées
  assert(std::abs(factor(12.0, 0.0) - dayFactor(12.0)) < 1e-9);
  assert(factor(12.0, 0.20) < factor(12.0, 0.0));
  assert(std::abs(factor(12.0, 0.50) - dayFactor(12.0) * 0.5) < 1e-9);
  assert(factor(12.0, -1.0) == dayFactor(12.0));   // soiling clampé à 0
  assert(factor(12.0, 2.0) == 0.0);                // soiling clampé à 1

  // Puissance crête
  assert(std::abs(powerW(12.0, 0.0, 3000.0) - dayFactor(12.0) * 3000.0) < 1e-6);
  assert(powerW(0.0, 0.0, 3000.0) == 0.0);

  // Énergie du jour : nulle avant le lever, maximale après le coucher
  const double pk = peakWForMonth(10);
  assert(energySinceSunriseKwh(5.0, 0.0, pk) == 0.0);
  assert(std::abs(energySinceSunriseKwh(12.0, 0.0, pk) * 2 - energySinceSunriseKwh(18.0, 0.0, pk)) < 1e-9);
  assert(energySinceSunriseKwh(23.0, 0.0, pk) == energySinceSunriseKwh(18.0, 0.0, pk));

  // Journée complète = REALISME × référence PVsyst du mois (jamais > 100 %)
  for (int m = 1; m <= 12; m++) {
    const double e = energySinceSunriseKwh(18.0, 0.0, peakWForMonth(m));
    assert(std::abs(e / dailyReferenceKwh(m) - REALISME) < 1e-9);
  }

  // L'intégrale exacte correspond à la somme numérique de powerW
  double somme = 0.0;
  const double dt = 1.0 / 3600.0;   // pas d'une seconde
  for (double h = 6.0; h < 15.0; h += dt) somme += powerW(h + dt / 2, 0.1, pk) / 1000.0 * dt;
  assert(std::abs(somme - energySinceSunriseKwh(15.0, 0.1, pk)) < 0.01);

  // ---- Modèle piloté par la météo réelle ----
  // P = 10 800 × G_incl/1000 × PR(octobre = 0,880)
  assert(std::abs(puissanceDepuisIrradiance(1000.0, 10, 0.0) - 10800.0 * 0.880) < 1e-6);
  assert(puissanceDepuisIrradiance(-5.0, 10, 0.0) == 0.0);
  assert(std::abs(puissanceDepuisIrradiance(800.0, 10, 0.2) - 0.8 * puissanceDepuisIrradiance(800.0, 10, 0.0)) < 1e-6);

  // Tension : nulle la nuit, = 9 × 39,44 V aux conditions STC (fiche JA Solar), baisse quand il fait chaud
  assert(tensionChaine(0.0, 25.0) == 0.0);
  assert(std::abs(tensionChaine(1000.0, 25.0) - 9 * 39.44) < 1e-9);
  assert(tensionChaine(1000.0, 50.0) < tensionChaine(1000.0, 25.0));

  // Courant d'une chaîne (pv_i) : moitié du courant total, 0 la nuit
  // 8 000 W sur 2 chaînes à 370 V → 10,81 A par chaîne (21,62 A au total)
  assert(std::abs(courantChaine(8000.0, 370.0) - 8000.0 / 2 / 370.0) < 1e-9);
  assert(std::abs(courantChaine(8000.0, 370.0) * NB_CHAINES * 370.0 - 8000.0) < 1e-6);
  assert(courantChaine(8000.0, 0.0) == 0.0 && courantChaine(0.0, 370.0) == 0.0);

  // Deux chaînes : chaîne 2 = chaîne 1 × (1 + e), e dans [−1 % ; +1 %]
  for (int k = -4; k <= 4; k++) {
    const double e = k * 0.0025;
    const MesuresChaines m = deuxChaines(8000.0, 370.0, e, -e, 0.0, false);
    assert(std::abs(m.v1 - 370.0) < 1e-9 && std::abs(m.i1 - 8000.0 / 2 / 370.0) < 1e-9);
    assert(std::abs(m.v2 - 370.0 * (1 + e)) < 1e-9);
    assert(std::abs(m.i2 - m.i1 * (1 - e)) < 1e-9);
    assert(ecartChainesPct(m.p1(), m.p2()) < 0.02);             // (1+e)(1−e) ≈ 1
    // pv_p = somme des deux chaînes
    assert(std::abs(m.puissanceTotale() - (m.v1 * m.i1 + m.v2 * m.i2)) < 1e-9);
  }
  // Désappariement stable : mêmes e → même écart à chaque message ; bruit ±0,5 V
  {
    const MesuresChaines a = deuxChaines(8000.0, 370.0, 0.008, 0.006, 0.5, false);
    const MesuresChaines b = deuxChaines(8000.0, 370.0, 0.008, 0.006, -0.5, false);
    assert(std::abs(a.i2 - b.i2) < 1e-12 && std::abs(a.v2 - b.v2 - 1.0) < 1e-9);
    const double ecart = ecartChainesPct(a.p1(), a.p2());
    assert(ecart > 1.0 && ecart < 2.0);                          // ≈ 1,4 % : vert (< 5 %)
  }
  // e hors bornes : ramené à ±1 %
  assert(std::abs(deuxChaines(8000.0, 370.0, 0.05, 0.05, 0.0, false).i2 / (8000.0 / 2 / 370.0) - 1.01) < 1e-9);
  // SIM_DEFAUT_CHAINE2 = 1 : courant nul, tension à vide, écart > 15 % (100 %)
  {
    const MesuresChaines m = deuxChaines(8000.0, 370.0, 0.003, 0.003, 0.2, true);
    assert(m.i2 == 0.0 && std::abs(m.v2 - 370.0 * RAPPORT_VOC_VMP) < 1e-9);
    assert(ecartChainesPct(m.p1(), m.p2()) > 15.0);
    assert(std::abs(m.puissanceTotale() - 4000.0) < 1e-6);       // moitié de la puissance
  }
  // Nuit : tout est nul (bruit ignoré), écart nul
  {
    const MesuresChaines m = deuxChaines(0.0, 0.0, 0.01, 0.01, 0.4, false);
    assert(m.v2 == 0.0);
    assert(m.i1 == 0.0 && m.i2 == 0.0 && ecartChainesPct(m.p1(), m.p2()) == 0.0);
  }

  // Séries 15 min : valeur constante → interpolation et intégrale exactes
  float serie[96];
  for (int i = 0; i < 96; i++) serie[i] = 600.0f;
  assert(std::abs(serieInstantanee(serie, 96, 12 * 60.0) - 600.0) < 1e-9);
  assert(std::abs(serieIntegraleWhM2(serie, 96, 60.0) - 600.0) < 1e-9);             // 1 h à 600 W/m²
  assert(std::abs(serieIntegraleWhM2(serie, 96, 1440.0) - 600.0 * 95 / 4) < 1e-6);   // 95 intervalles du jour
  // Rampe : au milieu d'un intervalle on retrouve sa valeur, entre deux on interpole
  for (int i = 0; i < 96; i++) serie[i] = (float)i;
  assert(std::abs(serieInstantanee(serie, 96, 15.0 * 10 - 7.5) - 10.0) < 1e-9);
  assert(std::abs(serieInstantanee(serie, 96, 15.0 * 10) - 10.5) < 1e-9);

  // Facteur de performance : toujours dans [0,76 ; 0,94], moyenne ≈ 0,85
  double somme_f = 0.0, fmin = 1.0, fmax = 0.0;
  const int N = 200000;
  for (int i = 0; i < N; i++) {
    const double t = i * 0.5;                       // un envoi toutes les 0,5 s
    const double alea = ((i * 7919) % 201) / 100.0 - 1.0;
    const double fp = facteurPerformance(t, alea);
    somme_f += fp; if (fp < fmin) fmin = fp; if (fp > fmax) fmax = fp;
  }
  assert(fmin >= PERF_MIN && fmax <= PERF_MAX);
  assert(std::abs(somme_f / N - PERF_MOYENNE) < 0.005);
  assert(facteurPerformance(0.0, 5.0) <= PERF_MAX && facteurPerformance(0.0, -5.0) >= PERF_MIN);

  std::printf("OK — tous les tests de solar_sim passent.\n");
  return 0;
}
