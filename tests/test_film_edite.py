import pytest

from controller.film_edite import (
    MARGE_TURBO_IMAGES,
    EditionError,
    FilmEdite,
)


def film(*sauts):
    return FilmEdite(sauts)


def test_un_film_neuf_choisit_son_premier_saut():
    f = film(66, 174, 211)

    assert f.sauts == [66, 174, 211]
    assert f.choisi == 66


def test_un_film_vide_ne_choisit_rien():
    f = film()

    assert f.sauts == []
    assert f.choisi is None


def test_les_sauts_sont_ordonnes_quoi_qu_on_lui_donne():
    assert film(211, 66, 174).sauts == [66, 174, 211]


def test_refus_de_deux_sauts_a_la_meme_image():
    with pytest.raises(EditionError):
        film(66, 66)


def test_refus_d_une_image_negative():
    with pytest.raises(EditionError):
        film(-1)


def test_poser_un_saut_le_choisit():
    f = film(66, 250)

    f.poser(174)

    assert f.sauts == [66, 174, 250]
    assert f.choisi == 174


def test_poser_sur_une_image_occupee_est_refuse():
    f = film(66)

    with pytest.raises(EditionError) as excinfo:
        f.poser(66)

    assert "66" in str(excinfo.value)


def test_retirer_rend_le_saut_et_garde_un_curseur_valide():
    f = film(66, 174, 211)
    f.suivant()
    f.suivant()          # curseur sur 211, le dernier

    assert f.retirer() == 211
    assert f.sauts == [66, 174]
    assert f.choisi == 174


def test_retirer_le_dernier_saut_laisse_un_film_vide():
    f = film(66)

    assert f.retirer() == 66
    assert f.sauts == []
    assert f.choisi is None


def test_retirer_sur_un_film_vide_ne_casse_pas():
    f = film()

    assert f.retirer() is None


def test_decaler_deplace_le_saut_choisi_et_le_garde_choisi():
    f = film(66, 174, 211)
    f.suivant()          # curseur sur 174

    assert f.decaler(+1) == 175
    assert f.sauts == [66, 175, 211]
    assert f.choisi == 175


def test_decaler_vers_l_arriere():
    f = film(66, 174)
    f.suivant()

    assert f.decaler(-4) == 170
    assert f.sauts == [66, 170]


def test_un_decalage_qui_franchit_un_voisin_reordonne_la_liste():
    """Rien n'interdit de faire passer un saut devant un autre : la liste se
    reordonne, et le curseur suit le saut deplace, pas sa position."""
    f = film(100, 200)
    f.suivant()          # curseur sur 200

    f.decaler(-150)

    assert f.sauts == [50, 100]
    assert f.choisi == 50


def test_un_decalage_qui_superpose_deux_sauts_est_refuse():
    f = film(100, 101)

    with pytest.raises(EditionError) as excinfo:
        f.decaler(+1)    # 100 tomberait sur 101

    assert "101" in str(excinfo.value)
    assert f.sauts == [100, 101]   # rien n'a bouge


def test_un_decalage_avant_l_image_zero_est_refuse():
    f = film(3)

    with pytest.raises(EditionError):
        f.decaler(-4)

    assert f.sauts == [3]


def test_decaler_un_film_vide_est_refuse():
    with pytest.raises(EditionError):
        film().decaler(+1)


def test_le_curseur_se_deplace_et_ne_deborde_pas():
    f = film(66, 174, 211)

    assert f.precedent() == 66      # deja au debut
    assert f.suivant() == 174
    assert f.suivant() == 211
    assert f.suivant() == 211       # deja a la fin
    assert f.precedent() == 174


def test_le_curseur_d_un_film_vide_reste_vide():
    f = film()

    assert f.suivant() is None
    assert f.precedent() is None


def test_la_frontiere_du_turbo_precede_le_saut_travaille():
    f = film(66, 400)
    f.suivant()          # curseur sur 400

    assert f.frontiere_turbo() == 400 - MARGE_TURBO_IMAGES


def test_pas_de_turbo_quand_le_saut_est_trop_proche_du_debut():
    """Rien a gagner a passer en turbo pour vingt images, et le saut serait
    passe avant qu'on ait le temps de le voir."""
    f = film(20)

    assert f.frontiere_turbo() is None


def test_pas_de_turbo_sur_un_film_vide():
    assert film().frontiere_turbo() is None


def test_la_marge_du_turbo_est_reglable():
    f = film(400)

    assert f.frontiere_turbo(marge=100) == 300


def test_choisir_designe_le_saut_pose_a_cette_image():
    f = film(66, 174, 211)

    assert f.choisir(211) == 211
    assert f.choisi == 211
    assert f.index == 2


def test_choisir_une_image_sans_saut_est_refuse():
    f = film(66, 174)

    with pytest.raises(EditionError):
        f.choisir(100)
