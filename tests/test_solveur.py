import pytest

from controller.solveur import (
    Balayage,
    Couple,
    SolveurError,
    espace,
)


# ----- l espace -----

def test_l_espace_couvre_le_carre_des_deux_rayons():
    couples = espace(rayon_p=3, rayon_t=3)

    assert len(couples) == 49
    assert len(set(couples)) == 49


def test_l_espace_commence_par_le_centre():
    couples = espace(rayon_p=3, rayon_t=3)

    assert couples[0] == Couple(0, 0)


def test_l_espace_va_du_centre_vers_l_exterieur():
    """Si le couple qui passe est a une image, on le sait au troisieme essai
    et non au quarante-septieme."""
    couples = espace(rayon_p=3, rayon_t=3)
    distances = [c.distance for c in couples]

    assert distances == sorted(distances)
    assert set(couples[1:5]) == {Couple(0, -1), Couple(0, 1),
                                 Couple(-1, 0), Couple(1, 0)}


def test_un_rayon_nul_reduit_l_espace_a_une_dimension():
    couples = espace(rayon_p=0, rayon_t=3)

    assert len(couples) == 7
    assert all(c.precedent == 0 for c in couples)


def test_a_distance_egale_le_saut_travaille_passe_avant_le_precedent():
    """Les deux dimensions ne se valent pas : celle du saut travaille change
    la phase des pieges, celle du precedent peut n avoir aucun effet. Payer
    les essais dans le mauvais ordre, c est chercher d abord la ou on doute.

    Ce test verrouille la SEQUENCE et pas seulement l ensemble : le test
    voisin compare des ensembles, donc un renversement du departage ne le
    ferait pas tomber."""
    couples = espace(rayon_p=3, rayon_t=3)

    assert couples[1:5] == [Couple(0, -1), Couple(0, 1),
                            Couple(-1, 0), Couple(1, 0)]


# ----- les couples impossibles -----

def test_un_couple_qui_ferait_se_confondre_deux_sauts_est_impossible():
    balayage = Balayage([100, 102], index=1, images=400, couples=[Couple(0, -2)])

    assert balayage.resultats[Couple(0, -2)].impossible is True
    assert balayage.prochain() is None
    assert balayage.total == 0


def test_un_couple_qui_ferait_tomber_un_saut_avant_l_image_zero_est_impossible():
    balayage = Balayage([1, 50], index=1, images=400, couples=[Couple(-3, 0)])

    assert balayage.resultats[Couple(-3, 0)].impossible is True


def test_un_couple_qui_pousse_un_saut_hors_du_run_est_impossible():
    """derouler ignore SILENCIEUSEMENT un tap au-dela de la derniere image
    (controller/run.py : `n < images`). L essai se deroulerait donc sans ce
    saut, et sa progression serait mesuree comme si de rien n etait : un
    couple ampute passerait pour un couple essaye."""
    balayage = Balayage([100, 298], index=1, images=300,
                        couples=[Couple(0, 2), Couple(0, 1)])

    assert balayage.resultats[Couple(0, 2)].impossible is True
    assert balayage.sauts_de(Couple(0, 1)) == [100, 299]


def test_les_deux_decalages_s_appliquent_en_une_fois():
    """Le piege : applique l un apres l autre, le precedent entre en
    collision avec un saut qui va lui aussi bouger. {102, 104} est pourtant
    valide, et ce couple doit couter un essai."""
    balayage = Balayage([100, 102], index=1, images=400, couples=[Couple(2, 2)])

    assert balayage.prochain() == Couple(2, 2)
    assert balayage.sauts_de(Couple(2, 2)) == [102, 104]


def test_sans_saut_precedent_seul_le_decalage_nul_est_possible():
    balayage = Balayage([100], index=0, images=400,
                        couples=[Couple(0, 1), Couple(1, 0)])

    assert balayage.sauts_de(Couple(0, 1)) == [101]
    assert balayage.resultats[Couple(1, 0)].impossible is True


def test_demander_les_sauts_d_un_couple_impossible_est_une_erreur():
    balayage = Balayage([100, 102], index=1, images=400, couples=[Couple(0, -2)])

    with pytest.raises(SolveurError):
        balayage.sauts_de(Couple(0, -2))


def test_l_image_travaillee_suit_le_saut_et_non_son_rang():
    """Un saut qui passe devant son voisin reste celui qu on travaille."""
    balayage = Balayage([100, 102], index=1, images=400, couples=[Couple(0, -3)])

    assert balayage.sauts_de(Couple(0, -3)) == [99, 100]
    assert balayage.image_travaillee(Couple(0, -3)) == 99


# ----- l avancement -----

def test_un_balayage_neuf_propose_son_premier_couple():
    balayage = Balayage([100, 200], index=1, images=400)

    assert balayage.prochain() == Couple(0, 0)
    assert balayage.faits == 0


