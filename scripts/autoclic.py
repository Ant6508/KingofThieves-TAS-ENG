# -*- coding: utf-8 -*-
"""autoclic.py - taper a intervalle regulier sur un point fixe.

Outil autonome : pas de barriere de frame, pas de Frida, pas de sonde. Il
emet un toucher sur un point donne, a cadence donnee, jusqu'a une limite
donnee. L'operateur choisit lui-meme quand le lancer et sur quel ecran.

Les coordonnees sont celles de l'ecran Android (1600 x 900), pas celles de la
fenetre MEmu : voir NOTES.md, "Fenetre MEmu et ecran Android : 33 pixels
d'ecart".

Usage :
    python scripts/autoclic.py 800 450 --intervalle 1.0 --taps 60
    python scripts/autoclic.py 1250 220 --intervalle 0.5 --duree 120
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass

# Lance depuis scripts/, la racine du depot n'est pas dans sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller.device import DeviceError  # noqa: E402
from controller.entree import taper as taper_adb  # noqa: E402

# Barre d'onglets de MEmu : l'ecran Android commence 33 px sous le haut de la
# fenetre. Voir NOTES.md, "Fenetre MEmu et ecran Android : 33 pixels d'ecart".
DECALAGE_FENETRE = 33


@dataclass(frozen=True)
class CompteRendu:
    """Ce que la boucle rapporte, qu'elle ait fini ou ete arretee.

    `erreur` vaut None, une DeviceError, ou une KeyboardInterrupt.
    """

    emis: int
    duree_reelle: float
    sautes: int
    erreur: object = None


class ArgumentsInvalides(Exception):
    """La ligne de commande ne decrit pas un travail qui s'arrete."""


class _Analyseur(argparse.ArgumentParser):
    """argparse qui leve au lieu de quitter, pour que main reste maitre."""

    def error(self, message):
        raise ArgumentsInvalides(message)


@dataclass(frozen=True)
class Config:
    x: int
    y: int
    intervalle: float
    taps: int | None
    duree: float | None


def analyser_arguments(argv):
    """Rend la Config, ou leve ArgumentsInvalides. Aucun effet de bord."""
    analyseur = _Analyseur(
        prog="autoclic.py",
        description="Tap a fixed point at a regular interval.",
    )
    analyseur.add_argument("x", type=int, help="x, Android screen")
    analyseur.add_argument("y", type=int, help="y, Android screen")
    analyseur.add_argument(
        "--intervalle", type=float, default=1.0, help="seconds between two taps"
    )
    analyseur.add_argument("--taps", type=int, default=None, help="number of taps")
    analyseur.add_argument("--duree", type=float, default=None, help="seconds")
    args = analyseur.parse_args(argv)

    if args.taps is None and args.duree is None:
        raise ArgumentsInvalides(
            "at least --taps or --duree is required: an autoclicker with no "
            "limit never stops on its own"
        )
    if args.intervalle <= 0:
        raise ArgumentsInvalides("--intervalle must be strictly positive")

    return Config(args.x, args.y, args.intervalle, args.taps, args.duree)


def boucle(
    x,
    y,
    intervalle,
    taps=None,
    duree=None,
    taper=taper_adb,
    dormir=time.sleep,
    horloge=time.monotonic,
):
    """Emet des touchers a echeances absolues t0 + n x intervalle.

    Absolues, et non "dormir l'intervalle apres chaque tap" : un adb input tap
    coute 80 a 200 ms, qui s'ajouteraient a chaque tour et feraient deriver la
    cadence de plusieurs secondes par minute.

    L'attente de 0,15 s integree par defaut a entree.taper sert a laisser
    Android mettre le toucher en file avant qu'on relache la barriere de
    frame. Il n'y a pas de barriere ici : on la met a zero, sinon elle
    fausserait la cadence.
    """
    t0 = horloge()
    emis = 0
    n = 0
    dernier = -1  # numero du creneau du dernier toucher parti
    erreur = None

    try:
        while True:
            if taps is not None and emis >= taps:
                break
            if duree is not None and n * intervalle > duree:
                break
            attente = (t0 + n * intervalle) - horloge()
            if attente > 0:
                dormir(attente)
            taper(x, y, attente=0.0)
            emis += 1
            dernier = n

            # Le prochain creneau est le premier strictement dans le futur. Les
            # creneaux deja passes sont sautes, jamais rattrapes d'affilee.
            apres = horloge()
            prochain = n + 1
            while t0 + prochain * intervalle <= apres:
                prochain += 1
            n = prochain
    except (DeviceError, KeyboardInterrupt) as exc:
        # On ne poursuit pas une serie de touchers quand l'appareil ne repond
        # plus, et un Ctrl+C doit quand meme rendre son bilan.
        erreur = exc

    # Les creneaux sautes se comptent sur la fenetre reellement parcourue, du
    # premier au dernier toucher. Compter au-dela du dernier gonflerait le
    # diagnostic d'un creneau que la boucle n'aurait de toute facon pas servi.
    sautes = dernier + 1 - emis

    return CompteRendu(emis, horloge() - t0, sautes, erreur)


def annonce(config):
    """Ce qu'on affiche avant de commencer, pour que l'operateur recoupe.

    La ligne de la fenetre n'est qu'un rappel : le script ne convertit jamais
    les coordonnees qu'on lui donne, il les passe telles quelles a adb.
    """
    limites = []
    if config.taps is not None:
        limites.append(f"{config.taps} taps")
    if config.duree is not None:
        limites.append(f"{config.duree} s")

    return "\n".join(
        [
            f"point: ({config.x}, {config.y}) Android screen"
            f"  =  y {config.y + DECALAGE_FENETRE} in the MEmu window",
            f"rate:  one tap every {config.intervalle} s",
            "stop:  " + " or ".join(limites) + ", or Ctrl+C",
        ]
    )


def bilan(rendu):
    lignes = [f"{rendu.emis} taps sent in {rendu.duree_reelle:.1f} s"]
    if rendu.sautes:
        lignes.append(f"{rendu.sautes} slots skipped: adb couldn't keep up with the rate")
    if isinstance(rendu.erreur, KeyboardInterrupt):
        lignes.append("interrupted from the keyboard")
    elif rendu.erreur is not None:
        lignes.append(f"stopped by adb: {rendu.erreur}")
    return "\n".join(lignes)


def main(argv=None):
    try:
        config = analyser_arguments(sys.argv[1:] if argv is None else argv)
    except ArgumentsInvalides as exc:
        print(f"arguments: {exc}", file=sys.stderr)
        return 2

    print(annonce(config))
    rendu = boucle(
        config.x,
        config.y,
        config.intervalle,
        taps=config.taps,
        duree=config.duree,
    )
    print(bilan(rendu))
    return 1 if isinstance(rendu.erreur, DeviceError) else 0


if __name__ == "__main__":
    sys.exit(main())
