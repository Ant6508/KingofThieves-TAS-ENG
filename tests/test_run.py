import pytest

from controller.run import (
    LATENCE_TAP_IMAGES,
    AncrageError,
    Run,
    RunError,
    derouler,
)
from tests.faux_agent import FauxApi, chute


def fabrique(images=20, mort_a=None, objets=1):
    """Rend (run, api, taps) : un run pret a derouler, et la liste des taps."""
    api = FauxApi(chute(images), mort_a=mort_a, objets=objets)
    taps = []
    run = Run(api, taper=lambda: taps.append("tap"), dormir=lambda s: None)
    return run, api, taps


def test_l_ancrage_ferme_la_barriere_avant_de_resoudre_le_heros():
    """L'ordre supprime une source de variance : la resolution coute 0,7 s de
    temps reel, et zero image de jeu si le thread GL est deja gare."""
    run, api, _ = fabrique()

    run.ancrer()

    assert api.appels.index("pause") < api.appels.index("probe_resolve")


def test_l_ancrage_impose_l_horloge_avant_de_demarrer_l_enregistrement():
    run, api, _ = fabrique()

    run.ancrer()

    assert api.appels.index(("horloge", True)) < api.appels.index("record_start")


def test_l_ancrage_emet_le_tap_de_demarrage():
    run, _, taps = fabrique()

    run.ancrer()

    assert taps == ["tap"]
    assert run.entrees == []   # le tap de demarrage n'est pas un saut


def test_l_ancrage_refuse_de_continuer_sans_un_heros_unique():
    run, _, _ = fabrique(objets=2)

    with pytest.raises(AncrageError) as excinfo:
        run.ancrer()

    assert "found 2" in str(excinfo.value)


def test_avancer_rend_les_images_demandees():
    run, _, _ = fabrique(images=20)
    run.ancrer()

    nouveaux = run.avancer(5)

    assert len(nouveaux) == 5
    assert run.image == 5
    assert len(run.trace) == 5


def test_l_image_courante_est_le_nombre_d_images_enregistrees():
    run, _, _ = fabrique(images=20)
    run.ancrer()
    run.avancer(3)
    run.avancer(4)

    assert run.image == 7


def test_sauter_date_l_entree_a_l_image_courante():
    run, _, taps = fabrique(images=20)
    run.ancrer()
    run.avancer(10)

    image = run.sauter()

    assert image == 10
    assert run.entrees == [10]
    assert len(taps) == 2          # le demarrage, puis ce saut
    assert run.decollage(image) == 10 + LATENCE_TAP_IMAGES


def test_la_disparition_du_heros_arrete_le_run_et_donne_son_image():
    """Disparaitre n'est pas mourir : mesure du 2026-09-18, un heros tue par
    un piege reste lisible en memoire. L'outil ne sait dire que "plus rien a
    enregistrer"."""
    run, _, _ = fabrique(images=20, mort_a=8)
    run.ancrer()

    run.avancer(20)

    assert run.mort_a == 8
    assert run.issue() == ("disparu", 8)
    assert len(run.trace) == 8


def test_on_ne_fait_pas_sauter_un_heros_qui_n_est_plus_lisible():
    run, _, _ = fabrique(images=20, mort_a=3)
    run.ancrer()
    run.avancer(10)

    with pytest.raises(RunError):
        run.sauter()


def test_un_run_qui_survit_est_incomplet_et_non_victorieux():
    """Le jeu ne signale ni la victoire ni la mort : les deviner serait un
    mensonge, et c'est l'operateur qui qualifie son run."""
    run, _, _ = fabrique(images=20)
    run.ancrer()
    run.avancer(20)

    assert run.issue() == ("incomplete", None)


def test_terminer_rend_le_jeu_meme_si_l_enregistrement_echoue():
    run, api, _ = fabrique()
    run.ancrer()

    run.terminer()

    assert api.appels[-1] == "resume"
    assert api.horloge_active is False


def test_derouler_tape_aux_images_du_film():
    run, _, taps = fabrique(images=30)
    run.ancrer()

    trace = derouler(run, [5, 12], images=30)

    assert run.entrees == [5, 12]
    assert len(taps) == 3          # demarrage + deux sauts
    assert len(trace) == 30


def test_derouler_ignore_les_entrees_au_dela_de_la_longueur_du_run():
    run, _, _ = fabrique(images=10)
    run.ancrer()

    derouler(run, [5, 99], images=10)

    assert run.entrees == [5]


def test_derouler_s_arrete_quand_le_heros_disparait_sans_taper_dans_le_vide():
    run, _, taps = fabrique(images=30, mort_a=7)
    run.ancrer()

    trace = derouler(run, [3, 20], images=30)

    assert run.entrees == [3]
    assert len(taps) == 2
    assert len(trace) == 7
    assert run.issue() == ("disparu", 7)


