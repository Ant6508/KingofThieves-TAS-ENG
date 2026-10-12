"""La boucle d'autoclic : cadence, limites, absence de rafale.

`boucle` recoit son horloge, son sommeil et son taper, donc tout se joue ici
sans MEmu et sans adb. L'horloge n'avance que quand le sommeil ou le cout d'un
toucher la fait avancer : le temps du test est entierement determine.
"""

import importlib.util
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def charger_autoclic():
    """Charge scripts/autoclic.py comme un module, sans l'executer comme script."""
    if RACINE not in sys.path:
        sys.path.insert(0, RACINE)
    chemin = os.path.join(RACINE, "scripts", "autoclic.py")
    spec = importlib.util.spec_from_file_location("autoclic_pour_test", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


autoclic = charger_autoclic()

from controller.device import DeviceError  # noqa: E402


class FausseHorloge:
    """N'avance que quand on le lui demande."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avancer(self, secondes):
        self.t += secondes


class FauxTaper:
    """Note l'instant de chaque toucher, et fait avancer l'horloge de son cout.

    `cout` represente le temps que prend un `adb input tap` : 80 a 200 ms en
    vrai. C'est ce cout qui ferait deriver une boucle a sommeil fixe.
    """

    def __init__(self, horloge, cout=0.0, lever_au=None, erreur=None):
        self.horloge = horloge
        self.cout = cout
        self.lever_au = lever_au
        self.erreur = erreur
        self.instants = []
        self.appels = []

    def __call__(self, x, y, attente=None):
        if self.lever_au is not None and len(self.appels) + 1 == self.lever_au:
            raise self.erreur
        self.instants.append(round(self.horloge(), 6))
        self.appels.append((x, y, attente))
        self.horloge.avancer(self.cout)


def test_la_cadence_ne_derive_pas_quand_le_toucher_coute_du_temps():
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge, cout=0.2)

    rendu = autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        taps=5,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert frappe.instants == [0.0, 0.5, 1.0, 1.5, 2.0]
    assert rendu.emis == 5
    assert rendu.sautes == 0


def test_le_toucher_part_aux_coordonnees_demandees_sans_attente_integree():
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge)

    autoclic.boucle(
        1250,
        220,
        intervalle=0.25,
        taps=2,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert frappe.appels == [(1250, 220, 0.0), (1250, 220, 0.0)]


def test_la_limite_de_duree_arrete_la_boucle():
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge)

    rendu = autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        duree=1.9,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert frappe.instants == [0.0, 0.5, 1.0, 1.5]
    assert rendu.emis == 4


def test_un_toucher_du_a_la_seconde_exacte_de_la_limite_part_encore():
    """La limite est "aucun toucher au-dela de S", pas "avant S"."""
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge)

    autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        duree=2.0,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert frappe.instants == [0.0, 0.5, 1.0, 1.5, 2.0]


def test_la_premiere_limite_atteinte_l_emporte():
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge)

    rendu = autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        taps=100,
        duree=1.0,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert rendu.emis == 3


def test_un_toucher_plus_lent_que_l_intervalle_saute_des_creneaux_sans_rafale():
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge, cout=0.8)

    rendu = autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        taps=3,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    # Un creneau sur deux est saute, et jamais deux touchers coup sur coup.
    assert frappe.instants == [0.0, 1.0, 2.0]
    assert rendu.sautes == 2
    ecarts = [b - a for a, b in zip(frappe.instants, frappe.instants[1:])]
    assert all(ecart >= 0.5 for ecart in ecarts)


def test_un_echec_adb_arrete_la_boucle_et_rapporte_ce_qui_est_parti():
    horloge = FausseHorloge()
    panne = DeviceError("adb shell input tap a echoue : device offline")
    frappe = FauxTaper(horloge, lever_au=3, erreur=panne)

    rendu = autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        taps=10,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert rendu.emis == 2
    assert rendu.erreur is panne


def test_ctrl_c_arrete_la_boucle_et_rapporte_ce_qui_est_parti():
    horloge = FausseHorloge()
    frappe = FauxTaper(horloge, lever_au=4, erreur=KeyboardInterrupt())

    rendu = autoclic.boucle(
        800,
        450,
        intervalle=0.5,
        taps=10,
        taper=frappe,
        dormir=horloge.avancer,
        horloge=horloge,
    )

    assert rendu.emis == 3
    assert isinstance(rendu.erreur, KeyboardInterrupt)


def test_les_arguments_minimaux_donnent_une_config():
    config = autoclic.analyser_arguments(["800", "450", "--taps", "60"])

    assert config.x == 800
    assert config.y == 450
    assert config.intervalle == 1.0
    assert config.taps == 60
    assert config.duree is None


def test_sans_limite_le_script_refuse_de_demarrer():
    with pytest.raises(autoclic.ArgumentsInvalides):
        autoclic.analyser_arguments(["800", "450", "--intervalle", "0.5"])


def test_un_intervalle_nul_ou_negatif_est_refuse():
    with pytest.raises(autoclic.ArgumentsInvalides):
        autoclic.analyser_arguments(["800", "450", "--taps", "5", "--intervalle", "0"])


def test_une_coordonnee_illisible_ne_fait_pas_quitter_le_processus():
    """argparse appelle sys.exit par defaut : on le remplace par une exception."""
    with pytest.raises(autoclic.ArgumentsInvalides):
        autoclic.analyser_arguments(["gauche", "450", "--taps", "5"])


def test_l_annonce_rappelle_l_ordonnee_correspondante_dans_la_fenetre_memu():
    config = autoclic.analyser_arguments(["1250", "220", "--taps", "5"])

    texte = autoclic.annonce(config)

    assert "1250" in texte
    assert "220" in texte
    assert "253" in texte  # 220 + 33, l'ordonnee cote fenetre MEmu


def test_le_bilan_signale_les_creneaux_sautes_et_la_cause_de_l_arret():
    panne = DeviceError("device offline")
    rendu = autoclic.CompteRendu(emis=7, duree_reelle=3.5, sautes=2, erreur=panne)

    texte = autoclic.bilan(rendu)

    assert "7 taps" in texte
    assert "2 slots skipped" in texte
    assert "device offline" in texte


def test_le_bilan_d_une_serie_complete_ne_parle_ni_de_saut_ni_d_erreur():
    rendu = autoclic.CompteRendu(emis=60, duree_reelle=60.0, sautes=0)

    texte = autoclic.bilan(rendu)

    assert "60 taps" in texte
    assert "skipped" not in texte
    assert "arrete" not in texte
