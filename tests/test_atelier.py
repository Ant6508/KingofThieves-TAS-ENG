import pytest

from controller.atelier import BROUILLON, ESSAYE, Atelier, AtelierError
from tests.faux_agent import chute

DEPART = (786.5624, 500.0)
CYCLE = (16, 17, 17)


def essaye(sauts, images=120):
    """Un atelier dont la derniere trace joue exactement `sauts`."""
    a = Atelier()
    for s in sauts:
        a.poser(s)
    a.noter_trace(chute(images), sauts, DEPART, CYCLE)
    return a


def test_un_atelier_neuf_est_un_brouillon_sans_essai():
    a = Atelier()
    assert a.etat == BROUILLON
    assert a.raison == "no try since opening"
    assert a.empreinte is None


def test_une_trace_qui_joue_les_sauts_du_film_le_rend_essaye():
    a = essaye([50])
    assert a.etat == ESSAYE
    assert a.longueur == 120
    assert a.raison == "trace up to date: 120 frames since a relaunch"
    assert a.empreinte.startswith("sha256:")


def test_decaler_un_saut_repasse_en_brouillon_et_dit_lequel():
    a = essaye([50, 90])
    a.deplacer(90, 91)
    assert a.etat == BROUILLON
    assert a.raison == "jump 2 shifted (90 -> 91)"
    assert a.film.sauts == [50, 91]
    assert a.trace, "la trace perimee reste, pour la courbe en pointilles"


def test_retirer_un_saut_ne_touche_pas_aux_autres():
    a = essaye([50, 90, 110])
    a.retirer(90)
    assert a.film.sauts == [50, 110]
    assert a.etat == BROUILLON
    assert a.raison == "jump at frame 90 removed"


def test_les_fleches_decalent_le_saut_choisi():
    a = essaye([50, 90])
    a.choisir(50)
    a.decaler(-1)
    assert a.film.sauts == [49, 90]
    assert a.raison == "jump 1 shifted (50 -> 49)"


def test_poser_un_saut_repasse_en_brouillon():
    a = essaye([50])
    a.poser(100)
    assert a.etat == BROUILLON
    assert a.raison == "jump placed at frame 100"


def test_une_edition_impossible_est_refusee_avec_le_message_du_film():
    a = essaye([50, 90])
    with pytest.raises(AtelierError, match="already placed at frame 90"):
        a.deplacer(50, 90)
    with pytest.raises(AtelierError, match="no jump at frame 70"):
        a.retirer(70)


def test_decaler_sans_saut_est_refuse():
    with pytest.raises(AtelierError, match="the movie is empty"):
        Atelier().decaler(1)


def test_une_trace_plus_courte_que_le_run_laisse_en_brouillon():
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE)
    assert a.etat == BROUILLON
    assert a.longueur == 120
    assert a.raison == "trace stopped at frame 80 of 120"


def test_la_trace_prolongee_allonge_le_run():
    a = essaye([50])
    a.noter_trace(chute(150), [50], DEPART, CYCLE)
    assert a.longueur == 150
    assert a.etat == ESSAYE


def test_une_trace_a_jour_efface_la_raison_de_la_derniere_edition():
    a = essaye([50])
    a.deplacer(50, 51)
    a.noter_trace(chute(120), [51], DEPART, CYCLE)
    assert a.etat == ESSAYE
    a.noter_trace(chute(120), [50], DEPART, CYCLE)
    assert a.raison == "the jumps changed since the last try"


def test_un_saut_en_direct_attend_son_decollage_pour_etre_essaye():
    """Spec section 8 : le tap direct donne la meme trace que le rejeu. Mais
    juste apres Sauter ici la trace s'arrete a l'image du tap : son decollage
    (N + LATENCE_TAP_IMAGES) n'y est pas, et un film gele la ne rejouerait
    meme pas le saut -- derouler n'emet que les taps n < run_frames."""
    a = essaye([50], images=120)
    a.sauter_en_direct(120)
    a.noter_trace(chute(120), [50, 120], DEPART, CYCLE)
    assert a.film.sauts == [50, 120]
    assert a.film.choisi == 120
    assert a.etat == BROUILLON
    assert a.raison == ("jump at frame 120 not yet played to its "
                        "liftoff: advance to frame 124")
    assert a.actions(occupe=False, tete=120)["jusquau_bout"]
    a.noter_trace(chute(124), [50, 120], DEPART, CYCLE)
    assert a.etat == ESSAYE


