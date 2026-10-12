"""La geometrie de la frise de l'atelier : images <-> pixels.

Pur : ni tkinter, ni jeu. La fenetre dessine ce que ce module calcule, et
c'est ici que se testent les conversions qui decident quel saut un clic
designe -- un clic mal attribue deplacerait le mauvais saut sans bruit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Vide laisse de chaque cote de la frise, pour que le saut de l'image 0 et le
# curseur de la derniere image restent cliquables.
MARGE_PX = 12

# Distance sous laquelle un clic designe un saut plutot que le vide : la
# largeur d'un trait epais, plus de quoi viser sans trembler.
TOLERANCE_CLIC_PX = 6


@dataclass(frozen=True)
class Echelle:
    largeur: int
    images: int
    marge: int = MARGE_PX

    def __post_init__(self) -> None:
        if self.images < 1:
            raise ValueError(
                f"a timeline covers at least one frame, got {self.images}")
        if self.largeur <= 2 * self.marge:
            raise ValueError(f"timeline too narrow: {self.largeur} px")

    @property
    def pas(self) -> float:
        return (self.largeur - 2 * self.marge) / self.images

    def x(self, image: float) -> float:
        return self.marge + image * self.pas

    def image(self, x: float) -> int:
        brute = round((x - self.marge) / self.pas)
        return max(0, min(self.images, brute))


def etendue(longueur: int, images_tracees: int, sauts) -> int:
    """Nombre d'images que la frise couvre : tout ce qui existe, au moins une.

    Un saut pose au-dela de la longueur du run doit rester visible, sinon on
    ne pourrait plus ni le voir ni le retirer.
    """
    return max(longueur, images_tracees, max(sauts, default=-1) + 1, 1)


def saut_proche(sauts, x: float, echelle: Echelle,
                tolerance: float = TOLERANCE_CLIC_PX) -> int | None:
    """Le saut le plus proche du clic, s'il est a moins de `tolerance` px."""
    meilleur = None
    for saut in sauts:
        distance = abs(echelle.x(saut) - x)
        if distance <= tolerance and (meilleur is None or distance < meilleur[0]):
            meilleur = (distance, saut)
    return None if meilleur is None else meilleur[1]


def courbe(ys, echelle: Echelle, hauteur: int,
           marge: int = MARGE_PX) -> list[tuple[float, float]]:
    """Points de la courbe de hauteur du heros, en pixels du canevas.

    L'axe y du jeu descend comme celui de l'ecran : un y plus petit est un
    heros plus haut, et il est dessine plus haut. Aucune inversion.
    """
    if not ys:
        return []
    bas, haut = min(ys), max(ys)
    utile = hauteur - 2 * marge
    points = []
    for image, y in enumerate(ys):
        if haut == bas:
            py = hauteur / 2
        else:
            py = marge + (y - bas) / (haut - bas) * utile
        points.append((echelle.x(image), py))
    return points


def graduations(images: int, cible: int = 8) -> list[int]:
    """Images a graduer : un pas de 1, 2 ou 5 fois une puissance de dix."""
    brut = max(1.0, images / cible)
    puissance = 10 ** math.floor(math.log10(brut))
    for facteur in (1, 2, 5, 10):
        pas = facteur * puissance
        if pas >= brut:
            break
    return list(range(0, images + 1, max(1, int(pas))))