def test_terminer_coupe_le_turbo():
    """Un run rate ne doit pas laisser le jeu sans synchronisation verticale :
    l'operateur reprendrait la main sur une fenetre figee."""
    run, api, _ = fabrique()
    run.ancrer()
    api.turbo(True)

    run.terminer()

    assert api.turbo_actif is False


def test_figer_draine_ce_qui_a_ete_enregistre_en_marche_libre():
    """En marche libre, l'agent continue d'enregistrer sans qu'on l'ait
    demande image par image. Figer doit ramasser ce qui s'est passe, sinon
    le HUD afficherait une position vieille de plusieurs secondes."""
    run, api, _ = fabrique(images=30)
    run.ancrer()
    run.relacher()
    api.step(12)          # le jeu a tourne tout seul

    nouveaux = run.figer()

    assert len(nouveaux) == 12
    assert run.image == 12
    assert api.en_pause is True


def test_relacher_rend_la_main_au_jeu():
    run, api, _ = fabrique()
    run.ancrer()

    run.relacher()

    assert api.en_pause is False


def test_le_pilotage_du_turbo_passe_par_l_agent():
    run, api, _ = fabrique()

    assert run.turbo(True) is True
    assert api.turbo_actif is True


def test_le_controle_de_l_image_zero_passe_quand_le_heros_est_au_depart():
    run, _, _ = fabrique(images=20)
    run.ancrer()
    premiere = chute(1)[0]

    etat = run.verifier_depart(premiere.x, premiere.y)

    assert etat.x == premiere.x
    assert run.image == 1


def test_le_controle_de_l_image_zero_arrete_l_essai_ailleurs():
    """Rien ne distingue l'ecran de commencement du menu principal, sauf
    ceci : deux runs comparables portent la meme position a l'image 0. Un
    essai lance ailleurs a deja deroule 244 images sans un seul mouvement
    avant qu'on s'en apercoive."""
    run, _, _ = fabrique(images=20)
    run.ancrer()

    with pytest.raises(AncrageError) as excinfo:
        run.verifier_depart(96.0, 548.0)

    assert "96" in str(excinfo.value)


def test_sans_cible_le_controle_se_contente_de_relever():
    """Premier essai d'une boucle : personne ne sait encore quelle position
    attendre."""
    run, _, _ = fabrique(images=20)
    run.ancrer()

    etat = run.verifier_depart()

    assert etat.x == chute(1)[0].x
    assert run.image == 1


def test_derouler_reprend_la_ou_le_run_en_est():
    """Le controle de l'image 0 a deja consomme une image : le deroule doit
    partir de la, pas de zero."""
    run, _, _ = fabrique(images=30)
    run.ancrer()
    run.avancer(5)

    derouler(run, [10], images=20)

    assert run.entrees == [10]
    assert len(run.trace) == 20


def test_derouler_coupe_le_turbo_avant_le_saut_travaille():
    run, api, _ = fabrique(images=60)
    run.ancrer()

    derouler(run, [50], images=60, frontiere_turbo=20)

    assert api.appels.index(("turbo", True)) < api.appels.index(("turbo", False))


def test_sans_frontiere_le_turbo_ne_s_allume_pas():
    run, api, _ = fabrique(images=30)
    run.ancrer()

    derouler(run, [10], images=30)

    assert ("turbo", True) not in api.appels


def test_pas_de_turbo_pour_une_frontiere_deja_depassee():
    """Allumer le turbo sans jamais l'eteindre laisserait la fenetre figee
    jusqu'a la fin du run."""
    run, api, _ = fabrique(images=30)
    run.ancrer()
    run.avancer(15)

    derouler(run, [20], images=30, frontiere_turbo=10)

    assert ("turbo", True) not in api.appels


def test_l_attente_du_repos_rend_la_main_quand_la_position_se_fige():
    """Trois releves identiques d'affilee : le niveau a fini de se remettre en
    place, on peut reancrer."""
    api = FauxApi(chute(5))
    api.positions_rendues = [(10.0, 20.0), (11.0, 20.0),
                             (12.0, 20.0), (12.0, 20.0), (12.0, 20.0)]
    run = Run(api, taper=lambda: None, dormir=lambda s: None)

    assert run.attendre_repos(stable=3) == (12.0, 20.0)


def test_l_attente_du_repos_abandonne_si_le_heros_ne_s_arrete_jamais():
    api = FauxApi(chute(5))
    run = Run(api, taper=lambda: None, dormir=lambda s: None)

    with pytest.raises(RunError):
        run.attendre_repos(stable=3, maximum=0.0)
