// ===== rpc.js =====
// Traduit les appels du controleur vers les modules. Aucune logique propre.

KOT.pump.install();

rpc.exports = {
  ping: function () {
    return 'pong';
  },

  symbols: function () {
    return KOT.symbols.describe();
  },

  // camelCase cote JS : frida convertit en snake_case cote Python
  // (s.api.probe_resolve() appelle bien probeResolve ici). Voir le plan
  // fondation, tache 8, note sur tapNow / tap_now.
  probeResolve: function () {
    return KOT.probe.resolve();
  },

  probeState: function () {
    return KOT.probe.state();
  },

  probeAlive: function () {
    return KOT.probe.alive();
  },

  recordStart: function () {
    KOT.record.start();
    return KOT.record.status();
  },

  recordStop: function () {
    KOT.record.stop();
    return KOT.record.status();
  },

  recordDrain: function () {
    return KOT.record.drain();
  },

  recordStatus: function () {
    return KOT.record.status();
  },

  frame: function () {
    return KOT.pump.frame();
  },

  pause: function () {
    KOT.pump.pause();
    return KOT.pump.frame();
  },

  resume: function () {
    KOT.pump.resume();
    return KOT.pump.frame();
  },

  step: function (n) {
    KOT.pump.step(n);
    return KOT.pump.frame();
  },

  paused: function () {
    return KOT.pump.paused();
  },

  heartbeat: function () {
    KOT.pump.heartbeat();
    return KOT.pump.frame();
  },

  rythme: function (ms) {
    return KOT.pump.rythme(ms);
  },

  horloge: function (actif) {
    return KOT.pump.horloge(actif);
  },

  horlogeTenue: function () {
    return KOT.pump.horlogeTenue();
  },

  cycle: function () {
    return KOT.pump.cycle();
  },

  turbo: function (actif) {
    return KOT.pump.turbo(actif);
  },

  turboTenu: function () {
    return KOT.pump.turboTenu();
  }
};
