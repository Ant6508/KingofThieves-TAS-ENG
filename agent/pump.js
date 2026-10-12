// ===== pump.js =====
// Possede le compteur de frames et la barriere. Ne sait rien des taps.
//
// Convention : le hook agit en onEnter, jamais en onLeave, jamais les deux.
// La frame N designe l'etat du jeu avant l'execution de la Nieme image.

var KOT = KOT || {};

KOT.pump = (function () {
  var FREE = -1;              // le jeu tourne librement
  var POLL_SECONDS = 0.001;
  var WATCHDOG_MS = 10000;    // au-dela, on considere le controleur mort

  var frame = 0;
  var granted = FREE;     // FREE, ou nombre de frames encore accordees
  var jniEnv = null;
  var listeners = [];
  var installed = false;
  var lastSeen = Date.now();

  // Millisecondes de temps reel a garantir entre deux images relachees.
  // 0 desactive le cadencement, et c'est le reglage normal. Voir cadencer().
  // Rendu sans objet par l'horloge virtuelle : quand elle tient, la vitesse
  // de relachement n'a plus aucun effet sur la simulation.
  var rythmeMs = 0;
  var derniereImage = 0;

  // ----- Horloge virtuelle -----
  //
  // Le temps du jeu n'est pas lu en natif : il est calcule cote Java et livre
  // en troisieme argument de nativeDrawFrame, en millisecondes entieres.
  // Mesure du 2026-09-18 : force a zero, la simulation s'arrete net -- 70
  // images rendues, zero mobile, deplacement 0,0000 px -- alors que les images
  // continuent d'etre rendues. Voir NOTES.md, "La source de temps du jeu".
  //
  // Le cycle 16, 17, 17 et non une constante : le moteur depense 16,667 ms
  // par pas de physique, donc 17 constant laisserait 0,33 ms d'excedent par
  // image, soit un pas de trop toutes les cinquante images -- exactement la
  // panne mesuree avec le cadencement a 20 ms. Le cycle donne 50 ms pour trois
  // images, soit trois pas pour trois images, sans derive possible.
  //
  // Indexe sur le compteur d'images et non sur une horloge : c'est ce qui rend
  // la suite reproductible d'un rejeu a l'autre.
  var CYCLE_MS = [16, 17, 17];
  var horlogeVirtuelle = false;

  // Index dans le cycle. Il appartient au RUN, pas a l'agent : voir horloge().
  var cycleIndex = 0;

  // ----- Turbo -----
  //
  // eglSwapBuffers presente l'image et attend la synchronisation verticale.
  // Neutralisee, elle rend EGL_TRUE sans rien presenter : le rendu continue,
  // l'attente disparait, et le thread GL encaisse autant d'images que la
  // machine en produit. La fenetre reste sur sa derniere image, ce qui est le
  // comportement voulu pendant un rejeu.
  //
  // Le NativeCallback est garde dans une variable de module : ramasse par le
  // GC, il laisserait un trampoline mort dans le processus.
  var turboActif = false;
  var swapNeutre = null;

  function turbo (actif) {
    var adresse = KOT.symbols.require('swapBuffers');
    if (actif && !turboActif) {
      if (swapNeutre === null) {
        swapNeutre = new NativeCallback(function (dpy, surface) {
          return 1;   // EGL_TRUE
        }, 'int', ['pointer', 'pointer']);
      }
      Interceptor.replace(adresse, swapNeutre);
      turboActif = true;
    } else if (!actif && turboActif) {
      Interceptor.revert(adresse);
      turboActif = false;
    }
    return turboActif;
  }

  // Chien de garde : si le controleur meurt ou se deconnecte alors que le jeu
  // est en pause, la barriere doit se relacher d'elle-meme. Un jeu fige pour
  // toujours est pire qu'une pause perdue.
  function controllerAlive () {
    return (Date.now() - lastSeen) < WATCHDOG_MS;
  }

  // Cadencement des images relachees. GARDE POUR LA MESURE, PAS POUR L'USAGE.
  //
  // Le jeu consomme le temps reel dans un accumulateur et depense 16,67 ms
  // par pas de physique. Tout rythme impose au-dela laisse un excedent qui
  // finit par valoir un pas entier : mesure du 2026-09-18, a 20 ms un doublon
  // toutes les 16,67/(20-16,67) = 5 images, exactement. Bilan sur 300 images,
  // 26 anomalies cadence a 20 ms contre 2 sans cadencement.
  //
  // Le bon cadenceur est la synchronisation verticale du jeu, qui vaut
  // 16,67 ms par construction : le reglage normal est donc rythmeMs = 0.
  // Il reste expose parce qu'il a servi a etablir le modele de
  // l'accumulateur, et qu'il le reetablira.
  //
  // Mesure ici et non depuis le controleur : un aller-retour RPC ajoute sa
  // propre gigue, qui est precisement ce qu'on cherche a supprimer.
  function cadencer () {
    if (rythmeMs <= 0) return;
    var reste = rythmeMs - (Date.now() - derniereImage);
    while (reste > 0) {
      Thread.sleep(reste / 1000);
      reste = rythmeMs - (Date.now() - derniereImage);
    }
    derniereImage = Date.now();
  }

  function gate () {
    if (granted === FREE) return;

    while (granted === 0) {
      // Thread.sleep relache le verrou du runtime JS : le RPC peut donc
      // s'executer pendant que ce thread attend. Verifie a l'etape 4.
      Thread.sleep(POLL_SECONDS);

      if (granted === FREE) return;

      if (!controllerAlive()) {
        send('watchdog: controller silent for ' +
             WATCHDOG_MS + ' ms, barrier released');
        granted = FREE;
        return;
      }
    }

    granted -= 1;

    cadencer();
  }

  function install () {
    if (installed) return;

    Interceptor.attach(KOT.symbols.require('drawFrame'), {
      onEnter: function (args) {
        jniEnv = args[0];

        gate();

        frame += 1;

        // Avant les auditeurs : ils observent l'etat d'avant l'image, mais le
        // delta doit etre en place quand le corps de la fonction s'executera.
        if (horlogeVirtuelle) {
          args[2] = ptr(CYCLE_MS[cycleIndex % CYCLE_MS.length]);
          cycleIndex += 1;
        }

        for (var i = 0; i < listeners.length; i++) {
          listeners[i](frame);
        }
      }
    });

    installed = true;
  }

  return {
    install: install,
    frame: function () { return frame; },
    env: function () { return jniEnv; },
    onFrame: function (callback) { listeners.push(callback); },

    pause:  function () { granted = 0; },
    resume: function () { granted = FREE; },
    step:   function (n) { granted = n; },
    paused: function () { return granted !== FREE; },

    // Appele par le controleur pour signaler qu'il est toujours en vie.
    heartbeat: function () { lastSeen = Date.now(); },

    // Millisecondes de temps reel a garantir entre deux images relachees.
    // 0 desactive. Voir cadencer().
    rythme: function (ms) {
      rythmeMs = ms;
      derniereImage = Date.now();
      return rythmeMs;
    },

    // Detache le temps de jeu du temps reel : chaque image rendue recoit
    // exactement un pas de physique, quelle que soit la vitesse a laquelle on
    // la relache. Voir CYCLE_MS.
    //
    // La phase du cycle repart de zero a chaque activation, donc a chaque
    // ancrage : controller/run.py active l'horloge barriere fermee, juste
    // avant record_start. Indexee sur le compteur global, la phase aurait
    // dependu du nombre d'images ecoulees depuis le chargement du script --
    // une variable qu'aucun film ne peut porter.
    horloge: function (actif) {
      horlogeVirtuelle = !!actif;
      cycleIndex = 0;
      return horlogeVirtuelle;
    },

    horlogeTenue: function () { return horlogeVirtuelle; },

    // Le cycle lui-meme, pour que le controleur refuse de rejouer un film
    // enregistre sous un autre.
    cycle: function () { return CYCLE_MS.slice(); },

    turbo: turbo,

    turboTenu: function () { return turboActif; }
  };
})();
