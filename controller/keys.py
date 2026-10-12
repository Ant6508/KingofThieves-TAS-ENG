"""Lecture des touches dans la console.

Pas de capture globale (spec 1 ter K) : les taps partent par `adb input tap`,
donc MEmu n'a jamais besoin du focus. msvcrt est dans la bibliotheque standard
de Windows -- aucune dependance, aucun droit administrateur.

Le decodage est separe de la lecture pour qu'il se teste sans clavier : le
harnais lui passe une source d'octets, la seance lui passe msvcrt.getch.
"""

from __future__ import annotations

# Une touche etendue (fleche, touche de fonction) arrive en deux octets : un
# prefixe, puis un code. Les deux prefixes existent selon la touche et le
# terminal ; les traiter tous les deux coute une ligne.
PREFIXES = (b"\x00", b"\xe0")

TOUCHES = {
    b"p": "pause",
    b"P": "pause",
    b" ": "saut",
    b"n": "avance",
    b"N": "avance",
    b"\t": "avance10",
    b"\x08": "annuler",
    b"t": "turbo",
    b"T": "turbo",
    b"q": "quitter",
    b"Q": "quitter",
    b"\x1b": "quitter",
    b"\r": "entree",
}

# Les fleches servent a l'edition et non au deplacement dans le run : decaler
# un saut d'une image est le geste le plus frequent d'une seance d'ajustement,
# et il merite les meilleures touches. L'avance passe sur `n`.
TOUCHES_ETENDUES = {
    b"H": "saut_precedent",   # fleche haut
    b"P": "saut_suivant",     # fleche bas -- meme octet que la touche `P`,
                              # que seul le prefixe distingue
    b"K": "reculer_saut",     # fleche gauche
    b"M": "avancer_saut",     # fleche droite
    b";": "relance",          # F1
    b"<": "essai",            # F2
    b"=": "validation",       # F3
    b">": "balayage",         # F4
    b"?": "ecrire",           # F5
}


def decoder(lire_octet) -> str | None:
    """Rend le nom de l'action, ou None si la touche n'en porte aucune.

    Une touche etendue inconnue consomme quand meme ses deux octets : sans
    cela, son code resterait dans la file et serait relu comme une touche
    simple a l'appel suivant.
    """
    octet = lire_octet()
    if octet in PREFIXES:
        return TOUCHES_ETENDUES.get(lire_octet())
    return TOUCHES.get(octet)


def lire_touche() -> str | None:
    """Bloque jusqu'a une frappe et rend le nom de l'action.

    msvcrt est importe ici et non en tete de module : les tests du decodeur
    tournent alors sur n'importe quelle plateforme.
    """
    import msvcrt

    return decoder(msvcrt.getch)


def frappe_en_attente() -> bool:
    """Une touche attend-elle d'etre lue ?

    Isole msvcrt.kbhit pour que la boucle de balayage se teste sans clavier.
    Cette fonction-ci ne prend rien et n'est pas parametrable : c'est la
    BOUCLE qui recoit un `interrompu` injectable, et `frappe_en_attente` en
    est la valeur de production. Le harnais lui en passe une autre.

    Sans elle, la seule facon de demander "veut-on m'arreter ?" serait de
    bloquer sur une frappe, ce qui arreterait le balayage a chaque essai.
    """
    import msvcrt

    return bool(msvcrt.kbhit())
