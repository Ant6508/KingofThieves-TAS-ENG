import pytest

from controller.cible import (
    PAS_DE_CIBLE_PX,
    Cible,
    CibleError,
    atteinte,
    progression,
    proposer_cible,
)
from controller.trace import Etat


def etats(*positions):
    """Une trace fabriquee : une position par image, vitesse deduite."""
    faits = []
    precedente = None
    for rang, (x, y) in enumerate(positions):
        vx = 0.0 if precedente is None else x - precedente[0]
        vy = 0.0 if precedente is None else y - precedente[1]
        faits.append(Etat(frame=rang, x=x, y=y, vx=vx, vy=vy))
        precedente = (x, y)
    return faits


def marche(depart, pas, combien, y=500.0):
    """Une marche rectiligne sur x, assez longue pour etre significative."""
    return etats(*[(depart + pas * k, y) for k in range(combien)])


# ----- progression -----

def test_vers_la_gauche_le_plus_avance_est_le_plus_petit_x():
    trace = marche(800.0, -5.0, 40)
    cible = Cible(axe="x", sens=-1, seuil=700.0, image_limite=40)

    # sens * valeur : le plus avance est toujours le plus grand nombre.
    assert progression(trace, cible) == pytest.approx(-605.0)


def test_vers_la_droite_le_plus_avance_est_le_plus_grand_x():
    trace = marche(100.0, 5.0, 40)
    cible = Cible(axe="x", sens=1, seuil=200.0, image_limite=40)

    assert progression(trace, cible) == pytest.approx(295.0)


def test_le_retour_au_depart_apres_la_mort_n_entame_pas_la_progression():
    """Un heros tue voit le niveau se remettre en place et revient a son
    point de depart. La progression est un maximum : elle survit."""
    aller = [(800.0 - 5.0 * k, 500.0) for k in range(40)]
    retour = [(800.0, 500.0)] * 20
    trace = etats(*(aller + retour))
    cible = Cible(axe="x", sens=-1, seuil=700.0, image_limite=60)

    assert progression(trace, cible) == pytest.approx(-605.0)


def test_l_image_limite_coupe_la_trace():
    trace = marche(800.0, -5.0, 40)
    cible = Cible(axe="x", sens=-1, seuil=700.0, image_limite=10)

    assert progression(trace, cible) == pytest.approx(-755.0)


def test_une_trace_vide_n_a_pas_de_progression():
    cible = Cible(axe="x", sens=-1, seuil=700.0, image_limite=10)

    with pytest.raises(CibleError):
        progression([], cible)


def test_une_fenetre_sans_mouvement_est_refusee():
    """Un essai qui n a pas eu lieu -- ancrage rate, tap jamais recu -- ne
    doit pas concourir au podium avec sa position de depart pour score."""
    fige = etats(*[(500.0, 500.0)] * 60)

    with pytest.raises(CibleError):
        progression(fige, Cible("x", -1, 505.0, 60))


def test_un_essai_qui_bouge_a_peine_reste_mesure():
    """Le garde-fou ne rejette que l immobilite complete : un run court mais
    legitime bouge moins qu une demi-seconde, et l avorter couterait plus
    cher que le defaut repare."""
    trace = etats((500.0, 500.0), (499.0, 500.0), (499.0, 500.0))

    assert progression(trace, Cible("x", -1, 600.0, 3)) == pytest.approx(-499.0)


# ----- atteinte -----

def test_l_essai_qui_depasse_le_seuil_reussit():
    trace = marche(800.0, -5.0, 40)

    assert atteinte(trace, Cible("x", -1, 700.0, 40)) is True


def test_l_essai_qui_s_arrete_avant_echoue():
    trace = marche(800.0, -5.0, 40)

    assert atteinte(trace, Cible("x", -1, 500.0, 40)) is False


def test_le_bord_exact_du_seuil_compte_comme_atteint():
    trace = marche(800.0, -5.0, 40)

    assert atteinte(trace, Cible("x", -1, 605.0, 40)) is True


# ----- proposer_cible -----

def test_l_axe_propose_est_celui_de_la_plus_grande_amplitude():
    trace = etats(*[(800.0 - 5.0 * k, 500.0 + 0.5 * k) for k in range(40)])

    cible = proposer_cible(trace)

    assert cible.axe == "x"


def test_le_sens_propose_est_celui_de_la_marche():
    vers_la_gauche = proposer_cible(marche(800.0, -5.0, 40))
    vers_la_droite = proposer_cible(marche(100.0, 5.0, 40))

    assert vers_la_gauche.sens == -1
    assert vers_la_droite.sens == 1