def test_la_longueur_requise_couvre_le_decollage_du_dernier_saut():
    """Tap emis a N, recu au pas N + 2, dont l'effet est l'enregistrement
    N + 3 : il faut N + 4 enregistrements."""
    a = Atelier()
    assert a.longueur_requise == 0
    a.poser(50)
    assert a.longueur_requise == 54
    assert essaye([50], images=120).longueur_requise == 120


def test_un_film_neuf_n_est_essaye_qu_une_fois_le_decollage_joue():
    a = Atelier()
    a.poser(50)
    a.noter_trace(chute(53), [50], DEPART, CYCLE)
    assert a.etat == BROUILLON
    assert "not yet played to its liftoff" in a.raison
    a.noter_trace(chute(54), [50], DEPART, CYCLE)
    assert a.etat == ESSAYE


def test_une_trace_arretee_se_compte_sur_la_longueur_requise():
    a = essaye([50], images=120)
    a.sauter_en_direct(120)
    a.noter_trace(chute(120), [50, 120], DEPART, CYCLE)
    # Reprendre d'ici a l'image 80 : le saut 120 est conserve, pas rejoue.
    a.noter_trace(chute(80), [50], DEPART, CYCLE)
    assert a.raison == "trace stopped at frame 80 of 124"


def test_sauter_ici_puis_geler_est_refuse_tant_que_le_decollage_n_est_pas_joue():
    a = essaye([50], images=120)
    a.sauter_en_direct(120)
    a.noter_trace(chute(120), [50, 120], DEPART, CYCLE)
    with pytest.raises(AtelierError, match="not yet played"):
        a.geler("films/x.json", "win", ecrire=lambda m, c: None)


def test_geler_refuse_un_saut_que_le_rejeu_n_emettrait_pas(monkeypatch):
    """Garde de defense : derouler n'emet que les taps n < run_frames. Un tel
    saut ne peut pas passer l'etat Essaye ; on force la main pour le voir."""
    a = essaye([50], images=120)
    a.film.poser(125)
    a.joues = (50, 125)
    monkeypatch.setattr(Atelier, "longueur_requise", property(lambda s: 0))
    assert a.etat == ESSAYE
    with pytest.raises(AtelierError, match="125"):
        a.geler("films/x.json", "win", ecrire=lambda m, c: None)
    assert not a.gele


def test_un_saut_trop_pres_de_la_sortie_laisse_en_brouillon():
    a = Atelier()
    a.poser(78)
    a.noter_trace(chute(80), [78], DEPART, CYCLE, fin=80)
    assert a.etat == BROUILLON
    assert a.raison == ("jump at frame 78 too close to the level exit "
                        "(frame 80): its liftoff isn't in the trace")


def test_un_saut_en_direct_sur_un_saut_conserve_ne_le_double_pas():
    a = essaye([50, 100], images=120)
    a.sauter_en_direct(100)
    assert a.film.sauts == [50, 100]
    assert a.film.choisi == 100


def test_la_frontiere_du_turbo_precede_le_saut_choisi():
    a = Atelier()
    a.poser(50)
    a.poser(200)
    a.choisir(200)
    assert a.frontiere_turbo(300) == 170


def test_sans_saut_choisi_avant_la_fin_le_turbo_s_arrete_avant_la_fin():
    a = Atelier()
    assert a.frontiere_turbo(300) == 270
    a.poser(250)
    assert a.frontiere_turbo(100) == 70   # reprise a l'image 100


def test_pas_de_turbo_quand_tout_est_trop_pres_du_debut():
    a = Atelier()
    a.poser(20)
    assert a.frontiere_turbo(300) is None
    assert Atelier().frontiere_turbo(0) is None


