"""Reconnaitre l'ecran de commencement.

Remplace le parcours de taps automatique, qui naviguait en aveugle sur des
attentes fixes. Les pubs ne viennent pas toujours au meme rythme : le
2026-09-18, un tap decale a fini par ouvrir une boite d'achat Google Play.
Un outil qui tape sans voir est un outil qui tape n'importe ou.

L'operateur navigue donc lui-meme, et confirme d'une touche. C'est le seul
signal fiable, et il ne coute rien : a l'ecran de commencement le niveau n'a
pas demarre, les pieges ne tournent pas et le heros ne bouge pas, donc
l'instant de la confirmation n'a aucune influence sur le run.

Ce que la position du heros NE dit PAS, mesure le 2026-09-18 : elle ne
distingue pas l'ecran de commencement du menu principal. Les deux rendent
(352, 548) sur le donjon de reference. Un premier releve avait donne
(160, 548) a l'ecran de commencement, mais c'etait une camera en pleine
transition : la coordonnee suit le cadrage, elle ne signe pas l'ecran. Une
attente fondee dessus s'est declenchee sur le menu et a deroule 244 images
sans un seul mouvement.

La position ne sert donc qu'a deux choses : verifier qu'il y a un heros et
un seul, et signaler un ecart. Elle ne refuse rien -- meme donjon, deux
seances du 2026-09-18 : (352, 548) puis (96, 548), parce que la camera ne
s'immobilise pas toujours au meme endroit. Le seul juge de "est-ce le meme
run" est l'empreinte, quelques secondes plus tard.
"""

from __future__ import annotations

# Ecart en pixels sous lequel on tient deux positions pour la meme. Les deux
# ecrans connus sont distants de 192 px : un demi-pixel separe sans ambiguite,
# tout en absorbant une eventuelle derive de la derniere decimale.
TOLERANCE_PX = 0.5


class DepartError(Exception):
    """L'ecran de commencement n'a pas ete atteint."""


def lire_position(api) -> tuple[float, float] | None:
    """Position du heros, ou None s'il n'y en a pas exactement un.

    Resout a chaque appel : entre deux relances, et meme entre deux ecrans,
    l'objet change d'adresse. Couteux (environ 0,7 s), donc a n'appeler qu'au
    rythme de la scrutation, jamais par image.
    """
    resolution = api.probe_resolve()
    if resolution["objets"] != 1:
        return None
    etat = api.probe_state()
    if etat is None:
        return None
    return (etat["x"], etat["y"])


def au_depart(position, x: float, y: float,
              tolerance: float = TOLERANCE_PX) -> bool:
    if position is None:
        return False
    return (abs(position[0] - x) <= tolerance
            and abs(position[1] - y) <= tolerance)


def confirmer_le_depart(
    api,
    attendu: tuple[float, float] | None = None,
    tolerance: float = TOLERANCE_PX,
    demander=input,
    dire=print,
) -> tuple[float, float]:
    """Attend que l'operateur declare etre a l'ecran de commencement.

    Rend la position du heros relevee a cet instant. Si `attendu` est donne --
    le film en porte une depuis son enregistrement -- une position differente
    arrete tout : le donjon a change de forme, et l'empreinte du film ne
    vaudrait plus pour lui.
    """
    dire("stop at the starting screen, then press Enter.")
    demander()

    position = lire_position(api)
    if position is None:
        raise DepartError(
            "exactly one hero is expected in memory. Are you on the screen "
            "right before the level starts?"
        )
    if attendu is not None and not au_depart(position, attendu[0], attendu[1],
                                             tolerance):
        # Avertissement et non refus : la position suit le cadrage de la
        # camera et non la forme du donjon. Meme donjon, deux seances du
        # 2026-09-18 : (352, 548) puis (96, 548). C'est l'empreinte du run qui
        # tranche, pas ce releve.
        dire(f"warning: hero at {position}, while the previous take gave "
             f"{attendu}. The position follows the camera; the fingerprint "
             f"will say whether the run is really the same.")
    return position
