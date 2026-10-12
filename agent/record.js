// ===== record.js =====
// Enregistrement image par image de l'etat du heros. S'accroche a pump via
// onFrame ; ne sait rien du hook de frame lui-meme, ni de la barriere.

var KOT = KOT || {};

KOT.record = (function () {
  var CAPACITE = 36000;       // 10 minutes a 60 images/s, soit 720 Ko
  var TAILLE = 20;            // uint32 numero + 4 float (x, y, vx, vy)

  var POS = KOT.symbols.field('position');   // cache au chargement du module
  var Y = 4;                  // sizeof(float) : y suit x dans le vec2

  // Le tampon est alloue une fois pour toutes : rien ne s'alloue dans tick().
  var tampon = null;
  var ecrits = 0;
  var deborde = false;
  var enregistre = false;
  var ancre = 0;              // numero de frame qui porte le numero 0 du run
  var absentes = 0;           // images ou le heros n'etait pas la, ou illisible
  var premiere = true;
  var px = 0.0, py = 0.0;

  // Appelee une fois par image par pump, apres l'increment du compteur. Cout
  // constant : aucune allocation, aucun send(), aucune construction de
  // chaine. Un handler qui deroge a cette regle sur le fil GL a deja tue le
  // jeu une fois (Thread.backtrace dans un piege Frida).
  //
  // La vitesse est la difference avec l'image precedente enregistree : on
  // echantillonne exactement une fois par image, donc elle est juste par
  // construction. On ne lit pas le champ +0x3c du jeu, qui servira de
  // controle croise et non de source.
  function tick (frame) {
    if (!enregistre) return;

    var p = KOT.probe.pointer();
    if (p === null) {
      absentes += 1;
      premiere = true;   // le prochain echantillon ne doit pas voir le trou
      return;
    }
    if (ecrits >= CAPACITE) {
      deborde = true;
      return;
    }

    // Entre le controle ci-dessus et la lecture, l'objet peut avoir ete
    // libere : la garde reste etroite, autour des deux lectures seulement,
    // pour ne masquer aucune autre erreur de logique.
    var pos = p.add(POS);
    var x, y;
    try {
      x = pos.readFloat();
      y = pos.add(Y).readFloat();
    } catch (e) {
      absentes += 1;
      premiere = true;
      return;
    }
    var vx = premiere ? 0.0 : x - px;
    var vy = premiere ? 0.0 : y - py;
    premiere = false;
    px = x;
    py = y;

    var o = tampon.add(ecrits * TAILLE);
    o.writeU32(frame - ancre);
    o.add(4).writeFloat(x);
    o.add(8).writeFloat(y);
    o.add(12).writeFloat(vx);
    o.add(16).writeFloat(vy);
    ecrits += 1;
  }

  return {
    // L'image qui suit cet appel portera le numero 0. Appele jeu en pause :
    // KOT.pump.frame() rend alors le numero de la derniere image achevee.
    start: function () {
      if (tampon === null) tampon = Memory.alloc(CAPACITE * TAILLE);
      ecrits = 0;
      deborde = false;
      absentes = 0;
      premiere = true;
      ancre = KOT.pump.frame() + 1;
      enregistre = true;
    },

    stop: function () { enregistre = false; },

    // A appeler jeu en pause. Le runtime JS de Frida est mono-fil : un drain
    // ne peut pas s'intercaler au milieu d'un enregistrement, seulement entre
    // deux images, pendant que le thread GL dort dans gate().
    //
    // deborde decrit la fenetre qui vient d'etre drainee, comme ecrits : sans
    // cette remise a zero, un deborde ancien resterait vrai indefiniment et
    // un appelant qui draine periodiquement ne pourrait plus distinguer "a
    // deborde depuis le dernier drain" de "a deborde il y a une heure".
    drain: function () {
      var octets = ecrits > 0
        ? tampon.readByteArray(ecrits * TAILLE)
        : new ArrayBuffer(0);
      ecrits = 0;
      deborde = false;
      return octets;
    },

    status: function () {
      return {
        enregistre: enregistre,
        ecrits: ecrits,
        deborde: deborde,
        absentes: absentes,
        ancre: ancre,
        frame: KOT.pump.frame()
      };
    },

    tick: tick
  };
})();

KOT.pump.onFrame(KOT.record.tick);
