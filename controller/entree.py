"""Emettre un toucher.

C'est le seul chemin qui fonctionne. Le jeu delivre ses touchers sur le
thread GL : un appel JNI depuis le fil de Frida faute, et le meme appel depuis
le hook de frame est avale. Voir NOTES.md, "Injection : le bon chemin est
adb input tap, pas JNI".

Emis barriere fermee, le toucher est mis en file par Android et traite a
l'image qu'on relache. Mesure du 2026-09-17 : meme image et meme position a
la quatrieme decimale pour des attentes de 0 a 2 s entre le tap et la reprise.
"""

from __future__ import annotations

import time

from controller.device import run_adb

# Centre de l'ecran. Un tap n'importe ou fait sauter le heros.
X_CENTRE, Y_CENTRE = 800, 450

# Le toucher est traite a l'image relachee quelle que soit cette attente ; on
# en garde une petite et fixe pour laisser a Android le temps de le mettre en
# file avant qu'on relache.
ATTENTE_TAP = 0.15


def taper(
    x: int = X_CENTRE,
    y: int = Y_CENTRE,
    attente: float = ATTENTE_TAP,
    adb=run_adb,
    dormir=time.sleep,
) -> None:
    adb("shell", "input", "tap", str(x), str(y))
    if attente:
        dormir(attente)
