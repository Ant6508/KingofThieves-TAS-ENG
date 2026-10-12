import threading

import pytest

from controller.pilote import TRANCHE_IMAGES, Interrompu, RunPilote
from tests.faux_agent import FauxApi, chute


def run_pilote(api, interruption=None, vues=None):
    return RunPilote(
        api,
        interruption or threading.Event(),
        (vues if vues is not None else []).append,
        taper=lambda: None,
        dormir=lambda s: None,
    )


def test_une_longue_avance_se_decoupe_en_tranches():
    api = FauxApi(chute(400))
    vues = []
    run = run_pilote(api, vues=vues)
    run.ancrer()
    run.avancer(2 * TRANCHE_IMAGES + 30)
    pas = [a for a in api.appels if isinstance(a, tuple) and a[0] == "step"]
    assert pas == [("step", TRANCHE_IMAGES), ("step", TRANCHE_IMAGES),
                   ("step", 30)]
    assert run.image == 2 * TRANCHE_IMAGES + 30
    assert vues == [TRANCHE_IMAGES, 2 * TRANCHE_IMAGES,
                    2 * TRANCHE_IMAGES + 30]


def test_une_interruption_est_prise_avant_la_tranche_suivante():
    api = FauxApi(chute(400))
    interruption = threading.Event()
    vues = []
    run = run_pilote(api, interruption, vues)
    run.ancrer()
    run._progression = lambda image: (vues.append(image), interruption.set())
    with pytest.raises(Interrompu):
        run.avancer(3 * TRANCHE_IMAGES)
    assert run.image == TRANCHE_IMAGES
    assert vues == [TRANCHE_IMAGES]


def test_un_heros_disparu_arrete_l_avance_sans_erreur():
    api = FauxApi(chute(400), mort_a=70)
    run = run_pilote(api)
    run.ancrer()
    run.avancer(200)
    assert run.image == 70
    assert run.mort_a == 70


import queue  # noqa: E402
import time  # noqa: E402

from controller.device import DeviceError  # noqa: E402
from controller.pilote import Pilote  # noqa: E402
from controller.session import SessionError  # noqa: E402

DEPART = (786.5624, 500.0)


def faux_jeu(images=400, depart=DEPART):
    """Un jeu fraichement relance : sa trajectoire repart de zero."""
    api = FauxApi(chute(images))
    api.positions_rendues = [depart]
    return api


class FauxSession:
    """Une session dont chaque attache rend un jeu neuf, comme une relance."""

    def __init__(self, fabrique=faux_jeu):
        self.fabrique = fabrique
        self._api = None
        self.attaches = 0

    @property
    def api(self):
        if self._api is None:
            raise SessionError("session non attachee")
        return self._api

    def attacher_avec_reessais(self):
        self._api = self.fabrique()
        self.attaches += 1

    def detach(self):
        self._api = None


def pilote(session=None, relance=None):
    return Pilote(session or FauxSession(),
                  relance=relance or (lambda: None),
                  taper=lambda: None, dormir=lambda s: None)


def jusqua(p, genre, delai=5.0):
    """Lit la file jusqu'a un evenement `genre`, et rend tout ce qui a ete lu."""
    vus = []
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        try:
            ev = p.evenements.get(timeout=0.05)
        except queue.Empty:
            continue
        vus.append(ev)
        if ev.genre == genre:
            return vus
    raise AssertionError(f"pas d'evenement {genre} : {[e.genre for e in vus]}")


def reste(p):
    p.attendre(5)
    vus = []
    while True:
        try:
            vus.append(p.evenements.get_nowait())
        except queue.Empty:
            return vus


def naviguer(p):
    jusqua(p, "navigation")
    p.confirmer()


def test_un_essai_relance_attend_la_navigation_puis_deroule():
    relances = []
    p = pilote(relance=lambda: relances.append(1))
    p.essayer([50], 120, None, None)
    naviguer(p)
    vus = reste(p)
    trace = [e for e in vus if e.genre == "trace"][-1]
    assert relances == [1]
    assert len(trace.trace) == 120
    assert trace.entrees == (50,)
    assert trace.image == 120
    assert trace.depart == DEPART
    assert trace.cycle == (16, 17, 17)
    assert vus[-1].genre == "libre"
    assert p.tete == 120, "le jeu reste en pause au bout de l'essai"


def test_le_turbo_s_allume_puis_se_coupe_a_la_frontiere():
    session = FauxSession()
    p = pilote(session)
    p.essayer([90], 120, 60, None)
    naviguer(p)
    reste(p)
    turbos = [a for a in session.api.appels
              if isinstance(a, tuple) and a[0] == "turbo"]
    assert turbos == [("turbo", True), ("turbo", False)]


