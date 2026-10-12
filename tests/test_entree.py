from controller.entree import ATTENTE_TAP, X_CENTRE, Y_CENTRE, taper


class FauxAdb:
    def __init__(self):
        self.commandes = []

    def __call__(self, *args, **kwargs):
        self.commandes.append(args)
        return ""


def test_le_tap_par_defaut_tombe_au_centre_de_l_ecran():
    adb = FauxAdb()
    dormis = []

    taper(adb=adb, dormir=dormis.append)

    assert adb.commandes == [
        ("shell", "input", "tap", str(X_CENTRE), str(Y_CENTRE))
    ]
    assert dormis == [ATTENTE_TAP]


def test_le_tap_accepte_des_coordonnees_et_une_attente_nulle():
    adb = FauxAdb()
    dormis = []

    taper(1250, 220, attente=0.0, adb=adb, dormir=dormis.append)

    assert adb.commandes == [("shell", "input", "tap", "1250", "220")]
    assert dormis == []
