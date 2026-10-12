import pytest

from controller.keys import decoder


def source(*octets):
    """Une source d'octets qui se vide, comme msvcrt.getch()."""
    restants = list(octets)

    def lire():
        if not restants:
            raise AssertionError("le decodeur a lu plus d'octets qu'il ne faut")
        return restants.pop(0)

    return lire


@pytest.mark.parametrize(
    "octets,attendu",
    [
        ((b"p",), "pause"),
        ((b"P",), "pause"),
        ((b" ",), "saut"),
        ((b"n",), "avance"),
        ((b"N",), "avance"),
        ((b"\t",), "avance10"),
        ((b"\x08",), "annuler"),
        ((b"t",), "turbo"),
        ((b"q",), "quitter"),
        ((b"\x1b",), "quitter"),
        ((b"\xe0", b"H"), "saut_precedent"),
        ((b"\x00", b"H"), "saut_precedent"),
        ((b"\xe0", b"P"), "saut_suivant"),
        ((b"\xe0", b"K"), "reculer_saut"),
        ((b"\xe0", b"M"), "avancer_saut"),
        ((b"\x00", b";"), "relance"),
        ((b"\xe0", b"<"), "essai"),
        ((b"\x00", b"="), "validation"),
        ((b"\x00", b"?"), "ecrire"),
        ((b"\x00", b">"), "balayage"),
        ((b"\xe0", b">"), "balayage"),
        ((b"\r",), "entree"),
    ],
)
def test_les_touches_de_l_editeur(octets, attendu):
    assert decoder(source(*octets)) == attendu


def test_la_fleche_bas_ne_se_confond_pas_avec_la_touche_pause():
    """Les deux arrivent comme l'octet b"P" : seul le prefixe les separe, et
    c'est exactement le genre de collision qu'un decodeur naif avale."""
    assert decoder(source(b"\x00", b"P")) == "saut_suivant"
    assert decoder(source(b"P")) == "pause"


def test_une_touche_inconnue_ne_vaut_rien():
    assert decoder(source(b"z")) is None


def test_une_touche_etendue_inconnue_consomme_ses_deux_octets():
    lire = source(b"\xe0", b"G", b"p")

    assert decoder(lire) is None
    assert decoder(lire) == "pause"
