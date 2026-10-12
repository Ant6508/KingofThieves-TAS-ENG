"""Ce qu'un essai doit atteindre, et jusqu'ou il est alle.

Pur : ni jeu, ni clavier, ni fichier. Prend une trace, rend un nombre ou un
verdict, donc se teste entierement sans appareil.

L'oracle du brute force ne sait pas ce qu'est une mort, et n'a pas a le
savoir. Les deux pistes evidentes sont mesurees mortes : un heros tue reste
parfaitement lisible en memoire (NOTES.md, 2026-09-18) et son immobilite ne
distingue pas une mort d'un repos. Ce qu'on demande ici est autre chose :
jusqu'ou le heros est alle. Une mort remet le niveau en place et ramene le
heros a son depart, ce qui ne peut pas entamer un maximum deja atteint --
donc la mesure survit a la mort sans avoir a la reconnaitre.
"""

from __future__ import annotations

from dataclasses import dataclass

from controller.trace import IMAGES_MOBILES_MINIMUM, Etat, images_mobiles

# Pas du reglage de la cible au clavier, en pixels. Assez gros pour deplacer
# une cible en quelques frappes, assez fin pour viser derriere un obstacle.
PAS_DE_CIBLE_PX = 10.0


class CibleError(Exception):
    """La cible ne peut pas etre construite, ou la trace ne se lit pas."""


@dataclass(frozen=True)
class Cible:
    """Un point a depasser sur l'axe de progression, avant une image donnee."""

    axe: str            # "x" ou "y"
    sens: int           # +1 ou -1, le sens dans lequel le heros progresse
    seuil: float
    image_limite: int

    def __post_init__(self) -> None:
        if self.axe not in ("x", "y"):
            raise CibleError(f"unknown axis: {self.axe!r}, expected 'x' or 'y'")
        if self.sens not in (1, -1):
            raise CibleError(f"unknown direction: {self.sens!r}, expected +1 or -1")
        if self.image_limite < 0:
            raise CibleError(
                f"negative frame limit: {self.image_limite}. Python "
                f"would cut the trace from the end instead of refusing, and "
                f"the progress would cover a window nobody chose."
            )

    def valeur(self, etat: Etat) -> float:
        return etat.x if self.axe == "x" else etat.y

    def deplacee(self, pas: float) -> Cible:
        """La meme cible, son seuil pousse de `pas` px DANS LE SENS de la
        marche. Un pas positif la rend plus dure a atteindre."""
        return Cible(self.axe, self.sens, self.seuil + self.sens * pas,
                     self.image_limite)


def progression(trace: list[Etat], cible: Cible, minimum: int = 1) -> float:
    """Le point le plus avance que le heros ait touche, compte en positif.

    `sens * valeur` fait que "plus grand" veut toujours dire "plus avance",
    quel que soit le sens de la marche : comparer deux essais redevient
    comparer deux nombres, et le podium se trie sans cas particulier.

    Refuse une fenetre ou le heros n'a pas bouge d'un pixel. Un tel essai n'a
    pas eu lieu -- ancrage rate, ou tap jamais recu -- et le noter comme un
    essai ordinaire le ferait concourir au podium avec sa position de depart
    pour score.

    Le seuil est UNE image mobile et non IMAGES_MOBILES_MINIMUM, qui en vaut
    trente : un run court mais legitime peut bouger moins d'une demi-seconde,
    et avorter un balayage entier sur un vrai essai couterait plus cher que le
    defaut qu'on repare. Ici on ne rejette que l'indiscutable.

    LIMITE CONNUE, et elle n'est pas refermable ici : un essai qui bouge deux
    images puis se fige passe ce garde-fou, et rien dans sa trace ne le
    distingue d'un vrai coup bref suivi d'un blocage. Aucun seuil ne les
    separe, parce que l'information n'est pas dans la trace -- le test
    test_un_essai_qui_bouge_a_peine_reste_mesure tient d'ailleurs un mouvement
    d'un seul pixel pour legitime, et il a raison de le faire. Si le cas
    devient genant, il se detectera au niveau du balayage, par plusieurs essais
    dont la progression colle anormalement au depart, et non essai par essai.
    """
    regardees = trace[:cible.image_limite]
    if not regardees:
        raise CibleError(
            f"no frame to look at: the trace has {len(trace)} and the "
            f"target stops at frame {cible.image_limite}"
        )
    if images_mobiles(regardees) < minimum:
        raise CibleError(
            f"the hero didn't move in any of the {len(regardees)} frames "
            f"looked at: this try didn't happen. Missed anchor, or tap "
            f"never received."
        )
    return max(cible.sens * cible.valeur(e) for e in regardees)


def atteinte(trace: list[Etat], cible: Cible) -> bool:
    """Le verdict binaire que le jalon 8 reclame."""
    return progression(trace, cible) >= cible.sens * cible.seuil


def proposer_cible(trace: list[Etat],
                    minimum: int = IMAGES_MOBILES_MINIMUM) -> Cible:
    """Deduit une cible de l'essai que l'operateur vient de regarder.

    L'axe est celui dont le heros a parcouru la plus grande amplitude, le sens
    celui de l'extremum atteint le plus tard, le seuil cet extremum, et
    l'image limite la longueur de la trace.

    La proposition dit donc "la ou ton dernier essai s'est arrete". L'operateur
    n'a jamais a connaitre les coordonnees du niveau : il la pousse plus loin,
    ce qui revient a dire "plus loin que la ou je meurs".

    Une trace immobile ne porte aucun axe dominant. On refuse plutot que d'en
    designer un au hasard : l'operateur lancerait quarante-neuf essais contre
    une cible qui ne veut rien dire.
    """
    mobiles = images_mobiles(trace)
    if mobiles < minimum:
        raise CibleError(
            f"the try doesn't move enough to pick an axis: {mobiles} "
            f"moving frames, {minimum} needed. Make a try where the hero "
            f"moves forward before starting a sweep."
        )

    amplitudes = {
        "x": max(e.x for e in trace) - min(e.x for e in trace),
        "y": max(e.y for e in trace) - min(e.y for e in trace),
    }
    axe = "x" if amplitudes["x"] >= amplitudes["y"] else "y"
    valeurs = [e.x if axe == "x" else e.y for e in trace]

    # Le sens est celui de l'extremum atteint LE PLUS TARD, et non celui de la
    # plus grande excursion depuis le depart. La difference n'est pas
    # theorique : un heros qui prend un peu d'elan d'un cote avant de partir de
    # l'autre, sur un essai qui meurt tot, a une excursion d'elan plus grande
    # que sa progression reelle. La cible partait alors a l'envers, et l'essai
    # qui avait le moins avance gagnait le podium.
    #
    # Le cas nominal n'est pas epargne par ce piege, il est dedans : on propose
    # une cible a partir de l'essai que l'operateur vient de rater, donc d'un
    # essai dont la progression est courte par construction.
    #
    # `index` rend la PREMIERE occurrence, ce qui traite au passage l'essai
    # mortel : le niveau se remet en place et le heros revient a son depart,
    # mais ce depart avait deja ete touche a l'image 0.
    plus_haut = valeurs.index(max(valeurs))
    plus_bas = valeurs.index(min(valeurs))
    sens = 1 if plus_haut > plus_bas else -1
    seuil = max(valeurs) if sens == 1 else min(valeurs)
    return Cible(axe=axe, sens=sens, seuil=seuil, image_limite=len(trace))