from controller.atelier import (  # noqa: E402
    ACTIONS,
    GELE,
    chemin_libre,
    nom_suggere,
)
from controller.movie import (  # noqa: E402
    GameBuild,
    Movie,
    StartConditions,
    TapInput,
)


def film_gele(sauts=(50,), images=120, fingerprint="sha256:abc"):
    return Movie(
        game=GameBuild("com.zeptolab.thieves.google", "2.83", 4755263),
        dt=1 / 60, run_frames=images,
        start=StartConditions(hero_x=DEPART[0], hero_y=DEPART[1]),
        run_label="ma base",
        inputs=[TapInput(n) for n in sauts],
        outcome_status="win", fingerprint=fingerprint,
    )


def test_geler_ecrit_le_film_avec_l_empreinte_de_l_essai():
    a = essaye([50])
    ecrits = []
    movie = a.geler("films/x.json", "win", "ma base",
                    ecrire=lambda m, c: ecrits.append((m, c)))
    assert ecrits == [(movie, "films/x.json")]
    assert movie.fingerprint == essaye([50]).empreinte
    assert [i.frame for i in movie.inputs] == [50]
    assert movie.run_frames == 120
    assert (movie.start.hero_x, movie.start.hero_y) == DEPART
    assert movie.outcome_status == "win"
    assert movie.run_label == "ma base"
    assert a.etat == GELE
    assert a.chemin == "films/x.json"


def test_geler_compte_comme_premier_passage():
    """Le run qu'on vient de geler a ete joue depuis une relance : le deuxieme
    passage sans relance peut suivre aussitot."""
    a = essaye([50])
    a.geler("films/x.json", "win", ecrire=lambda m, c: None)
    assert a.passages == 1
    assert a.actions(occupe=False, tete=120)["rejouer_encore"]


def test_geler_sans_le_run_en_pause_ne_compte_pas_de_premier_passage():
    """Le run de l'essai n'est plus en pause (jeu rendu, perdu, interrompu) :
    le deuxieme passage sans relance ne suivrait pas une premiere reussite."""
    a = essaye([50])
    a.geler("films/x.json", "win", premier_passage=False,
            ecrire=lambda m, c: None)
    assert a.passages == 0
    assert not a.passage_reussi
    assert not a.actions(occupe=False, tete=None)["rejouer_encore"]
    assert a.actions(occupe=False, tete=None)["rejouer"]


def test_un_brouillon_ne_se_gele_pas():
    a = essaye([50])
    a.deplacer(50, 51)
    with pytest.raises(AtelierError, match="only a tried movie can be frozen"):
        a.geler("films/x.json", "win", ecrire=lambda m, c: None)


def test_une_issue_inconnue_est_refusee():
    with pytest.raises(AtelierError, match="unknown outcome"):
        essaye([50]).geler("films/x.json", "gagne", ecrire=lambda m, c: None)


def test_un_film_ouvert_est_gele_et_ne_se_modifie_pas():
    a = Atelier.depuis_film(film_gele([50, 90]), "films/ref.json")
    assert a.etat == GELE
    assert a.film.sauts == [50, 90]
    assert a.longueur == 120
    assert a.label == "ma base"
    with pytest.raises(AtelierError, match="unfreeze it"):
        a.poser(10)


def test_degeler_cree_une_copie_de_travail_sans_essai():
    a = Atelier.depuis_film(film_gele(), "films/ref.json")
    a.degeler()
    assert a.etat == BROUILLON
    assert a.source == "films/ref.json"
    assert a.chemin is None
    assert a.raison == "working copy of films/ref.json, no try yet"
    a.poser(10)


def test_un_premier_passage_conforme_ouvre_le_deuxieme():
    a = Atelier.depuis_film(film_gele(fingerprint="sha256:abc"), "f.json")
    assert not a.actions(occupe=False, tete=None)["rejouer_encore"]
    verdict = a.noter_passage(1, "sha256:abc")
    assert "identical" in verdict
    assert a.actions(occupe=False, tete=None)["rejouer_encore"]