def test_un_second_essai_rend_d_abord_le_premier_run():
    session = FauxSession()
    p = pilote(session)
    p.essayer([], 50, None, None)
    naviguer(p)
    reste(p)
    premier = session.api
    p.essayer([], 50, None, None)
    naviguer(p)
    reste(p)
    assert "resume" in premier.appels, "l'ancien run a ete termine"
    assert session.attaches == 2


def test_une_mauvaise_navigation_se_rattrape_sans_relancer():
    """Une DepartError ne coute rien : aucun tap n'est parti."""
    relances = []
    session = FauxSession()
    p = pilote(session, relance=lambda: relances.append(1))
    p.essayer([], 50, None, None)
    jusqua(p, "navigation")
    session.api.objets = 2
    p.confirmer()
    jusqua(p, "navigation")
    session.api.objets = 1
    p.confirmer()
    vus = reste(p)
    assert relances == [1]
    assert any(e.genre == "trace" for e in vus)


def test_un_ancrage_rate_rend_le_jeu_et_le_dit():
    session = FauxSession(lambda: faux_jeu(depart=(96.0, 548.0)))
    p = pilote(session)
    p.essayer([50], 120, None, None)
    naviguer(p)
    vus = reste(p)
    erreur = [e for e in vus if e.genre == "erreur"][-1]
    assert "expected at (96.0, 548.0)" in erreur.texte
    assert not erreur.perdu
    assert p.tete is None
    assert session.api.appels[-1] == "resume"


def test_un_adb_mort_est_un_jeu_perdu():
    def relance():
        raise DeviceError("device offline")

    p = pilote(relance=relance)
    p.essayer([50], 120, None, None)
    vus = reste(p)
    erreur = [e for e in vus if e.genre == "erreur"][-1]
    assert erreur.perdu
    assert "device offline" in erreur.texte


def test_interrompre_pendant_la_navigation_ne_laisse_aucun_run():
    p = pilote()
    p.essayer([50], 120, None, None)
    jusqua(p, "navigation")
    p.interrompre()
    vus = reste(p)
    assert any(e.genre == "message" and "interrupted" in e.texte for e in vus)
    assert p.tete is None
    assert vus[-1].genre == "libre"


def test_une_seule_operation_a_la_fois():
    p = pilote()
    p.essayer([50], 120, None, None)
    jusqua(p, "navigation")
    with pytest.raises(RuntimeError, match="already in progress"):
        p.essayer([50], 120, None, None)
    p.interrompre()
    reste(p)


def essai_en_pause(sauts, images):
    p = pilote()
    p.essayer(sauts, images, None, None)
    naviguer(p)
    reste(p)
    return p


def derniere_trace(vus):
    return [e for e in vus if e.genre == "trace"][-1]


def test_avancer_prolonge_le_run_et_rejoue_les_sauts_conserves():
    """Reprendre d'ici a 100 : le saut de 150 reste au film, et part quand
    l'avance passe dessus."""
    p = essai_en_pause([50, 150], 100)
    assert p.run.entrees == [50]
    p.avancer([50, 150], 200)
    trace = derniere_trace(reste(p))
    assert trace.entrees == (50, 150)
    assert len(trace.trace) == 200
    assert trace.image == 200


def test_sauter_ici_emet_un_tap_a_l_image_courante():
    p = essai_en_pause([50], 100)
    p.sauter()
    trace = derniere_trace(reste(p))
    assert trace.saut == 100
    assert trace.entrees == (50, 100)


def test_sauter_deux_fois_a_la_meme_image_n_emet_qu_un_tap():
    p = essai_en_pause([50], 100)
    p.sauter()
    reste(p)
    p.sauter()
    vus = reste(p)
    assert any(e.genre == "message" and "already fired" in e.texte for e in vus)
    assert p.run.entrees == [50, 100]


def test_un_saut_deja_emis_n_est_pas_rejoue_par_l_avance():
    p = essai_en_pause([50], 100)
    p.sauter()
    reste(p)
    p.avancer([50, 100], 130)
    assert derniere_trace(reste(p)).entrees == (50, 100)


def test_avancer_sans_run_est_refuse_proprement():
    p = pilote()
    p.avancer([50], 10)
    erreur = [e for e in reste(p) if e.genre == "erreur"][-1]
    assert "Try first" in erreur.texte


from controller.movie import (  # noqa: E402
    GameBuild,
    Movie,
    StartConditions,
    TapInput,
)
from controller.trace import empreinte, encode  # noqa: E402


