import io

from controller.cible import Cible
from controller.hud import (
    LARGEUR_LIGNE,
    aide,
    ecrire_en_place,
    ligne_balayage,
    ligne_cible,
    ligne_decalage,
    ligne_etat,
    ligne_issue,
    ligne_saut,
    ligne_sauts,
    lignes_podium,
)
from controller.solveur import Couple, Resultat
from controller.trace import Etat


ETAT = Etat(frame=142, x=786.5624, y=505.0718, vx=0.0, vy=-8.2102)


def test_la_ligne_d_etat_porte_l_image_la_position_et_le_mode():
    assert ligne_etat(142, ETAT, sauts=3, en_pause=True) == (
        "frame   142 | x=  786.5624 y=  505.0718 vx=  0.0000 vy= -8.2102 "
        "| 3 jump(s) | PAUSE"
    )


def test_la_ligne_d_etat_dit_le_turbo():
    ligne = ligne_etat(10, ETAT, sauts=0, en_pause=False, turbo=True)
    assert ligne.endswith("| 0 jump(s) | RUNNING+TURBO")


def test_sans_image_enregistree_la_ligne_le_dit_au_lieu_d_inventer():
    assert ligne_etat(0, None, sauts=0, en_pause=True) == (
        "frame     0 | no frame recorded | 0 jump(s) | PAUSE"
    )


def test_la_ligne_de_saut_montre_les_deux_images():
    assert ligne_saut(100, 102) == (
        "jump placed at frame 100 -> liftoff expected at frame 102"
    )


def test_la_ligne_d_issue_nomme_l_image_de_la_mort():
    assert ligne_issue("death", 128) == (
        "the hero disappeared at frame 128: the run stops there"
    )


def test_la_ligne_d_issue_d_un_run_qui_continue():
    assert ligne_issue("incomplete", None) == (
        "run incomplete: the hero is still there"
    )


def test_l_aide_liste_les_touches_de_l_editeur():
    texte = aide()
    for attendu in ("F1", "F2", "F3", "F5", "Space", "Tab", "Backspace", "n"):
        assert attendu in texte


def test_l_ecriture_en_place_revient_au_debut_et_efface_la_ligne_precedente():
    sortie = io.StringIO()

    ecrire_en_place("court", sortie)

    ecrit = sortie.getvalue()
    assert ecrit.startswith("\r")
    assert len(ecrit) == 1 + LARGEUR_LIGNE
    assert ecrit.strip() == "court"


def test_la_ligne_des_sauts_marque_celui_qu_on_travaille():
    assert ligne_sauts([66, 174, 211, 250, 284], 2) == (
        "jumps  66  174  [211]  250  284"
    )


def test_la_ligne_des_sauts_d_un_film_vide_dit_quoi_faire():
    assert ligne_sauts([], None) == (
        "jumps  none -- Space places one at the current frame"
    )


def test_la_ligne_de_decalage_montre_les_trois_nombres():
    """Les deux images du saut, et celle du decollage : aucune convention ne
    doit rester implicite."""
    assert ligne_decalage(3, 211, 212, 214) == (
        "jump 3: 211 -> 212 (liftoff expected at frame 214)"
    )


def test_la_ligne_de_cible_dit_le_sens_de_la_marche():
    assert ligne_cible(Cible("x", -1, 605.25, 300)) == (
        "target: x <= 605.2500 before frame 300"
    )
    assert ligne_cible(Cible("y", 1, 120.0, 40)) == (
        "target: y >= 120.0000 before frame 40"
    )


def test_la_ligne_de_balayage_porte_l_avancement_et_le_verdict():
    resultat = Resultat(Couple(-1, 2), progression=-452.25, reussi=True)

    assert ligne_balayage(17, 49, resultat, reussis=3) == (
        "sweep  17/ 49 | (-1,+2) |  -452.2500 | HIT | 3 hit(s)"
    )


def test_un_essai_rate_ne_porte_pas_la_marque():
    resultat = Resultat(Couple(0, 0), progression=-700.0, reussi=False)

    assert "HIT" not in ligne_balayage(1, 49, resultat, reussis=0)


def test_le_podium_numerote_et_marque_ceux_qui_atteignent_la_cible():
    resultats = [
        Resultat(Couple(0, 1), progression=-500.0, reussi=True),
        Resultat(Couple(0, 0), progression=-700.0, reussi=False),
    ]

    lignes = lignes_podium(resultats)

    assert lignes[0] == "podium:"
    assert lignes[1] == "  1. (+0,+1) progress -500.0000  <-- reaches the target"
    assert lignes[2] == "  2. (+0,+0) progress -700.0000"


def test_un_podium_vide_le_dit():
    assert lignes_podium([]) == ["no try measured"]


def test_l_aide_annonce_la_touche_du_balayage():
    assert "F4" in aide()