def test_noter_un_couple_le_retire_des_restants():
    balayage = Balayage([100, 200], index=1, images=400)

    balayage.noter(Couple(0, 0), progression=-500.0, reussi=False)

    assert balayage.prochain() != Couple(0, 0)
    assert balayage.faits == 1
    assert Couple(0, 0) not in balayage.restants()


def test_le_balayage_se_termine_quand_tout_est_note():
    balayage = Balayage([100, 200], index=1, images=400, couples=[Couple(0, 0)])

    balayage.noter(Couple(0, 0), progression=-500.0, reussi=True)

    assert balayage.prochain() is None
    assert balayage.restants() == []


def test_noter_un_couple_impossible_est_une_erreur():
    balayage = Balayage([100, 102], index=1, images=400, couples=[Couple(0, -2)])

    with pytest.raises(SolveurError):
        balayage.noter(Couple(0, -2), progression=0.0, reussi=False)


def test_un_film_vide_ne_se_balaie_pas():
    with pytest.raises(SolveurError):
        Balayage([], index=0, images=400)


def test_un_rang_hors_du_film_est_refuse():
    with pytest.raises(SolveurError):
        Balayage([100, 200], index=2, images=400)


# ----- le podium -----

def test_le_podium_classe_par_progression_decroissante():
    balayage = Balayage([100, 200], index=1, images=400)
    balayage.noter(Couple(0, 0), progression=-700.0, reussi=False)
    balayage.noter(Couple(0, 1), progression=-500.0, reussi=True)
    balayage.noter(Couple(0, -1), progression=-600.0, reussi=False)

    classement = [r.couple for r in balayage.podium()]

    assert classement == [Couple(0, 1), Couple(0, -1), Couple(0, 0)]


def test_a_progression_egale_le_plus_petit_deplacement_gagne():
    balayage = Balayage([100, 200], index=1, images=400)
    balayage.noter(Couple(2, 2), progression=-500.0, reussi=True)
    balayage.noter(Couple(0, 1), progression=-500.0, reussi=True)

    assert balayage.meilleur().couple == Couple(0, 1)


def test_le_podium_ne_rend_que_ce_qu_on_lui_demande():
    balayage = Balayage([100, 200], index=1, images=400)
    for rang, couple in enumerate(espace(1, 1)):
        balayage.noter(couple, progression=float(-rang), reussi=False)

    assert len(balayage.podium(combien=5)) == 5


def test_sans_essai_il_n_y_a_pas_de_meilleur():
    assert Balayage([100, 200], index=1, images=400).meilleur() is None


def test_les_reussis_se_comptent():
    balayage = Balayage([100, 200], index=1, images=400)
    balayage.noter(Couple(0, 0), progression=-700.0, reussi=False)
    balayage.noter(Couple(0, 1), progression=-500.0, reussi=True)

    assert len(balayage.reussis) == 1
    assert balayage.reussis[0].couple == Couple(0, 1)


def test_noter_un_couple_etranger_a_l_espace_est_une_erreur():
    """Il compterait dans faits sans compter dans total, et pourrait gagner
    le podium sans etre passe par la validation de _sauts_de."""
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(1, 1))

    with pytest.raises(SolveurError):
        balayage.noter(Couple(9, 9), progression=-100.0, reussi=True)


def test_noter_deux_fois_le_meme_couple_est_une_erreur():
    """Ecraser en silence ferait disparaitre un essai qu on a paye."""
    balayage = Balayage([100, 200], index=1, images=400)
    balayage.noter(Couple(0, 0), progression=-700.0, reussi=False)

    with pytest.raises(SolveurError):
        balayage.noter(Couple(0, 0), progression=-500.0, reussi=True)


def test_sans_saut_precedent_l_espace_par_defaut_retombe_a_sept_essais():
    """Avec index=0, les 42 couples qui decalent un saut precedent inexistant
    sont impossibles, et ne coutent rien."""
    balayage = Balayage([100], index=0, images=400)

    assert balayage.total == 7


def test_l_image_travaillee_refuse_un_couple_impossible():
    """Le chemin d erreur propre de image_travaillee, exerce pour lui-meme :
    rendre un numero d image pour un essai qui n aura pas lieu ferait
    travailler un appelant sur un essai fantome."""
    balayage = Balayage([100, 102], index=1, images=400, couples=[Couple(0, -2)])

    with pytest.raises(SolveurError):
        balayage.image_travaillee(Couple(0, -2))


# ----- la boucle -----

from controller.cible import Cible
from controller.solveur import balayer
from controller.trace import Etat


CIBLE = Cible(axe="x", sens=-1, seuil=600.0, image_limite=40)


def trace_qui_va_jusqu_a(x_final):
    """Une trace rectiligne de 800 jusqu'a `x_final`, en 40 images."""
    pas = (x_final - 800.0) / 39.0
    faits = []
    for k in range(40):
        x = 800.0 + pas * k
        faits.append(Etat(frame=k, x=x, y=500.0, vx=pas, vy=0.0))
    return faits