def film(sauts=(50,), images=120, cycle=(16, 17, 17)):
    return Movie(
        game=GameBuild("com.zeptolab.thieves.google", "2.83", 4755263),
        dt=1 / 60, run_frames=images,
        start=StartConditions(hero_x=DEPART[0], hero_y=DEPART[1]),
        clock_cycle_ms=cycle, inputs=[TapInput(n) for n in sauts],
        outcome_status="win",
    )


def passages(vus):
    return [e for e in vus if e.genre == "passage"]


def test_le_premier_passage_relance_et_rend_l_empreinte():
    relances = []
    p = pilote(relance=lambda: relances.append(1))
    p.rejouer(film())
    naviguer(p)
    (passage,) = passages(reste(p))
    assert relances == [1]
    assert passage.numero == 1
    assert passage.empreinte.startswith("sha256:")
    assert p.tete is None, "le jeu est rendu a l'operateur"


def test_deux_premiers_passages_donnent_la_meme_empreinte():
    p = pilote()
    p.rejouer(film())
    naviguer(p)
    (a,) = passages(reste(p))
    p.rejouer(film())
    naviguer(p)
    (b,) = passages(reste(p))
    assert a.empreinte == b.empreinte


def test_le_premier_passage_d_un_essai_vaut_l_empreinte_de_l_essai():
    """Un film gele sur un essai se rejoue a l'identique."""
    p = essai_en_pause([50], 120)
    essai = p.run.trace
    p.rejouer(film([50], 120))
    naviguer(p)
    (passage,) = passages(reste(p))
    assert passage.empreinte == empreinte(encode(essai))


def test_le_deuxieme_passage_ne_relance_pas():
    relances = []
    session = FauxSession()
    p = pilote(session, relance=lambda: relances.append(1))
    p.rejouer(film())
    naviguer(p)
    reste(p)
    p.rejouer_encore(film(), 2)
    naviguer(p)
    (passage,) = passages(reste(p))
    assert relances == [1]
    assert session.attaches == 1
    assert passage.numero == 2


def test_un_film_d_un_autre_cycle_est_refuse_avant_la_navigation():
    p = pilote()
    p.rejouer(film(cycle=(16, 16, 16)))
    vus = reste(p)
    assert not any(e.genre == "navigation" for e in vus)
    assert "clock cycle" in [e for e in vus if e.genre == "erreur"][-1].texte


def test_fermer_rend_le_jeu_et_detache():
    session = FauxSession()
    p = pilote(session)
    p.essayer([50], 100, None, None)
    naviguer(p)
    reste(p)
    api = session.api
    p.fermer()
    assert api.appels[-1] == "resume"
    assert p.tete is None
    with pytest.raises(SessionError):
        session.api


def jeu_qui_sort(mort_a=40):
    """Un jeu ou le heros sort du niveau a l'image `mort_a`."""
    def fabrique():
        api = FauxApi(chute(400), mort_a=mort_a)
        api.positions_rendues = [DEPART]
        return api
    return fabrique


def test_le_turbo_se_coupe_meme_si_le_heros_sort_avant_la_frontiere():
    """derouler rend la main des la disparition, turbo encore allume."""
    session = FauxSession(jeu_qui_sort(40))
    p = pilote(session)
    p.essayer([90], 120, 60, None)
    naviguer(p)
    reste(p)
    assert session.api.turbo_actif is False


def test_la_trace_dit_ou_le_heros_est_sorti_du_niveau():
    session = FauxSession(jeu_qui_sort(40))
    p = pilote(session)
    p.essayer([90], 120, None, None)
    naviguer(p)
    assert derniere_trace(reste(p)).fin == 40


def test_la_trace_d_un_heros_encore_la_ne_porte_pas_de_fin():
    p = essai_en_pause([50], 100)
    p.avancer([50], 120)
    assert derniere_trace(reste(p)).fin is None


def test_une_perte_en_cours_de_run_rend_quand_meme_le_jeu():
    """adb tombe au saut de l'image 50 : le jeu, lui, est peut-etre encore
    la, fige dans la barriere. On essaie de le rendre."""
    session = FauxSession()
    taps = []
    au_moment = []

    def taper():
        taps.append(1)
        if len(taps) == 2:   # le 1er est le tap de demarrage
            au_moment.append(len(session.api.appels))
            raise DeviceError("device offline")

    p = Pilote(session, relance=lambda: None, taper=taper,
               dormir=lambda s: None)
    p.essayer([50], 120, None, None)
    naviguer(p)
    vus = reste(p)
    erreur = [e for e in vus if e.genre == "erreur"][-1]
    assert erreur.perdu
    assert "resume" in session.api.appels[au_moment[0]:]
    assert p.tete is None


