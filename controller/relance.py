"""Relance complete du jeu : la seule condition de depart bit-exacte.

NOTES.md, jalon 5, section 2 : la derive de la position de depart s'accumule
par entree de donjon a l'interieur d'une session, et un relancement la remet
a sa valeur d'origine -- 786.5623779296875, trois essais sur trois. Un film ne
se rejoue donc pas en ressortant du donjon pour y rentrer, mais en relancant
le jeu.

`am force-stop` detruit le processus : la session Frida meurt avec lui.
L'appelant detache avant et rattache apres (voir Session.attacher_avec_reessais).

Ce module ne navigue pas. Un parcours de taps automatique a existe ici, et il
a ete retire le 2026-09-18 : il tapait en aveugle sur des attentes fixes, les
pubs ne viennent pas toujours au meme rythme, et un tap decale a fini par
ouvrir une boite d'achat Google Play. C'est l'operateur qui navigue, et
controller/depart.py qui reconnait l'arrivee.
"""

from __future__ import annotations

import time

from controller.device import PACKAGE, run_adb

CATEGORIE_LANCEUR = "android.intent.category.LAUNCHER"

# Le jeu met quelques secondes a afficher quelque chose. Cette attente ne sert
# qu'a eviter des tentatives d'attache vouees a l'echec : la vraie garantie
# est le reessai de Session.attacher_avec_reessais.
ATTENTE_DEMARRAGE = 5.0


def force_stop(package: str = PACKAGE, adb=run_adb) -> None:
    adb("shell", "am", "force-stop", package)


def demarrer(package: str = PACKAGE, adb=run_adb) -> None:
    # monkey plutot que `am start -n <paquet>/<activite>` : il trouve
    # l'activite de lancement tout seul, donc aucun nom d'activite a
    # maintenir a travers les mises a jour du jeu.
    adb("shell", "monkey", "-p", package, "-c", CATEGORIE_LANCEUR, "1")


def relancer(
    package: str = PACKAGE,
    adb=run_adb,
    dormir=time.sleep,
    attente: float = ATTENTE_DEMARRAGE,
) -> None:
    """Arrete le jeu et le redemarre. Ne navigue pas, ne tape nulle part."""
    force_stop(package, adb)
    demarrer(package, adb)
    dormir(attente)
