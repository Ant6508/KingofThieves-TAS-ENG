from controller.relance import ATTENTE_DEMARRAGE, demarrer, force_stop, relancer


class FauxAdb:
    def __init__(self):
        self.commandes = []

    def __call__(self, *args, **kwargs):
        self.commandes.append(args)
        return ""


def test_force_stop_vise_le_paquet_du_jeu():
    adb = FauxAdb()

    force_stop(adb=adb)

    assert adb.commandes == [
        ("shell", "am", "force-stop", "com.zeptolab.thieves.google")
    ]


def test_demarrer_passe_par_monkey():
    """monkey plutot qu'un nom d'activite : il trouve l'activite de lancement
    tout seul, donc une mise a jour du jeu ne casse pas cette ligne."""
    adb = FauxAdb()

    demarrer(adb=adb)

    assert adb.commandes[0][:4] == ("shell", "monkey", "-p",
                                    "com.zeptolab.thieves.google")


def test_relancer_arrete_puis_demarre_et_ne_tape_nulle_part():
    """Le parcours de taps automatique a ete retire : il naviguait en aveugle
    et un tap decale a ouvert une boite d'achat. C'est l'operateur qui
    navigue desormais."""
    adb = FauxAdb()
    attentes = []

    relancer(adb=adb, dormir=attentes.append)

    # adb("shell", "am", "force-stop", ...) : le verbe est au deuxieme champ,
    # le premier etant toujours "shell".
    assert [c[1] for c in adb.commandes] == ["am", "monkey"]
    assert [c for c in adb.commandes if c[1] == "input"] == []
    assert attentes == [ATTENTE_DEMARRAGE]
