"""Decodage, empreinte et comparaison des traces d'un run.

Module pur : il ne connait ni Frida ni la memoire du jeu. Il prend des octets
et rend des valeurs, donc il se teste sans appareil.

L'agent ecrit un enregistrement de 20 octets par image :
    uint32 numero de frame, puis quatre float : x, y, vx, vy
en petit-boutiste, l'ordre natif de la cible x86_64.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

TAILLE_ENREGISTREMENT = 20
FORMAT = "<Iffff"

# En dessous de ce nombre d'images ou le heros bouge, la trace ne prouve rien :
# comparer cinq traces immobiles donne cinq empreintes identiques sans que le
# jeu ait rien fait. Une demi-seconde de mouvement est le minimum defendable.
IMAGES_MOBILES_MINIMUM = 30


class TraceError(Exception):
    """La trace est malformee."""


@dataclass(frozen=True)
class Etat:
    frame: int
    x: float
    y: float
    vx: float
    vy: float


def decode(octets: bytes) -> list[Etat]:
    if len(octets) % TAILLE_ENREGISTREMENT != 0:
        raise TraceError(
            f"{len(octets)} bytes don't divide into records of "
            f"{TAILLE_ENREGISTREMENT} bytes"
        )
    return [
        Etat(*struct.unpack_from(FORMAT, octets, position))
        for position in range(0, len(octets), TAILLE_ENREGISTREMENT)
    ]


def encode(etats: list[Etat]) -> bytes:
    return b"".join(
        struct.pack(FORMAT, e.frame, e.x, e.y, e.vx, e.vy) for e in etats
    )


def empreinte(octets: bytes) -> str:
    """SHA-256 du flux brut, sans conversion en texte (spec section 7)."""
    return "sha256:" + hashlib.sha256(octets).hexdigest()


def premiere_divergence(a: list[Etat], b: list[Etat]) -> int | None:
    """Indice du premier enregistrement qui differe, ou None."""
    for indice, (ea, eb) in enumerate(zip(a, b)):
        if ea != eb:
            return indice
    if len(a) != len(b):
        return min(len(a), len(b))
    return None


def decrire_divergence(a: list[Etat], b: list[Etat]) -> str:
    indice = premiere_divergence(a, b)
    if indice is None:
        return "no divergence"
    if indice >= len(a) or indice >= len(b):
        return (
            f"different lengths: {len(a)} and {len(b)} records, "
            f"identical up to index {indice - 1}"
        )
    ea, eb = a[indice], b[indice]
    return (
        f"first divergence at frame {ea.frame}: "
        f"x={ea.x!r} y={ea.y!r} vx={ea.vx!r} vy={ea.vy!r} "
        f"versus x={eb.x!r} y={eb.y!r} vx={eb.vx!r} vy={eb.vy!r}"
    )


def images_mobiles(etats: list[Etat]) -> int:
    """Nombre d'images ou le heros bouge.

    La comparaison a 0.0 est exacte, et c'est mesure, pas suppose : sur
    120 images du heros au repos, aucune n'a montre de vitesse non nulle et
    la position n'a pris qu'une seule valeur. Le moteur ne laisse pas de
    gigue residuelle, donc un epsilon serait du bruit ajoute. Voir NOTES.md,
    "Vitesse au repos : exactement nulle".
    """
    return sum(1 for e in etats if e.vx != 0.0 or e.vy != 0.0)


def est_significative(
    etats: list[Etat], minimum: int = IMAGES_MOBILES_MINIMUM
) -> bool:
    """La trace contient-elle assez de mouvement pour qu'un test veuille dire
    quelque chose ? Un heros immobile rend cinq empreintes identiques et un
    faux vert."""
    return images_mobiles(etats) >= minimum


# Ecart en pixels sous lequel deux traces sont tenues pour concordantes.
# Mesure du 2026-09-17 : le heros derive d'environ 1e-4 px d'un essai a
# l'autre sans jamais revenir a un etat identique, et un ecart de 1,2e-4 px
# apparu en cours de course s'est resorbe en deux images. Un centieme de
# pixel est donc cent fois plus large que le bruit observe, et cent fois plus
# fin que ce qui pourrait changer une collision.
TOLERANCE_PX = 0.01


def ecarts(a: list[Etat], b: list[Etat]) -> list[float]:
    """Ecart absolu, image par image, sur la plus grande des deux coordonnees.

    On ne compare pas les vitesses : elles derivent des positions, donc les
    compter deux fois donnerait a un meme ecart un poids double.
    """
    return [max(abs(ea.x - eb.x), abs(ea.y - eb.y)) for ea, eb in zip(a, b)]


def ecart_maximal(a: list[Etat], b: list[Etat]) -> tuple[int | None, float]:
    """Indice et valeur de l'image ou les deux traces s'ecartent le plus."""
    mesures = ecarts(a, b)
    if not mesures:
        return None, 0.0
    indice = max(range(len(mesures)), key=lambda k: mesures[k])
    return indice, mesures[indice]


def ecart_translate(a: list[Etat], b: list[Etat], decalage: int,
                    depuis: int = 0) -> float | None:
    """Ecart maximal entre `a` et `b`, `b` etant recalee de `decalage` images.

    Compare a[k] a b[k + decalage], pour k >= depuis.

    Sert a distinguer deux trajectoires qui different vraiment de deux fois la
    meme jouee plus tard. Un saut decale d'une image produit, sous le modele A
    de la spec du brute force, une trace identique a une translation pres :
    `ecart_maximal` la declare divergente partout, `ecart_translate` la
    reconnait.

    Rend None quand le recouvrement est vide. Rendre 0.0 ferait passer
    l'absence de mesure pour une concordance, ce qui est exactement le genre
    de faux vert qu'on ne veut pas dans un verdict de modele.
    """
    paires = [
        (a[k], b[k + decalage])
        for k in range(depuis, len(a))
        if 0 <= k + decalage < len(b)
    ]
    if not paires:
        return None
    return max(max(abs(ea.x - eb.x), abs(ea.y - eb.y)) for ea, eb in paires)


def concordent(a: list[Etat], b: list[Etat],
               tolerance: float = TOLERANCE_PX) -> bool:
    """Les deux traces racontent-elles le meme run ?

    Remplace la comparaison d'empreintes SHA-256, qui repond "les octets
    different" la ou la question est "le run s'est-il passe autrement".
    """
    return len(a) == len(b) and ecart_maximal(a, b)[1] <= tolerance


def classer_modele(ecarts: list[float | None],
                   tolerance: float = TOLERANCE_PX) -> str | None:
    """Modele A ou B, a partir d'ecarts entre traces recalees.

    "A" quand toutes les trajectoires atteignables sont la meme jouee plus
    tard : les traces se recouvrent a la tolerance pres. "B" quand leur forme
    differe vraiment.

    None quand rien n'est mesurable. Les `None` de la liste viennent d'un
    recouvrement vide (voir ecart_translate) : zero mesure ne fait pas un
    verdict, et repondre "A" faute de contre-exemple serait le pire des faux
    verts -- il ferait renoncer a une dimension de recherche sans preuve.
    """
    mesurables = [e for e in ecarts if e is not None]
    if not mesurables:
        return None
    return "A" if max(mesurables) <= tolerance else "B"


def _mediane(valeurs: list[float]) -> float:
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) / 2.0


def amplifie(a: list[Etat], b: list[Etat]) -> bool:
    """L'ecart entre les deux traces grandit-il au fil du run ?

    C'est la seule question qui condamne vraiment un TAS. Un ecart constant
    ou qui se resorbe est sans consequence ; un ecart qui croit finit par
    changer l'issue, quelle que soit sa petitesse au depart.

    Mediane et non moyenne, et la difference n'est pas cosmetique : mesure du
    2026-09-18, deux essais dont l'ecart reste exactement celui des positions
    de depart pendant 288 images, puis une bosse de douze images qui se
    resorbe d'un facteur 0,8 par image. La moyenne de la seconde moitie y
    triplait, et rendait un NO-GO sur le cas le plus favorable jamais mesure.
    La mediane ne bouge pas : douze images sur cent cinquante ne la deplacent
    pas, une divergence reelle si.
    """
    mesures = ecarts(a, b)
    if len(mesures) < 4 or max(mesures) == 0.0:
        return False
    milieu = len(mesures) // 2
    debut = _mediane(mesures[:milieu])
    fin = _mediane(mesures[milieu:])
    # Un facteur deux separe une croissance reelle d'une simple fluctuation.
    return fin > debut * 2.0


# Acceleration verticale du heros, mesuree image par image pendant un saut
# enregistre : ecarts de vitesse de +0,4183 px/image constants a 2e-4 pres.
# Voir NOTES.md, "Gravite, verrouillee sur l'image".
GRAVITE_PX_PAR_IMAGE2 = 0.4183

# En dessous de cette vitesse, le rapport d'une image a ses voisines n'a plus
# de sens : le heros rampe a ~1e-4 px/image apres un saut, et diviser par une
# telle valeur transforme du bruit en verdict.
VITESSE_MINIMALE_PX = 0.5

# Marge sur le nombre de pas deduit. Les rapports mesures valent 1,0000 ou
# 2,0000 a 1e-5 pres : un dixieme de pas est largement plus large que l'ecart
# observe, et assez etroit pour ne jamais confondre un pas avec deux.
MARGE_PAS = 0.1

# Au-dela de cet ecart entre les deux voisines, elles n'appartiennent pas a la
# meme phase lisse : impulsion d'un saut, choc, atterrissage. Quatre pas de
# gravite laissent passer l'image doublee, dont les voisines sont par
# construction distantes de trois pas, et rejettent l'impulsion d'un saut, qui
# en vaut plus de quatre-vingt-dix.
ECART_DE_PHASE_MAXIMAL = 4.0 * GRAVITE_PX_PAR_IMAGE2

# La premiere image enregistree porte une vitesse nulle par convention et non
# par mesure (agent/record.js n'a pas d'image precedente a soustraire). Elle ne
# peut donc ni etre classee, ni servir de voisine.
PREMIERE_IMAGE_CLASSABLE = 2


def images_figees(etats: list[Etat]) -> list[int]:
    """Images rendues SANS que le jeu avance sa simulation.

    Signature exacte, sans tolerance : la position ne change pas d'un bit,
    donc la vitesse -- qui est une difference de positions, voir
    agent/record.js -- vaut exactement zero. La chute reprend ensuite tout
    juste ou elle en etait.

    L'encadrement par du mouvement est ce qui distingue l'image figee du heros
    reellement immobile : au repos la vitesse est nulle au bit pres aussi
    (mesure sur 120 images), mais rien ne la precede ni ne la suit.
    """
    return [
        k
        for k in range(PREMIERE_IMAGE_CLASSABLE, len(etats) - 1)
        if etats[k].vx == 0.0
        and etats[k].vy == 0.0
        and (etats[k - 1].vx != 0.0 or etats[k - 1].vy != 0.0)
        and (etats[k + 1].vx != 0.0 or etats[k + 1].vy != 0.0)
    ]


def images_doublees(etats: list[Etat]) -> list[int]:
    """Images ayant recu DEUX pas de physique au lieu d'un.

    Dans toute phase lisse -- vitesse constante le long d'un mur, acceleration
    constante en vol --, la vitesse est localement lineaire en numero d'image :
    chaque image vaut la moyenne de ses deux voisines. Une image qui fusionne
    deux pas en vaut le double. Le test ne suppose donc aucune phase
    particuliere, ce qu'une detection fondee sur la seule gravite ne permettait
    pas : elle laissait passer les doublons du glissement, ou la vitesse est
    constante et l'ecart nul.
    """
    doublees = []
    for k in range(PREMIERE_IMAGE_CLASSABLE, len(etats) - 1):
        moyenne = (etats[k - 1].vy + etats[k + 1].vy) / 2.0
        if abs(moyenne) < VITESSE_MINIMALE_PX:
            continue
        if abs(etats[k + 1].vy - etats[k - 1].vy) > ECART_DE_PHASE_MAXIMAL:
            continue
        if abs(etats[k].vy / moyenne - 2.0) < MARGE_PAS:
            doublees.append(k)
    return doublees
