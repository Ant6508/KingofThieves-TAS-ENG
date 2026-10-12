import pytest

from controller.frise import (
    MARGE_PX,
    Echelle,
    courbe,
    etendue,
    graduations,
    saut_proche,
)


def test_les_bornes_de_la_frise_tombent_sur_les_marges():
    e = Echelle(largeur=1000, images=100)
    assert e.x(0) == MARGE_PX
    assert e.x(100) == 1000 - MARGE_PX


def test_l_image_d_un_pixel_est_l_inverse_de_son_pixel():
    e = Echelle(largeur=812, images=131)
    for image in (0, 1, 65, 106, 131):
        assert e.image(e.x(image)) == image


def test_un_clic_hors_de_la_frise_est_ramene_a_ses_bornes():
    e = Echelle(largeur=500, images=50)
    assert e.image(-40) == 0
    assert e.image(10_000) == 50


def test_une_frise_sans_image_est_refusee():
    with pytest.raises(ValueError):
        Echelle(largeur=500, images=0)


def test_une_frise_trop_etroite_est_refusee():
    with pytest.raises(ValueError):
        Echelle(largeur=2 * MARGE_PX, images=10)


def test_l_etendue_couvre_la_longueur_la_trace_et_le_dernier_saut():
    assert etendue(longueur=131, images_tracees=80, sauts=[65]) == 131
    assert etendue(longueur=100, images_tracees=140, sauts=[]) == 140
    assert etendue(longueur=100, images_tracees=0, sauts=[150]) == 151
    assert etendue(longueur=0, images_tracees=0, sauts=[]) == 1


def test_un_clic_pres_d_un_saut_le_designe():
    e = Echelle(largeur=1000, images=100)
    assert saut_proche([30, 60], e.x(60) + 3, e) == 60


def test_un_clic_dans_le_vide_ne_designe_aucun_saut():
    e = Echelle(largeur=1000, images=100)
    assert saut_proche([30, 60], e.x(45), e) is None


def test_entre_deux_sauts_proches_le_clic_designe_le_plus_proche():
    e = Echelle(largeur=200, images=100)  # 1,76 px par image
    assert saut_proche([50, 52], e.x(52) - 1, e) == 52


def test_la_courbe_met_le_y_le_plus_petit_en_haut():
    e = Echelle(largeur=1000, images=3)
    points = courbe([548.0, 500.0, 548.0], e, hauteur=100)
    assert [round(x) for x, _ in points] == [round(e.x(k)) for k in range(3)]
    assert points[1][1] == MARGE_PX           # le heros au plus haut
    assert points[0][1] == 100 - MARGE_PX     # au repos, en bas


def test_une_courbe_plate_passe_au_milieu():
    e = Echelle(largeur=1000, images=2)
    assert [y for _, y in courbe([548.0, 548.0], e, hauteur=100)] == [50, 50]


def test_une_trace_vide_ne_donne_aucun_point():
    assert courbe([], Echelle(largeur=1000, images=1), hauteur=100) == []


def test_les_graduations_ont_un_pas_rond():
    assert graduations(131) == [0, 20, 40, 60, 80, 100, 120]
    assert graduations(5) == [0, 1, 2, 3, 4, 5]
    assert graduations(1000) == list(range(0, 1001, 200))
