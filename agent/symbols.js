// ===== symbols.js =====
// Unique depositaire de la connaissance du binaire.
// Une mise a jour du jeu ne doit casser que ce fichier.

var KOT = KOT || {};

KOT.symbols = (function () {
  // Le nom du binaire du jeu n'est ecrit qu'ici.
  var MODULE = 'libthieves.so';

  var REQUIRED = {
    drawFrame:   [MODULE,      'Java_com_zf_ZRenderer_nativeDrawFrame'],
    passTouch:   [MODULE,      'Java_com_zf_ZRenderer_nativePassTouch'],
    swapBuffers: ['libEGL.so', 'eglSwapBuffers']
  };

  // Offsets releves le 2026-09-17 sur King of Thieves 2.83, par watchpoint
  // materiel. Voir NOTES.md, "Sonde d'etat du heros - TROUVEE".
  // Reportes sur 2.84 (versionCode 4755781) le 2026-09-28 : voir NOTES.md,
  // "Passage a 2.84".
  // Tous relatifs a la base de libthieves.so : aucune adresse absolue.
  var OFFSETS = {
    heroVtable:     0x1f466f0,   // vtable de la classe du heros
    positionGetter: 0x1d9d0f0    // BaseElement::getPos : movups xmm0, [rdi+0x34] ; ret
  };

  // Offsets a l'interieur des objets, en octets.
  var FIELDS = {
    vtableSlot: 0x268,   // slot du getter de position dans la vtable
    position:   0x34,    // (x, y) vivants, deux float
    previous:   0x3c,    // (x, y) de l'image precedente
    recorder:   0x1d0    // pointeur vers l'enregistreur de trace
  };

  var resolved = {};
  var missing = [];

  Object.keys(REQUIRED).forEach(function (name) {
    var moduleName = REQUIRED[name][0];
    var exportName = REQUIRED[name][1];
    var address = null;

    try {
      // Forme portable entre Frida 16 et 17 : le statique
      // Module.findExportByName a disparu en 17.
      address = Process.getModuleByName(moduleName).findExportByName(exportName);
    } catch (e) {
      address = null;
    }

    if (address === null || address.isNull()) {
      missing.push(name + ' (' + moduleName + '!' + exportName + ')');
    } else {
      resolved[name] = address;
    }
  });

  // Controle de coherence : la vtable doit porter le getter de position au
  // slot attendu. C'est ce qui distingue "les offsets sont bons" de "les
  // offsets pointent quelque part". Si ca ne colle pas, la session refusera
  // de demarrer, ce qui est le comportement voulu.
  //
  // N'emet jamais d'exception : un echec s'inscrit dans missing, comme pour
  // un symbole absent. Une exception ici laisserait KOT.symbols indefini
  // pour tous les fichiers charges ensuite.
  function verifierVtableDuHeros () {
    var thieves = null;
    try {
      thieves = Process.getModuleByName(MODULE);
    } catch (e) {
      missing.push(MODULE + ' (module not found)');
      return;
    }

    var attendu = thieves.base.add(OFFSETS.positionGetter);
    var trouve = null;
    try {
      trouve = thieves.base.add(OFFSETS.heroVtable)
                           .add(FIELDS.vtableSlot).readPointer();
    } catch (e) {
      trouve = null;
    }

    if (trouve === null || !trouve.equals(attendu)) {
      missing.push(
        'heroVtable: ' + MODULE + '+0x' + OFFSETS.heroVtable.toString(16) +
        ' does not carry the position getter at slot 0x' +
        FIELDS.vtableSlot.toString(16) +
        ' (expected +0x' + OFFSETS.positionGetter.toString(16) +
        ', found ' + (trouve === null ? 'unreadable' : trouve.toString()) + ').' +
        ' The game was probably updated: the offsets above only hold' +
        ' for 2.84. Run scripts/reverse/sonde.py again to find them,' +
        ' then fix OFFSETS in agent/symbols.js and NOTES.md.'
      );
    }
  }

  verifierVtableDuHeros();

  return {
    require: function (name) {
      var address = resolved[name];
      if (address === undefined) {
        throw new Error('unresolved symbol: ' + name);
      }
      return address;
    },

    // Adresse absolue d'un offset de module, resolue a chaque appel : le
    // module est retrouve par son nom, jamais mis en cache.
    address: function (name) {
      if (OFFSETS[name] === undefined) {
        throw new Error('unknown offset: ' + name);
      }
      return Process.getModuleByName(MODULE).base.add(OFFSETS[name]);
    },

    // Offset a l'interieur d'un objet, en octets. Contrairement a address(),
    // ne rend pas un pointeur : l'appelant l'ajoute a l'adresse d'un objet
    // vivant. Appele une fois par image, donc ne resout rien.
    field: function (name) {
      if (FIELDS[name] === undefined) {
        throw new Error('unknown field: ' + name);
      }
      return FIELDS[name];
    },

    describe: function () {
      var out = {};
      Object.keys(resolved).forEach(function (key) {
        out[key] = resolved[key].toString();
      });
      var offs = {};
      Object.keys(OFFSETS).forEach(function (key) {
        offs[key] = '0x' + OFFSETS[key].toString(16);
      });
      return { resolved: out, offsets: offs, missing: missing };
    },

    missing: function () {
      return missing;
    }
  };
})();