def test_interrompre_pendant_la_relance_n_attache_pas():
    """Fermer la fenetre pendant une relance : pas la peine d'attendre
    l'attache, ni de demander une navigation."""
    session = FauxSession()
    p = pilote(session, relance=lambda: p.interrompre())
    p.essayer([50], 120, None, None)
    vus = reste(p)
    assert session.attaches == 0
    assert not any(e.genre == "navigation" for e in vus)
    assert any(e.genre == "message" and "interrupted" in e.texte for e in vus)
    assert vus[-1].genre == "libre"


def test_interrompre_pendant_l_attache_ne_demande_pas_de_navigation():
    class SessionInterrompue(FauxSession):
        def attacher_avec_reessais(self):
            super().attacher_avec_reessais()
            p.interrompre()

    session = SessionInterrompue()
    p = pilote(session)
    p.essayer([50], 120, None, None)
    vus = reste(p)
    assert session.attaches == 1
    assert not any(e.genre == "navigation" for e in vus)
    assert any(e.genre == "message" and "interrupted" in e.texte for e in vus)


class FileLente(queue.Queue):
    """Une file dont l'emission de `libre` s'attarde : le thread du pilote
    est encore vivant quand la fenetre lit l'evenement."""

    def put(self, item, block=True, timeout=None):
        super().put(item, block, timeout)
        if item.genre == "libre":
            time.sleep(0.3)


def test_des_libre_recu_le_pilote_accepte_une_nouvelle_commande():
    p = Pilote(FauxSession(), evenements=FileLente(), relance=lambda: None,
               taper=lambda: None, dormir=lambda s: None)
    p.avancer([], 10)          # refusee aussitot : aucun run en cours
    jusqua(p, "libre")
    assert p.occupe is False
    p.avancer([], 10)          # ne leve pas RuntimeError
    reste(p)


def test_interrompre_avant_la_premiere_image_rend_le_jeu_sans_trace():
    """Le tap de demarrage est parti, aucune image n'est relevee : une trace
    vide ecraserait la courbe de l'essai precedent."""
    session = FauxSession()
    p = Pilote(session, relance=lambda: None, taper=lambda: p.interrompre(),
               dormir=lambda s: None)
    p.essayer([50], 120, None, None)
    naviguer(p)
    vus = reste(p)
    assert not any(e.genre == "trace" for e in vus)
    assert any(e.genre == "message" and e.texte ==
               "interrupted before the first frame: Try again"
               for e in vus)
    assert p.tete is None
    assert session.api.appels[-1] == "resume"


def test_interrompre_sans_run_le_dit_sans_pretendre_rien_rendre():
    p = pilote()
    p.essayer([50], 120, None, None)
    jusqua(p, "navigation")
    p.interrompre()
    vus = reste(p)
    assert any(e.genre == "message" and
               e.texte == "interrupted: no run paused" for e in vus)


def test_un_jeu_qui_ne_se_rend_pas_le_dit_sans_casser_le_handler():
    p = essai_en_pause([50], 100)

    def record_stop():
        raise ValueError("agent incoherent")

    p.session.api.record_stop = record_stop
    p.liberer()
    vus = reste(p)
    assert any(e.genre == "message" and e.texte ==
               "the game could not be returned: ValueError('agent incoherent')"
               for e in vus)
    assert not any(e.genre == "erreur" for e in vus)
    assert not any(e.texte == "game returned to the operator" for e in vus)
    assert p.tete is None
    assert vus[-1].genre == "libre"


def pilote_qui_note_les_taps():
    """Un pilote dont chaque tap note l'image que le jeu a atteinte."""
    session = FauxSession()
    images = []
    p = Pilote(session, relance=lambda: None,
               taper=lambda: images.append(session.api.curseur),
               dormir=lambda s: None)
    return p, images


def test_les_taps_partent_a_l_image_voulue():
    """Le tap de demarrage a 0, barriere fermee ; le saut a 50, pas a 51 --
    malgre l'image que le controle du depart a consommee."""
    p, images = pilote_qui_note_les_taps()
    p.essayer([50], 120, None, None)
    naviguer(p)
    reste(p)
    assert images == [0, 50]


def test_un_saut_conserve_part_a_son_image_apres_une_reprise():
    p, images = pilote_qui_note_les_taps()
    p.essayer([50, 150], 100, None, None)
    naviguer(p)
    reste(p)
    p.avancer([50, 150], 200)
    reste(p)
    assert images == [0, 50, 150]