def test_le_seuil_propose_est_la_ou_l_essai_s_est_arrete():
    cible = proposer_cible(marche(800.0, -5.0, 40))

    assert cible.seuil == pytest.approx(605.0)
    assert cible.image_limite == 40


def test_la_cible_proposee_est_atteinte_de_justesse_par_son_propre_essai():
    """Elle dit 'la ou tu t es arrete' : l essai qui l a produite la touche,
    et tout essai qui va moins loin echoue."""
    trace = marche(800.0, -5.0, 40)
    cible = proposer_cible(trace)

    assert atteinte(trace, cible) is True
    assert atteinte(marche(800.0, -4.0, 40), cible) is False


def test_l_axe_vertical_est_propose_quand_c_est_lui_qui_bouge():
    trace = etats(*[(300.0, 800.0 - 5.0 * k) for k in range(40)])

    cible = proposer_cible(trace)

    assert cible.axe == "y"
    assert cible.sens == -1


def test_une_trace_immobile_ne_designe_aucun_axe():
    """Designer un axe au hasard lancerait 49 essais contre une cible qui ne
    veut rien dire."""
    trace = etats(*[(300.0, 500.0)] * 60)

    with pytest.raises(CibleError):
        proposer_cible(trace)


def test_le_sens_suit_l_extremum_atteint_le_plus_tard():
    """Un elan avant le vrai mouvement ne doit pas retourner la cible.
    L heuristique naive -- la plus grande excursion depuis le depart --
    rendait ici +1, parce que l elan de 20 px depasse la progression de
    17 px d un essai qui meurt tot."""
    elan = [(500.0 + k, 500.0) for k in range(21)]        # 500 -> 520
    vrai = [(520.0 - 1.85 * k, 500.0) for k in range(1, 21)]  # 520 -> 483
    trace = etats(*(elan + vrai))

    cible = proposer_cible(trace)

    assert cible.sens == -1
    assert cible.seuil == pytest.approx(483.0)


def test_un_elan_ne_retourne_pas_le_podium():
    """Le defaut que la correction repare : l essai qui avance le plus doit
    etre celui qui atteint la cible, pas l inverse."""
    elan = [(500.0 + k, 500.0) for k in range(21)]
    vrai = [(520.0 - 1.85 * k, 500.0) for k in range(1, 21)]
    calibration = etats(*(elan + vrai))
    cible = proposer_cible(calibration)

    meilleur = etats(*(elan + [(520.0 - 3.45 * k, 500.0)
                               for k in range(1, 41)]))

    assert atteinte(meilleur, cible) is True
    assert progression(meilleur, cible) > progression(calibration, cible)


def test_un_essai_mortel_garde_le_bon_sens():
    """Le niveau se remet en place et le heros revient a son depart. Ce
    depart avait deja ete touche a l image 0, donc la premiere occurrence du
    maximum reste au debut et le sens ne bascule pas."""
    aller = [(800.0 - 5.0 * k, 500.0) for k in range(40)]
    retour = [(800.0, 500.0)] * 20
    cible = proposer_cible(etats(*(aller + retour)))

    assert cible.sens == -1
    assert cible.seuil == pytest.approx(605.0)


# ----- reglage -----

def test_la_cible_se_deplace_dans_le_sens_de_la_marche():
    cible = Cible("x", -1, 600.0, 40)

    plus_loin = cible.deplacee(PAS_DE_CIBLE_PX)
    plus_pres = cible.deplacee(-PAS_DE_CIBLE_PX)

    assert plus_loin.seuil == pytest.approx(590.0)
    assert plus_pres.seuil == pytest.approx(610.0)


def test_un_axe_inconnu_est_refuse():
    with pytest.raises(CibleError):
        Cible("z", 1, 0.0, 10)


def test_un_sens_inconnu_est_refuse():
    with pytest.raises(CibleError):
        Cible("x", 0, 0.0, 10)


def test_une_image_limite_negative_est_refusee():
    """Python tronquerait la trace par la fin au lieu de refuser."""
    with pytest.raises(CibleError):
        Cible("x", -1, 600.0, -5)


def test_atteinte_propage_le_refus_au_lieu_de_rendre_faux():
    """Un essai qui n a pas eu lieu doit arreter le balayage, pas y figurer
    comme un echec ordinaire : les deux ne demandent pas la meme conduite."""
    fige = etats(*[(500.0, 500.0)] * 60)

    with pytest.raises(CibleError):
        atteinte(fige, Cible("x", -1, 505.0, 60))