def test_un_premier_passage_divergent_ferme_le_deuxieme():
    a = Atelier.depuis_film(film_gele(fingerprint="sha256:abc"), "f.json")
    verdict = a.noter_passage(1, "sha256:def")
    assert "MISMATCH" in verdict and "sha256:def" in verdict
    assert not a.actions(occupe=False, tete=None)["rejouer_encore"]


def test_le_deuxieme_passage_ne_compare_pas_d_empreinte():
    a = Atelier.depuis_film(film_gele(), "f.json")
    a.noter_passage(1, "sha256:abc")
    verdict = a.noter_passage(2, "sha256:zzz")
    assert "pass 2 finished" in verdict
    assert a.passages == 2
    assert a.actions(occupe=False, tete=None)["rejouer_encore"]


def test_un_film_sans_empreinte_laisse_faire_le_deuxieme_passage():
    a = Atelier.depuis_film(film_gele(fingerprint=None), "f.json")
    assert "nothing to compare" in a.noter_passage(1, "sha256:abc")
    assert a.passage_reussi


def test_pendant_une_operation_seul_interrompre_est_permis():
    permis = essaye([50]).actions(occupe=True, tete=120)
    assert [nom for nom, oui in permis.items() if oui] == ["interrompre"]
    assert set(permis) == set(ACTIONS)


def test_les_boutons_d_un_brouillon_neuf():
    permis = Atelier().actions(occupe=False, tete=None)
    assert permis["essayer"] and permis["ouvrir"] and permis["poser"]
    assert not permis["geler"] and not permis["avancer"]
    assert not permis["rejouer"] and not permis["reprendre"]


def test_les_boutons_d_un_essai_en_pause():
    permis = essaye([50]).actions(occupe=False, tete=120)
    assert permis["geler"] and permis["avancer"] and permis["sauter"]
    assert permis["reprendre"]
    assert not permis["jusquau_bout"]      # la tete est deja au bout
    assert not permis["rejouer"] and not permis["degeler"]


def test_apres_une_reprise_on_peut_jouer_jusqu_au_bout():
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE)
    assert a.actions(occupe=False, tete=80)["jusquau_bout"]


def test_les_boutons_d_un_film_gele():
    permis = Atelier.depuis_film(film_gele(), "f.json").actions(
        occupe=False, tete=None)
    assert permis["rejouer"] and permis["degeler"] and permis["ouvrir"]
    assert not permis["essayer"] and not permis["poser"]
    assert not permis["editer"] and not permis["geler"]


def test_une_copie_de_travail_touchee_est_a_perdre():
    assert not Atelier().a_perdre
    a = Atelier()
    a.poser(10)
    assert a.a_perdre
    assert not Atelier.depuis_film(film_gele(), "f.json").a_perdre


def test_le_nom_suggere_est_le_premier_vn_libre():
    existants = {"films/ref_v2.json"}
    assert nom_suggere("films/ref.json", existants.__contains__) == \
        "films/ref_v3.json"
    assert nom_suggere("films/ref_v3.json", existants.__contains__) == \
        "films/ref_v4.json"
    assert nom_suggere("films/run.json", lambda c: False) == "films/run_v2.json"


def test_un_chemin_libre_est_garde_tel_quel():
    assert chemin_libre("films/run.json", lambda c: False) == "films/run.json"
    assert chemin_libre("films/run.json", {"films/run.json"}.__contains__) == \
        "films/run_v2.json"


def test_un_heros_sorti_du_niveau_arrete_le_run_et_le_laisse_essaye():
    """Run.issue : disparu veut dire sorti du niveau, le run ne va pas plus
    loin. Attendre 120 images qui ne viendront jamais laisserait le film en
    brouillon pour toujours."""
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE, fin=80)
    assert a.etat == ESSAYE
    assert a.longueur == 80
    assert a.raison == ("trace up to date: hero exited the level at frame 80, "
                        "since a relaunch")


def test_un_saut_pose_apres_la_sortie_repasse_en_brouillon():
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE, fin=80)
    a.poser(100)
    assert a.etat == BROUILLON


