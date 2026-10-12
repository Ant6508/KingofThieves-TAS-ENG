"""Le balayage : quels essais faire, dans quel ordre, et ce qu'ils ont donne.

Pur : ni jeu, ni clavier, ni fichier, comme film_edite.py. La seule chose que
la seance fournit est `essayer`, qui prend une liste de sauts et rend une
trace -- voir `balayer`.

Deux decalages et non un, et ils ne jouent pas le meme role :

- celui du saut TRAVAILLE change la phase des pieges au moment ou le heros
  decolle, puisque les pieges tournent sur des images absolues depuis le
  demarrage du niveau ;
- celui du saut PRECEDENT ne touche pas a cette phase. Il ne change que
  l'etat du heros a l'instant du decollage -- et il ne sert donc que si la
  contraction de 0,8 par image (NOTES.md, jalon 5, section 6) ne l'a pas deja
  efface. C'est ce que mesure scripts/mesure_ab.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from controller.cible import Cible, atteinte, progression
from controller.film_edite import EditionError, FilmEdite

# Rayons du balayage, en images. 3 et 3 font 49 essais, soit environ une
# minute en turbo plein. RAYON_PRECEDENT tombe a 0 si la mesure du modele A/B
# montre que decaler le saut precedent ne change rien a l'etat de decollage.
RAYON_PRECEDENT = 3
RAYON_TRAVAILLE = 3


class SolveurError(Exception):
    """Le balayage demande n'a pas de sens."""


@dataclass(frozen=True, order=True)
class Couple:
    """Deux decalages, en images : le saut precedent et le saut travaille."""

    precedent: int
    travaille: int

    @property
    def distance(self) -> int:
        return abs(self.precedent) + abs(self.travaille)


@dataclass
class Resultat:
    """Ce qu'un couple a donne, ou le fait qu'il ne donnera rien.

    Un couple impossible garde `progression=None` et `reussi=False` : c'est ce
    `None` qui le tient hors du podium sans qu'aucun filtre n'ait a connaitre
    la notion d'impossible.
    """

    couple: Couple
    progression: float | None = None
    reussi: bool = False
    impossible: bool = False


def espace(rayon_p: int = RAYON_PRECEDENT,
           rayon_t: int = RAYON_TRAVAILLE) -> list[Couple]:
    """Tous les couples, du centre vers l'exterieur.

    L'ordre n'est pas cosmetique : si le couple qui passe est a une image, on
    le sait au troisieme essai et non au quarante-septieme, et l'operateur peut
    interrompre sans avoir tout paye.

    A distance egale, le decalage du saut TRAVAILLE passe en premier. Les deux
    dimensions ne se valent pas : celle du saut travaille change la phase des
    pieges au decollage -- effet direct -- tandis que celle du saut precedent
    ne change que l'etat du heros, et la contraction de 0,8 par image peut
    l'avoir deja efface. C'est meme la question que scripts/mesure_ab.py doit
    trancher, et RAYON_PRECEDENT tombera a 0 si la reponse est le modele A.
    Explorer d'abord la dimension dont on doute serait payer les essais dans
    le mauvais ordre, et la promesse du paragraphe precedent ne tiendrait plus
    que par accident.
    """
    couples = [
        Couple(p, t)
        for p in range(-rayon_p, rayon_p + 1)
        for t in range(-rayon_t, rayon_t + 1)
    ]
    return sorted(couples, key=lambda c: (c.distance, abs(c.precedent), c))


