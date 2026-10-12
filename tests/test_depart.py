import pytest

from controller.depart import (
    DepartError,
    au_depart,
    confirmer_le_depart,
    lire_position,
)


class FauxSonde:
    """Rend une suite de positions, une par appel a probe_state.

    None signifie "pas exactement un heros" : l'ecran de chargement, ou un
    moment ou l'objet n'est pas encore en memoire.
    """

    def __init__(self, positions):
        self.positions = list(positions)
        self.vues = 0
        self.courante = None

    # L'avance se fait ici et non dans probe_state : un ecran sans heros
    # n'atteint jamais probe_state, et la suite ne defilerait pas.
    def probe_resolve(self):
        indice = min(self.vues, len(self.positions) - 1)
        self.courante = self.positions[indice]
        self.vues += 1
        return {"vus": 1, "objets": 0 if self.courante is None else 1,
                "heros": "0x1"}

    def probe_state(self):
        if self.courante is None:
            return None
        return {"x": self.courante[0], "y": self.courante[1],
                "px": 0.0, "py": 0.0}


def test_la_position_du_menu_n_est_pas_celle_du_depart():
    """Releve du 2026-09-18 : (352, 548) sur le menu principal, (160, 548) a
    l'ecran de commencement. Rien d'autre ne distingue les deux ecrans."""
    assert au_depart((352.0, 548.0), 160.0, 548.0) is False
    assert au_depart((160.0, 548.0), 160.0, 548.0) is True


def test_une_position_absente_n_est_jamais_le_depart():
    assert au_depart(None, 160.0, 548.0) is False


def test_la_tolerance_absorbe_la_derniere_decimale():
    assert au_depart((160.4, 548.3), 160.0, 548.0) is True
    assert au_depart((161.0, 548.0), 160.0, 548.0) is False


def test_lire_position_rend_none_sans_heros_unique():
    class SansHeros:
        def probe_resolve(self):
            return {"vus": 3, "objets": 2, "heros": None}

        def probe_state(self):
            raise AssertionError("ne doit pas etre appele sans heros unique")

    assert lire_position(SansHeros()) is None


def test_la_confirmation_rend_la_position_relevee():
    sonde = FauxSonde([(352.0, 548.0)])
    invites = []

    position = confirmer_le_depart(sonde, demander=lambda: None,
                                   dire=invites.append)

    assert position == (352.0, 548.0)
    assert "Enter" in invites[0]


def test_la_confirmation_refuse_un_ecran_sans_heros_unique():
    sonde = FauxSonde([None])

    with pytest.raises(DepartError):
        confirmer_le_depart(sonde, demander=lambda: None,
                            dire=lambda t: None)


def test_la_confirmation_signale_un_ecart_sans_refuser():
    """La position suit la camera et non la forme du donjon : refuser
    la-dessus bloquerait des rejeux legitimes. On previent, l'empreinte
    tranche."""
    sonde = FauxSonde([(500.0, 548.0)])
    dits = []

    position = confirmer_le_depart(sonde, attendu=(352.0, 548.0),
                                   demander=lambda: None, dire=dits.append)

    assert position == (500.0, 548.0)
    assert any("warning" in ligne for ligne in dits)


def test_la_confirmation_accepte_la_meme_position():
    sonde = FauxSonde([(352.0, 548.0)])

    position = confirmer_le_depart(sonde, attendu=(352.0, 548.0),
                                   demander=lambda: None, dire=lambda t: None)

    assert position == (352.0, 548.0)
