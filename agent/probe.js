// ===== probe.js =====
// Retrouve le heros par identite de classe, et lit son etat.
// Ne sait pas quand le faire : c'est pump qui decide.

var KOT = KOT || {};

KOT.probe = (function () {
  var RANGE_MAX = 300 * 1024 * 1024;   // au-dela, ce n'est pas un tas d'objets
  var BORNE = 1e5;                     // l'espace du jeu fait 960 x 640

  // La position est un vec2 : y suit x d'un float. Ce 4 est sizeof(float),
  // pas un offset du binaire ; il n'a donc rien a faire dans symbols.js.
  var Y = 4;

  var heros = null;      // NativePointer, ou null
  var vtable = null;     // vtable du heros, mise en cache a la resolution

  // Motif de 8 octets, petit-boutiste, pour Memory.scanSync.
  function motif (p) {
    var hex = ptr(p).toString(16).padStart(16, '0');
    var m = '';
    for (var i = 14; i >= 0; i -= 2) {
      m += hex.substr(i, 2) + ' ';
    }
    return m.trim();
  }

  // Un objet est plausible s'il a un enregistreur qui pointe quelque part et
  // des coordonnees finies et bornees. Ecarte les restes non initialises : sur
  // le processus de reference, 3 objets portaient la vtable, dont 2 restes
  // (y = 9,1e8, enregistreur nul).
  function plausible (p) {
    try {
      var rec = p.add(KOT.symbols.field('recorder')).readPointer();
      if (rec.isNull() || Process.findRangeByAddress(rec) === null) return false;
      var pos = p.add(KOT.symbols.field('position'));
      var x = pos.readFloat();
      var y = pos.add(Y).readFloat();
      return isFinite(x) && isFinite(y) &&
             Math.abs(x) < BORNE && Math.abs(y) < BORNE;
    } catch (e) {
      return false;
    }
  }

  // Rend les objets retenus, et combien portaient la vtable avant filtrage.
  // Les deux comptes repondent a deux questions differentes quand le resultat
  // est vide : zero vu = l'offset de vtable ne vaut plus rien (jeu mis a
  // jour) ; vus mais zero retenu = le filtre est trop serre, ou le heros
  // n'existe pas encore. Sans cette distinction, les deux pannes ont le meme
  // symptome et on ne sait pas laquelle chercher.
  function candidats () {
    vtable = KOT.symbols.address('heroVtable');
    var m = motif(vtable);
    var out = [];
    var vus = 0;
    var ranges = Process.enumerateRanges('rw-');

    for (var k = 0; k < ranges.length; k++) {
      if (ranges[k].file || ranges[k].size > RANGE_MAX) continue;
      var hits;
      try {
        hits = Memory.scanSync(ranges[k].base, ranges[k].size, m);
      } catch (e) {
        continue;
      }
      vus += hits.length;
      for (var j = 0; j < hits.length; j++) {
        if (plausible(hits[j].address)) out.push(hits[j].address);
      }
    }
    return { vus: vus, retenus: out };
  }

  // Le heros est-il toujours la ? Une lecture de pointeur, assez bon marche
  // pour le hook de frame. Repond faux dans deux cas que l'appelant ne peut
  // pas distinguer : jamais resolu, et resolu puis disparu. Les deux appellent
  // la meme reaction, un nouveau resolve().
  //
  // Limite connue, a mesurer : ceci prouve que la memoire porte toujours la
  // vtable du heros, pas que c'est le meme heros. Si l'allocateur reutilise le
  // bloc entre une mort et une reapparition, la reponse resterait vraie et une
  // trace recollerait deux vies distinctes sans le signaler. Verifie a la
  // tache 4 en mourant volontairement. Voir NOTES.md.
  function vivant () {
    if (heros === null || vtable === null) return false;
    try {
      return heros.readPointer().equals(vtable);
    } catch (e) {
      return false;
    }
  }

  return {
    // Coute environ 0,7 s : a n'appeler que jeu en pause, jamais par image.
    resolve: function () {
      var trouves = candidats();
      heros = trouves.retenus.length > 0 ? trouves.retenus[0] : null;
      // Le premier gagne, mais objets dit combien il y en avait : c'est a
      // l'appelant de refuser de continuer si ce n'est pas exactement 1.
      return {
        vus: trouves.vus,
        objets: trouves.retenus.length,
        heros: heros === null ? null : String(heros)
      };
    },

    pointer: function () { return vivant() ? heros : null; },
    alive: vivant,

    // Diagnostic et RPC seulement : alloue un objet a chaque appel. Le hook
    // de frame lit pointer() et les champs directement, sans passer par ici.
    state: function () {
      if (!vivant()) return null;
      var pos = heros.add(KOT.symbols.field('position'));
      var pre = heros.add(KOT.symbols.field('previous'));
      return {
        x: pos.readFloat(),  y: pos.add(Y).readFloat(),
        px: pre.readFloat(), py: pre.add(Y).readFloat()
      };
    }
  };
})();