class Balayage:
    """L'etat d'une recherche : ce qui est fait, ce qui reste, ce qu'on a vu.

    C'est cet objet que la seance garde entre deux appuis sur la touche :
    un balayage arrete par un ancrage douteux reprend ou il en etait.
    """

    def __init__(self, sauts, index: int, images: int, couples=None) -> None:
        ordonnes = sorted(sauts)
        if not ordonnes:
            raise SolveurError("no jump to sweep: the movie is empty")
        if not 0 <= index < len(ordonnes):
            raise SolveurError(
                f"no jump at rank {index}: the movie has "
                f"{len(ordonnes)}"
            )
        self.sauts = ordonnes
        self.index = index
        self.images = images
        self.couples = list(espace()) if couples is None else list(couples)
        self.resultats: dict[Couple, Resultat] = {}
        for couple in self.couples:
            if self._sauts_de(couple) is None:
                self.resultats[couple] = Resultat(couple, impossible=True)

    # ----- ce que vaut un couple -----

    def image_travaillee(self, couple: Couple) -> int:
        """Image du saut travaille apres application du couple.

        Se calcule et ne se cherche pas dans la liste d'arrivee : un saut qui
        passe devant son voisin change de rang sans cesser d'etre celui qu'on
        travaille.

        Refuse un couple impossible plutot que de rendre une image qui ne
        correspondrait a aucun essai reel -- meme garde-fou que sauts_de, pour
        la meme raison : un appelant qui lirait cette image avant de verifier
        `impossible` la prendrait pour la phase d'un essai qui n'aura jamais
        lieu.
        """
        if self._sauts_de(couple) is None:
            raise SolveurError(
                f"impossible pair: {couple} would merge two jumps "
                f"or drop one before frame 0"
            )
        return self.sauts[self.index] + couple.travaille

    def sauts_de(self, couple: Couple) -> list[int]:
        arrivee = self._sauts_de(couple)
        if arrivee is None:
            raise SolveurError(
                f"impossible pair: {couple} would merge two jumps "
                f"or drop one before frame 0"
            )
        return arrivee

    def _sauts_de(self, couple: Couple) -> list[int] | None:
        """La liste d'arrivee, ou None si elle serait invalide.

        Les deux decalages s'appliquent EN UNE FOIS, et c'est un piege reel :
        les appliquer l'un apres l'autre declarerait impossibles des couples
        qui ne le sont pas. Sauts a 100 et 102, couple (+2, +2) -- deplacer
        d'abord le precedent le fait entrer en collision avec un saut qui va
        lui aussi bouger, alors que {102, 104} est parfaitement valide.

        La validation est celle de FilmEdite, qui refuse deja les doublons et
        les images negatives. La reutiliser plutot que la reecrire, c'est aussi
        ce qui evite le piege.

        Reste une borne que FilmEdite ne connait pas : la fin du run. derouler
        ignore SILENCIEUSEMENT un tap au-dela de la derniere image
        (controller/run.py : `taps = [n for n in sorted(entrees)
        if n < images]`).
        L'essai se deroulerait donc sans ce saut, et sa progression serait
        mesuree comme celle d'un essai normal -- un couple ampute passerait
        pour un couple essaye, et pourrait meme gagner le podium. On refuse
        ici ce que derouler avalerait sans rien dire.

        LIMITE ASSUMEE : rien n'empeche le saut precedent de DOUBLER le saut
        travaille. Sauts a 98 et 100, couple (+3, 0) : le precedent tombe a
        101, donc apres celui qu'on travaille. L'essai reste parfaitement
        valide et sa mesure honnete -- deux taps a deux images distinctes --
        mais il ne raconte plus l'histoire "precedent puis travaille" du
        paragraphe de tete. On ne le refuse pas : ce serait ecarter un essai
        jouable pour une raison de vocabulaire. A garder en tete si un couple
        gagnant se revele etre de ceux-la.
        """
        if self.index == 0 and couple.precedent != 0:
            return None
        arrivee = list(self.sauts)
        arrivee[self.index] += couple.travaille
        if self.index > 0:
            arrivee[self.index - 1] += couple.precedent
        if any(n >= self.images for n in arrivee):
            return None
        try:
            FilmEdite(arrivee)
        except EditionError:
            return None
        return sorted(arrivee)

    # ----- l avancement -----

    def prochain(self) -> Couple | None:
        for couple in self.couples:
            if couple not in self.resultats:
                return couple
        return None

    def restants(self) -> list[Couple]:
        return [c for c in self.couples if c not in self.resultats]

    def noter(self, couple: Couple, progression: float, reussi: bool) -> None:
        """Enregistre ce qu'un essai a donne.

        Refuse un couple etranger a l'espace de recherche : il compterait dans
        `faits` sans compter dans `total`, et pourrait gagner le podium sans
        etre jamais passe par la validation de `_sauts_de` -- donc en
        contournant les deux garde-fous qui empechent un essai ampute de
        concourir.

        Refuse aussi un couple deja note : l'ecraser en silence ferait
        disparaitre un essai qu'on a pourtant paye.
        """
        if couple not in self.couples:
            raise SolveurError(
                f"pair outside the search space: {couple}"
            )
        connu = self.resultats.get(couple)
        if connu is not None:
            if connu.impossible:
                raise SolveurError(f"impossible pair: {couple}")
            raise SolveurError(f"pair already recorded: {couple}")
        self.resultats[couple] = Resultat(couple, progression, reussi)

    @property
    def total(self) -> int:
        """Nombre de couples qui coutent un essai."""
        return len(self.couples) - sum(
            1 for r in self.resultats.values() if r.impossible
        )

    @property
    def faits(self) -> int:
        return sum(1 for r in self.resultats.values() if not r.impossible)

    @property
    def reussis(self) -> list[Resultat]:
        return [r for r in self.resultats.values() if r.reussi]

    # ----- le classement -----

    def podium(self, combien: int = 5) -> list[Resultat]:
        """Les meilleurs essais, du plus avance au moins avance.

        Trier sur la seule progression suffit : un essai reussi est par
        definition un essai dont la progression depasse le seuil, donc aucun
        essai rate ne peut le devancer. A progression egale, le plus petit
        deplacement gagne -- on ne bouge pas deux sauts de trois images quand
        un demi-pixel etait deja la.

        Cette garantie tient tant que l'appelant fait ce que son nom promet :
        passer a `noter` un `reussi` qui reflete vraiment `progression >=
        seuil` pour la meme cible (voir controller/cible.py, `atteinte`).
        Balayage ne connait pas la cible et ne peut pas le verifier lui-meme
        -- ce n'est pas son role, mais celui de la boucle qui appelle
        `noter`.
        """
        mesures = [r for r in self.resultats.values()
                   if r.progression is not None]
        mesures.sort(key=lambda r: (-r.progression, r.couple.distance,
                                    r.couple))
        return mesures[:combien]

    def meilleur(self) -> Resultat | None:
        classement = self.podium(1)
        return classement[0] if classement else None


