"""La liste des sauts d'un film, et le curseur qui designe celui qu'on travaille.

Pur : ni jeu, ni clavier, ni fichier. Decaler un saut, refuser une collision,
deplacer un curseur -- ce sont des operations sur une liste d'entiers, et c'est
la seule piece de l'editeur qui se teste entierement sans appareil.

Deux curseurs coexistent dans une seance, et ils ne designent pas la meme
chose : la tete de lecture avance dans le run vivant et ne sait pas reculer,
tandis que celui-ci se promene librement dans la liste. C'est parce que le
premier ne recule pas que le second existe -- editer "le saut sous la tete de
lecture" supposerait un rembobinage qu'on n'a pas.
"""

from __future__ import annotations

# Images de jeu montrees a vitesse normale avant le saut travaille. Une
# demi-seconde : assez pour le voir arriver, assez peu pour que les cinq cents
# images qui precedent passent en une seconde.
MARGE_TURBO_IMAGES = 30


class EditionError(Exception):
    """L'edition demandee rendrait le film invalide."""


class FilmEdite:
    """Les sauts d'un film en cours d'edition, et lequel on travaille."""

    def __init__(self, sauts=()) -> None:
        ordonnes = sorted(sauts)
        if len(set(ordonnes)) != len(ordonnes):
            raise EditionError(f"two jumps at the same frame: {ordonnes}")
        if ordonnes and ordonnes[0] < 0:
            raise EditionError(f"negative frame: {ordonnes[0]}")
        self.sauts = ordonnes
        self.index = 0 if ordonnes else None

    @property
    def choisi(self) -> int | None:
        """Image du saut travaille, ou None si le film est vide."""
        return None if self.index is None else self.sauts[self.index]

    def poser(self, image: int) -> int:
        """Ajoute un saut et le choisit."""
        if image < 0:
            raise EditionError(f"negative frame: {image}")
        if image in self.sauts:
            raise EditionError(f"a jump is already placed at frame {image}")
        self.sauts = sorted(self.sauts + [image])
        self.index = self.sauts.index(image)
        return image

    def retirer(self) -> int | None:
        """Retire le saut choisi et rend son image, ou None si le film est vide."""
        if self.index is None:
            return None
        retire = self.sauts.pop(self.index)
        self.index = None if not self.sauts else min(self.index,
                                                     len(self.sauts) - 1)
        return retire

    def choisir(self, image: int) -> int:
        """Choisit le saut pose a `image`.

        Sert apres un balayage : les deux sauts ont bouge, et le curseur doit
        se reposer sur celui qu'on travaillait -- designe par son image, qui
        le suit, et non par son rang, qui ne le suit pas.
        """
        if image not in self.sauts:
            raise EditionError(f"no jump at frame {image}")
        self.index = self.sauts.index(image)
        return image

    def decaler(self, pas: int) -> int:
        """Decale le saut choisi de `pas` images, et le garde choisi.

        Le curseur suit le saut deplace et non sa position dans la liste : un
        saut qui passe devant son voisin reste celui qu'on travaille.
        """
        if self.index is None:
            raise EditionError("no jump to shift: the movie is empty")
        depart = self.sauts[self.index]
        arrivee = depart + pas
        if arrivee < 0:
            raise EditionError(
                f"a jump can't land before frame 0 "
                f"(requested: {arrivee})"
            )
        if arrivee != depart and arrivee in self.sauts:
            raise EditionError(
                f"a jump is already placed at frame {arrivee}: the two "
                f"would overlap"
            )
        autres = [s for rang, s in enumerate(self.sauts) if rang != self.index]
        self.sauts = sorted(autres + [arrivee])
        self.index = self.sauts.index(arrivee)
        return arrivee

    def precedent(self) -> int | None:
        if self.index is not None and self.index > 0:
            self.index -= 1
        return self.choisi

    def suivant(self) -> int | None:
        if self.index is not None and self.index < len(self.sauts) - 1:
            self.index += 1
        return self.choisi

    def frontiere_turbo(self, marge: int = MARGE_TURBO_IMAGES) -> int | None:
        """Image ou le turbo doit se couper a l'essai suivant.

        None quand il n'y a rien a gagner : film vide, ou saut travaille trop
        proche du debut pour qu'une avance rapide ait un sens -- il serait
        passe avant qu'on ait le temps de le voir.
        """
        choisi = self.choisi
        if choisi is None or choisi <= marge:
            return None
        return choisi - marge