def test_une_trace_sans_sortie_oublie_la_sortie_precedente():
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE, fin=80)
    a.noter_trace(chute(120), [50], DEPART, CYCLE)
    assert a.sortie is None
    assert a.raison == "trace up to date: 120 frames since a relaunch"


def test_degeler_oublie_la_sortie_du_niveau():
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE, fin=80)
    a.geler("films/x.json", "win", ecrire=lambda m, c: None)
    a.degeler()
    assert a.sortie is None


def test_un_saut_a_l_image_0_est_refuse():
    """verifier_depart consomme l'image 0 avant derouler : un tap pose la ne
    partirait jamais, et le film mentirait sur ce qu'il joue."""
    a = Atelier()
    with pytest.raises(AtelierError, match="frame 1 at the earliest"):
        a.poser(0)
    assert a.film.sauts == []


def test_decaler_un_saut_vers_l_image_0_est_refuse():
    a = Atelier()
    a.poser(1)
    with pytest.raises(AtelierError, match="frame 1 at the earliest"):
        a.decaler(-1)
    with pytest.raises(AtelierError, match="frame 1 at the earliest"):
        a.deplacer(1, 0)
    assert a.film.sauts == [1]


def test_apres_la_sortie_du_niveau_on_ne_prolonge_plus_le_run():
    """Le heros n'est plus lisible : +1 et Sauter ici leveraient une RunError,
    et le pilote rendrait le jeu, tuant le run qu'on peut encore geler."""
    a = essaye([50])
    a.noter_trace(chute(80), [50], DEPART, CYCLE, fin=80)
    permis = a.actions(occupe=False, tete=80)
    assert not permis["avancer"] and not permis["sauter"]
    assert not permis["jusquau_bout"]
    assert permis["geler"] and permis["essayer"]


# ----- points d'arret -----

def test_sans_arret_la_borne_est_la_cible():
    assert Atelier().borne(0, 120) == 120


def test_la_borne_est_le_premier_arret_sur_le_chemin():
    a = Atelier()
    for n in (30, 80, 10):
        a.poser_arret(n)
    assert a.borne(0, 120) == 10
    assert a.borne(10, 120) == 30, "on repart d'un arret sans s'y rebloquer"
    assert a.borne(30, 120) == 80
    assert a.borne(80, 120) == 120


def test_un_arret_au_bout_ou_au_dela_ne_change_pas_la_borne():
    a = Atelier()
    a.poser_arret(120)
    a.poser_arret(200)
    assert a.borne(0, 120) == 120


def test_un_arret_a_l_image_0_est_refuse():
    with pytest.raises(AtelierError, match="frame 0"):
        Atelier().poser_arret(0)


def test_un_arret_en_double_est_refuse():
    a = Atelier()
    a.poser_arret(30)
    with pytest.raises(AtelierError, match="already placed at frame 30"):
        a.poser_arret(30)


def test_retirer_un_arret_absent_est_refuse():
    with pytest.raises(AtelierError, match="no breakpoint at frame 30"):
        Atelier().retirer_arret(30)


def test_un_arret_ne_change_ni_l_etat_ni_l_empreinte():
    a = essaye([50])
    avant = (a.etat, a.empreinte, a.raison)
    a.poser_arret(30)
    assert (a.etat, a.empreinte, a.raison) == avant
    a.retirer_arret(30)
    assert a.arrets == set()


def test_un_film_gele_ne_prend_pas_d_arret():
    a = Atelier.depuis_film(film_gele(), "f.json")
    with pytest.raises(AtelierError, match="unfreeze it"):
        a.poser_arret(30)
    assert not a.actions(occupe=False, tete=None)["arret"]


def test_degeler_garde_les_arrets_de_la_seance():
    a = essaye([50])
    a.poser_arret(30)
    a.geler("films/x.json", "win", ecrire=lambda m, c: None)
    a.degeler()
    assert a.arrets == {30}


def test_poser_un_arret_est_permis_hors_gel_et_hors_operation():
    assert Atelier().actions(occupe=False, tete=None)["arret"]
    assert not Atelier().actions(occupe=True, tete=None)["arret"]