def balayer(balayage: Balayage, essayer, cible: Cible,
            dire=lambda balayage, resultat: None,
            interrompu=lambda: False) -> str:
    """Mene le balayage jusqu'au bout, ou jusqu'a ce qu'on l'arrete.

    `essayer` prend une liste de sauts et rend une trace. C'est la seule
    chose que la seance fournit, et c'est ce qui permet de tester toute la
    boucle sans appareil.

    Toute exception levee par `essayer` -- AncrageError en particulier --
    TRAVERSE. Le balayage s'arrete net et l'appelant garde `balayage`, qui
    porte tout ce qui est deja mesure et repart du couple suivant. Rattraper
    l'erreur pour continuer a taper alors qu'on ne sait plus ou est le jeu
    est exactement ce qui a ouvert une boite d'achat Google Play le
    2026-09-18.

    `progression` (importee de controller.cible) leve aussi CibleError
    quand la fenetre regardee ne contient aucune image ou le heros bouge --
    ancrage rate, ou tap jamais recu. Cette exception traverse de la meme
    facon : `noter` n'est appele qu'apres, donc le couple fautif ne finit
    jamais note et reste dans `restants()` pour la reprise.

    `interrompu` est interroge apres `prochain` et avant `essayer` : aucun
    appui n'est donc emis pour le couple qui declenche l'arret, et ce couple
    reste lui aussi a essayer a la reprise.

    LIMITE CONNUE de la reprise : le couple fautif revient en tete des
    restants, donc une reprise le retente en premier. C'est ce qu'on veut
    quand la cause lui est etrangere -- une navigation ratee, que l'operateur
    corrige avant de relancer. Mais si un couple echoue pour une raison qui
    lui est propre, rien ici ne distingue les deux cas et rien ne compte ses
    echecs : la touche de reprise peut buter indefiniment sur lui. La boucle
    n'a pas l'information qu'il faudrait pour trancher ; si le cas se
    presente, c'est a la seance de compter les echecs consecutifs d'un meme
    couple, puisqu'elle seule voit l'operateur insister.

    Rend "termine" ou "interrompu".
    """
    while True:
        couple = balayage.prochain()
        if couple is None:
            return "termine"
        if interrompu():
            return "interrompu"
        trace = essayer(balayage.sauts_de(couple))
        balayage.noter(couple, progression(trace, cible),
                       atteinte(trace, cible))
        dire(balayage, balayage.resultats[couple])
