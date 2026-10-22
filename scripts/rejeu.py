# -*- coding: utf-8 -*-
"""rejeu.py - rejouer un film, et dire si le rejeu est conforme.

Chaque essai part d'un jeu fraichement relance : c'est la seule condition de
depart bit-exacte (kot_headless/docs/savoir/jeu/horloge.md). L'operateur renavigue ensuite
jusqu'a l'ecran de commencement et confirme d'une touche -- voir
controller/depart.py pour ce qui a ete essaye avant, et pourquoi.

Le verdict porte sur deux choses, et la seconde n'est pas cosmetique :

- l'empreinte, qui prouve que la physique du heros s'est rejouee a l'identique ;
- ce que le heros a subi, qui y est aussi : un run ou un piege le touche porte
  la marque du piege dans sa trajectoire. Un run ou rien ne le touche ne dit
  rien de la phase des pieges -- l'empreinte ne porte que le heros.

Un essai se mene en deux temps, parce que la navigation est manuelle :

    python scripts/rejeu.py films/reference.json --relance
    ... l'operateur renavigue jusqu'a l'ecran de commencement ...
    python scripts/rejeu.py films/reference.json

Le premier essai s'ecrit avec --ecrire, qui fixe l'empreinte de reference dans
le film ; les suivants s'y comparent. Trois essais concordants, c'est trois
fois cette paire de commandes.
"""

import os
import sys
import time

# Lance depuis scripts/, la racine du depot n'est pas dans sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller.movie import (  # noqa: E402
    load_movie,
    save_movie,
    verifier_rejouable,
)
from controller.depart import DepartError, au_depart, lire_position  # noqa: E402
from controller.relance import relancer  # noqa: E402
from controller.run import Run, derouler  # noqa: E402
from controller.session import Session, version_attendue  # noqa: E402
from controller.trace import (  # noqa: E402
    decode,
    decrire_divergence,
    ecart_maximal,
    empreinte,
    encode,
    est_significative,
    images_doublees,
    images_figees,
    images_mobiles,
)

CHEMIN = sys.argv[1] if len(sys.argv) > 1 else "films/reference.json"
ECRIRE = False
TURBO = False
RELANCE_SEULE = False
# Fichier ou ecrire la trace de cet essai, et fichier auquel la comparer.
TRACE = None
REFERENCE = None
for _arg in sys.argv[2:]:
    if _arg == "--ecrire":
        ECRIRE = True
    elif _arg == "--turbo":
        TURBO = True
    elif _arg == "--relance":
        RELANCE_SEULE = True
    elif _arg.startswith("--trace="):
        TRACE = _arg.split("=", 1)[1]
    elif _arg.startswith("--contre="):
        REFERENCE = _arg.split("=", 1)[1]


def un_essai(session, movie):
    """Un essai, l'operateur etant deja a l'ecran de commencement.

    La position du heros est relue et confrontee a celle du film : elle ne dit
    pas sur quel ecran on est (voir controller/depart.py), mais elle attrape un
    donjon remodele, dont l'empreinte ne vaudrait plus rien.
    """
    print("   attaching...")
    session.attacher_avec_reessais()
    verifier_rejouable(movie, tuple(session.api.cycle()))

    attendu = (movie.start.hero_x, movie.start.hero_y)
    position = lire_position(session.api)
    if position is None:
        raise DepartError(
            "exactly one hero is expected in memory. Are you on the starting "
            "screen?"
        )
    if au_depart(position, attendu[0], attendu[1]):
        print(f"   start at {position}, same as when recorded")
    else:
        # Avertissement et non refus : la position suit le cadrage de la
        # camera et non la forme du donjon. Mesure du 2026-09-18, meme donjon,
        # deux seances : (352, 548) puis (96, 548). Refuser la-dessus
        # bloquerait des rejeux parfaitement legitimes. C'est l'empreinte qui
        # tranche, quelques secondes plus tard.
        print(f"   start at {position}, while the movie carried {attendu}."
              f" The position follows the camera: if the dungeon really"
              f" changed, the fingerprint will tell.")

    run = Run(session.api)
    try:
        run.ancrer()
        if TURBO:
            session.api.turbo(True)
        debut = time.monotonic()
        derouler(run, [i.frame for i in movie.inputs], movie.run_frames)
        duree = time.monotonic() - debut
    finally:
        run.terminer()

    if duree > 0:
        print(f"   {len(run.trace)} frames in {duree:.2f} s "
              f"= {len(run.trace) / duree:.1f} frames/s"
              f"{'  (turbo)' if TURBO else ''}")
    return run