def essayeur(par_couple, journal=None):
    """Un `essayer` factice : rend la trace prevue pour la liste de sauts.

    Il ne connait pas les couples, seulement les sauts -- comme le vrai.
    """
    def essayer(sauts):
        if journal is not None:
            journal.append(list(sauts))
        return trace_qui_va_jusqu_a(par_couple.get(tuple(sauts), 700.0))
    return essayer


def test_la_boucle_essaie_tous_les_couples_puis_se_termine():
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(1, 1))
    journal = []

    fin = balayer(balayage, essayeur({}, journal), CIBLE)

    assert fin == "termine"
    assert balayage.faits == 9
    assert len(journal) == 9
    assert balayage.prochain() is None


def test_la_boucle_note_le_verdict_de_chaque_essai():
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(0, 1))
    # Le saut travaille decale de +1 tombe a 201 et atteint 550 : reussi.
    prevues = {(100, 201): 550.0}

    balayer(balayage, essayeur(prevues), CIBLE)

    assert [r.couple for r in balayage.reussis] == [Couple(0, 1)]
    assert balayage.meilleur().couple == Couple(0, 1)


def test_la_boucle_s_arrete_quand_on_l_interrompt():
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(1, 1))
    tours = []

    def interrompu():
        tours.append(1)
        return len(tours) > 3

    fin = balayer(balayage, essayeur({}), CIBLE, interrompu=interrompu)

    assert fin == "interrompu"
    assert balayage.faits == 3
    assert len(balayage.restants()) == 6


def test_une_erreur_d_ancrage_traverse_et_laisse_le_balayage_reprenable():
    """C est le garde-fou : au premier doute sur l ancrage, on n emet plus un
    seul tap. Les essais deja faits restent acquis."""
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(1, 1))
    faits = []

    def essayer(sauts):
        if len(faits) == 3:
            raise RuntimeError("ancrage douteux")
        faits.append(list(sauts))
        return trace_qui_va_jusqu_a(700.0)

    with pytest.raises(RuntimeError):
        balayer(balayage, essayer, CIBLE)

    assert balayage.faits == 3
    assert len(balayage.restants()) == 6

    # La reprise repart du quatrieme, et non du premier.
    fin = balayer(balayage, essayeur({}), CIBLE)

    assert fin == "termine"
    assert balayage.faits == 9


def test_la_boucle_dit_chaque_resultat_a_mesure():
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(0, 1))
    dits = []

    balayer(balayage, essayeur({}), CIBLE,
            dire=lambda b, r: dits.append((b.faits, r.couple)))

    assert dits == [(1, Couple(0, 0)), (2, Couple(0, -1)), (3, Couple(0, 1))]


def test_la_boucle_ne_depense_pas_d_essai_sur_un_couple_impossible():
    balayage = Balayage([100, 102], index=1, images=400, couples=espace(0, 3))
    journal = []

    balayer(balayage, essayeur({}, journal), CIBLE)

    # Sept couples, mais decaler le saut travaille de -2 le ferait tomber sur
    # 100, ou l'autre saut se trouve deja : six essais, pas sept.
    assert balayage.total == 6
    assert len(journal) == 6


def test_interrompu_des_le_premier_tour_n_emet_aucun_tap():
    """La garantie la plus sensible du module : pas un seul appui avant la
    premiere permission. L autre test d interruption ne l exerce qu apres
    trois essais deja faits."""
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(1, 1))
    journal = []

    fin = balayer(balayage, essayeur({}, journal), CIBLE,
                  interrompu=lambda: True)

    assert fin == "interrompu"
    assert journal == []
    assert balayage.faits == 0
    assert len(balayage.restants()) == 9


def test_une_panne_d_affichage_traverse_mais_l_essai_reste_acquis():
    """C est l inverse exact du cas AncrageError, et c est cette difference
    qui justifie de ne pas proteger `dire` : l essai est deja note quand
    l affichage casse, donc la reprise ne le retapera pas."""
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(0, 1))

    def dire(balayage, resultat):
        raise RuntimeError("console cassee")

    with pytest.raises(RuntimeError):
        balayer(balayage, essayeur({}), CIBLE, dire=dire)

    assert balayage.faits == 1
    assert Couple(0, 0) not in balayage.restants()


def test_un_espace_entierement_impossible_se_termine_sans_rien_essayer():
    """Un `images` mal calcule peut rendre tous les couples impossibles. La
    boucle doit le dire en se terminant, et non en tapant."""
    journal = []
    dits = []
    veilles = []

    def interrompu():
        veilles.append(1)
        return False

    # Sauts a 100 et 200, run de 199 images : les trois decalages du saut
    # travaille tombent tous a 199 ou au-dela, donc hors du run.
    balayage = Balayage([100, 200], index=1, images=199, couples=espace(0, 1))

    fin = balayer(balayage, essayeur({}, journal), CIBLE,
                  dire=lambda b, r: dits.append(r), interrompu=interrompu)

    assert balayage.total == 0
    assert fin == "termine"
    assert journal == []
    assert dits == []
    assert veilles == []