def decrire(run):
    trace = run.trace
    if not trace:
        return "   no frame recorded"
    statut, image = run.issue()
    depart = f"   start x={trace[0].x!r} y={trace[0].y!r}"
    fin = f"   outcome: {statut}"
    if image is not None:
        fin += f" at frame {image}"
    return "\n".join([
        f"   {len(trace)} frames, {images_mobiles(trace)} with movement",
        f"   frozen {images_figees(trace)}, "
        f"doubled {images_doublees(trace)}",
        depart,
        fin,
    ])


def verdict(movie, runs):
    print("\n" + "=" * 60)

    if not runs:
        print("no try run: nothing to conclude.")
        return 3

    traces = [r.trace for r in runs]
    if any(not est_significative(t) for t in traces):
        print("WORTHLESS TEST: the hero doesn't move enough.")
        print("A motionless hero gives as many identical fingerprints as you")
        print("like without the game doing anything. Place a jump in the movie.")
        return 2

    empreintes = [empreinte(encode(t)) for t in traces]
    issues = [r.issue() for r in runs]

    attendue = movie.fingerprint
    if attendue is None:
        print("the movie carried no fingerprint: the first try's is taken")
        print("as the reference.")
        attendue = empreintes[0]

    divergents = [i for i, e in enumerate(empreintes) if e != attendue]
    issues_differentes = len(set(issues)) > 1

    if not divergents and not issues_differentes:
        statut, image = issues[0]
        print(f"GO: {len(runs)} replay(s), a single fingerprint.")
        print(f"   {attendue}")
        print(f"   outcome: {statut}"
              + (f" at frame {image}" if image is not None else ""))
        if movie.outcome_status == "death":
            print("   the movie is declared deadly: the trajectory therefore")
            print("   carries the trap's mark, and reproducing it proves the")
            print("   trap was in the same state.")
        else:
            print("   movie with no declared death: if no trap touched the")
            print("   hero, the fingerprint says nothing about their state.")
        return 0

    print("DIVERGENCE.")
    for i, (e, issue) in enumerate(zip(empreintes, issues), 1):
        marque = "  <-- differs" if e != attendue else ""
        print(f"   try {i}: {e}{marque}   outcome {issue}")

    for i, trace in enumerate(traces[1:], 2):
        if empreintes[i - 1] != empreintes[0]:
            print(f"\n   try 1 versus {i}: "
                  f"{decrire_divergence(traces[0], trace)}")
    if issues_differentes:
        print("\n   The outcomes differ: if the fingerprints are nevertheless")
        print("   identical, it's the traps' phase that moved, not the")
        print("   hero's physics.")
    return 1


def main():
    movie = load_movie(CHEMIN, expected_version_code=version_attendue()[1])
    print(f"movie {CHEMIN}: {len(movie.inputs)} jump(s), "
          f"{movie.run_frames} frames, start expected at "
          f"({movie.start.hero_x}, {movie.start.hero_y})")

    if RELANCE_SEULE:
        # Le jeu meurt, donc la session Frida aussi : on ne s'attache pas ici.
        print("relaunching the game. Navigate again to the starting screen, "
              "then run this command again without --relance.")
        relancer()
        return 0

    session = Session()
    runs = []
    try:
        runs.append(un_essai(session, movie))
        print(decrire(runs[0]))
        print(f"   {empreinte(encode(runs[0].trace))}")
    except KeyboardInterrupt:
        print("\ninterrupted.")
    finally:
        session.detach()

    # La trace vaut mieux que son empreinte quand il faut chercher : une
    # empreinte repond "les octets different", une trace dit a quelle image et
    # de combien. Le film n'en porte pas, faute de place ; ce fichier-ci si.
    if TRACE and runs:
        with open(TRACE, "wb") as f:
            f.write(encode(runs[0].trace))
        print(f"   trace written to {TRACE} ({len(runs[0].trace)} frames)")

    if REFERENCE and runs:
        with open(REFERENCE, "rb") as f:
            reference = decode(f.read())
        print(f"\n   versus {REFERENCE} ({len(reference)} frames): "
              f"{decrire_divergence(reference, runs[0].trace)}")
        ecarts_max = ecart_maximal(reference, runs[0].trace)
        print(f"   maximum gap {ecarts_max[1]:.6f} px at frame "
              f"{ecarts_max[0]}")

    code = verdict(movie, runs)

    if ECRIRE and runs:
        statut, image = runs[0].issue()
        movie.fingerprint = empreinte(encode(runs[0].trace))
        movie.outcome_status = statut
        movie.outcome_frame = image
        save_movie(movie, CHEMIN)
        print(f"\nfingerprint and outcome written to {CHEMIN}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())
