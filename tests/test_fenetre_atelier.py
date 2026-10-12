"""La fenetre de l'atelier, sur un faux pilote.

Pas de test d'interface au pixel : la fenetre ne contient aucune logique, tout
est dans controller/atelier.py et controller/pilote.py. On verifie qu'elle se
construit, qu'elle lit les evenements du pilote, et que le bandeau et les
boutons suivent l'etat du film.
"""

import importlib.util
import os
import queue
import sys

import pytest

tk = pytest.importorskip("tkinter")

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from controller.pilote import Evenement  # noqa: E402
from tests.faux_agent import chute  # noqa: E402


def charger_atelier():
    chemin = os.path.join(RACINE, "scripts", "atelier.py")
    spec = importlib.util.spec_from_file_location("atelier_pour_test", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


atelier = charger_atelier()


class FauxPilote:
    # Explicite : __getattr__ en ferait une methode, toujours vraie.
    occupe = False

    def __init__(self):
        self.evenements = queue.Queue()
        self.tete = None
        self.commandes = []

    def __getattr__(self, nom):
        # essayer, avancer, sauter, rejouer, rejouer_encore, liberer,
        # confirmer, interrompre, fermer : on note l'appel, rien de plus.
        return lambda *args: self.commandes.append((nom, args))


@pytest.fixture(scope="module")
def racine():
    """Un seul interprete Tcl pour tout le fichier, et trois tentatives.

    Sous Windows, tk.Tk() echoue parfois a relire init.tcl ("couldn't read
    file ... No error") quand on en cree plusieurs d'affilee : un Tk par test
    faisait sauter un test sur sept, au hasard, sans que rien ne le signale.
    """
    derniere = None
    for _ in range(3):
        try:
            principale = tk.Tk()
            break
        except tk.TclError as exc:
            derniere = exc
    else:
        pytest.skip(f"tkinter indisponible : {derniere}")
    principale.withdraw()
    yield principale
    principale.destroy()


@pytest.fixture
def fenetre(racine):
    haut = tk.Toplevel(racine)
    haut.withdraw()
    f = atelier.Fenetre(haut, FauxPilote())
    haut.update()
    yield f
    f.arreter()
    haut.destroy()


def etat(fenetre, action):
    return str(fenetre.boutons[action][0].cget("state"))


def essai(fenetre, sauts, images=120):
    fenetre.pilote.tete = images
    fenetre._recevoir(Evenement(
        "trace", image=images, trace=tuple(chute(images)),
        entrees=tuple(sauts), depart=(786.5624, 500.0), cycle=(16, 17, 17)))


def test_une_fenetre_neuve_est_un_brouillon_qui_ne_propose_qu_essayer(fenetre):
    assert fenetre.badge.cget("text") == "DRAFT"
    assert etat(fenetre, "essayer") == "normal"
    assert etat(fenetre, "geler") == "disabled"
    assert etat(fenetre, "avancer") == "disabled"
    assert etat(fenetre, "rejouer") == "disabled"


def test_essayer_transmet_les_sauts_et_la_longueur(fenetre):
    """Sur un film neuf la longueur est 0 : c'est la longueur requise qui
    part, sans quoi aucun saut pose ne serait joue."""
    fenetre.atelier.poser(50)
    fenetre._essayer()
    requise = fenetre.atelier.longueur_requise
    assert requise == 54
    frontiere = fenetre.atelier.frontiere_turbo(requise)
    assert fenetre.pilote.commandes[-1] == ("essayer",
                                            ([50], requise, frontiere, None))
    assert fenetre.occupe


def test_jouer_jusqu_au_bout_va_jusqu_a_la_longueur_requise(fenetre):
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    fenetre._recevoir(Evenement("trace", image=120, trace=tuple(chute(120)),
                                entrees=(50, 120), saut=120))
    assert fenetre.badge.cget("text") == "DRAFT"
    assert "not yet played" in fenetre.ligne_raison.cget("text")
    assert etat(fenetre, "jusquau_bout") == "normal"
    fenetre._jusquau_bout()
    assert fenetre.pilote.commandes[-1] == ("avancer", ([50, 120], 124))


def test_la_frise_couvre_la_longueur_requise(fenetre):
    fenetre.atelier.poser(50)
    fenetre.rafraichir()
    assert fenetre.echelle.images == 54


def test_un_essai_rendu_passe_le_bandeau_en_essaye(fenetre):
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    assert fenetre.badge.cget("text") == "TRIED"
    assert etat(fenetre, "geler") == "normal"
    assert etat(fenetre, "avancer") == "normal"


def test_decaler_un_saut_repasse_en_brouillon_et_dit_pourquoi(fenetre):
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    fenetre._editer(lambda: fenetre.atelier.decaler(+1))
    assert fenetre.badge.cget("text") == "DRAFT"
    assert "shifted (50 -> 51)" in fenetre.ligne_raison.cget("text")


def test_pendant_une_operation_seul_interrompre_reste(fenetre):
    fenetre._recevoir(Evenement("occupe"))
    assert etat(fenetre, "interrompre") == "normal"
    assert etat(fenetre, "essayer") == "disabled"
    fenetre._recevoir(Evenement("libre"))
    assert etat(fenetre, "essayer") == "normal"


def test_la_navigation_montre_le_bouton_j_y_suis(fenetre):
    fenetre._recevoir(Evenement("navigation", texte="Navigate..."))
    assert fenetre.bouton_y_suis.winfo_manager() == "pack"
    fenetre._recevoir(Evenement("libre"))
    assert fenetre.bouton_y_suis.winfo_manager() == ""


def test_un_jeu_perdu_s_affiche_en_rouge(fenetre):
    fenetre._recevoir(Evenement("erreur", texte="game lost: adb", perdu=True))
    assert "game lost" in fenetre.ligne_jeu.cget("text")
    assert fenetre.ligne_jeu.cget("foreground") == atelier.ROUGE


def test_geler_au_bout_de_l_essai_en_pause_compte_le_premier_passage(
        fenetre, tmp_path):
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    assert fenetre._geler_vers(str(tmp_path / "x.json"), "win", "", None)
    assert fenetre.atelier.passage_reussi
    assert etat(fenetre, "rejouer_encore") == "normal"
    assert "Replay again" in fenetre.message


def test_geler_sans_run_en_pause_demande_un_rejouer_avec_relance(
        fenetre, tmp_path):
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    fenetre.pilote.tete = None      # le jeu a ete rendu depuis l'essai
    assert fenetre._geler_vers(str(tmp_path / "x.json"), "win", "", None)
    assert not fenetre.atelier.passage_reussi
    assert etat(fenetre, "rejouer_encore") == "disabled"
    assert "Replay (with relaunch) for the 1st pass" in fenetre.message


def test_une_erreur_sur_un_film_gele_rompt_la_serie(fenetre, tmp_path):
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    fenetre._geler_vers(str(tmp_path / "x.json"), "win", "", None)
    fenetre.pilote.tete = None
    fenetre._recevoir(Evenement("erreur", texte="replay failed"))
    assert not fenetre.atelier.passage_reussi
    assert etat(fenetre, "rejouer_encore") == "disabled"


def ligne_jeu(fenetre):
    return fenetre.ligne_jeu.cget("text")


def test_la_ligne_jeu_suit_occupe_et_libre(fenetre):
    fenetre._recevoir(Evenement("occupe"))
    assert ligne_jeu(fenetre) == "game: operation in progress"
    fenetre.pilote.tete = 120
    fenetre._recevoir(Evenement("libre"))
    assert ligne_jeu(fenetre) == "game: paused at frame 120"
    fenetre._recevoir(Evenement("occupe"))
    fenetre.pilote.tete = None
    fenetre._recevoir(Evenement("libre"))
    assert ligne_jeu(fenetre) == "game: returned to operator"


def test_sans_trace_la_position_est_inconnue(fenetre):
    assert fenetre.ligne_position.cget("text") == "hero: position unknown"


def test_la_position_suit_la_derniere_trace_notee(fenetre):
    fenetre.atelier.poser(50)
    essai(fenetre, [50], images=120)
    derniere = chute(120)[-1]
    saut = chute(120)[50]
    attendu = (f"hero: x={derniere.x:.4f} y={derniere.y:.4f} "
              f"(frame {derniere.frame}) · jump 1 (frame 50): "
              f"x={saut.x:.4f} y={saut.y:.4f}")
    assert fenetre.ligne_position.cget("text") == attendu


def test_saut_choisi_hors_de_la_trace_dit_position_pas_encore_connue(fenetre):
    fenetre.atelier.poser(110)
    essai(fenetre, [], images=50)
    derniere = chute(50)[-1]
    attendu = (f"hero: x={derniere.x:.4f} y={derniere.y:.4f} "
              f"(frame {derniere.frame}) · jump 1 (frame 110): "
              f"position not yet known")
    assert fenetre.ligne_position.cget("text") == attendu


def test_la_position_du_saut_choisi_suit_son_rang(fenetre):
    fenetre.atelier.poser(30)
    fenetre.atelier.poser(70)   # poser choisit le saut qu'il vient de poser
    essai(fenetre, [30, 70], images=120)
    saut = chute(120)[70]
    attendu_fin = f"jump 2 (frame 70): x={saut.x:.4f} y={saut.y:.4f}"
    assert fenetre.ligne_position.cget("text").endswith(attendu_fin)


def test_la_navigation_ne_dit_pas_que_le_jeu_est_relance(fenetre):
    """Rejouer encore attend aussi [J'y suis], sans relancer."""
    fenetre._recevoir(Evenement("occupe"))
    fenetre._recevoir(Evenement("navigation", texte="Navigate..."))
    assert ligne_jeu(fenetre) == "game: waiting for navigation"


def test_une_erreur_reste_affichee_apres_libre(fenetre):
    fenetre._recevoir(Evenement("occupe"))
    fenetre._recevoir(Evenement("erreur", texte="game lost: adb", perdu=True))
    fenetre._recevoir(Evenement("libre"))
    assert "game lost" in ligne_jeu(fenetre)
    assert fenetre.ligne_jeu.cget("foreground") == atelier.ROUGE


def film_sur_disque(tmp_path):
    from controller.atelier import Atelier
    a = Atelier()
    a.poser(50)
    a.noter_trace(chute(120), [50], (786.5624, 500.0), (16, 17, 17))
    chemin = str(tmp_path / "gele.json")
    a.geler(chemin, "win")
    return chemin


def test_ouvrir_garde_son_message_malgre_la_liberation_du_jeu(fenetre,
                                                              tmp_path):
    chemin = film_sur_disque(tmp_path)
    fenetre.pilote.tete = 120
    fenetre.ouvrir(chemin)
    assert fenetre.pilote.commandes[-1] == ("liberer", ())
    fenetre.pilote.tete = None
    for ev in (Evenement("occupe"),
               Evenement("message", texte="game returned to the operator"),
               Evenement("libre")):
        fenetre._recevoir(ev)
    assert fenetre.message.startswith("Frozen movie opened")
    assert ligne_jeu(fenetre) == "game: returned to operator"


def test_une_erreur_de_la_fenetre_ne_tue_pas_la_scrutation(fenetre):
    """Un evenement qui fait lever _recevoir s'affiche ; le suivant est lu,
    et la scrutation reste armee."""
    fenetre.arreter()
    # Un passage sur un film non gele : noter_passage leve AtelierError.
    fenetre.pilote.evenements.put(Evenement("passage", numero=1,
                                            empreinte="sha256:x"))
    fenetre.pilote.evenements.put(Evenement("occupe"))
    fenetre._scruter()
    assert "only a frozen movie can be replayed" in fenetre.message
    assert fenetre.occupe
    en_attente = fenetre.racine.tk.splitlist(
        fenetre.racine.tk.call("after", "info"))
    assert fenetre._rappel in en_attente


def test_un_film_illisible_est_refuse_dans_le_bandeau(fenetre, tmp_path):
    chemin = tmp_path / "liste.json"
    chemin.write_text("[1, 2]", encoding="utf-8")
    fenetre.ouvrir(str(chemin))
    assert fenetre.message.startswith("open refused: ")
    assert not fenetre.atelier.gele


def test_les_films_se_cherchent_a_la_racine_du_depot(fenetre, monkeypatch):
    films = os.path.join(RACINE, "films")
    assert os.path.normpath(atelier.FILM_NEUF) == os.path.join(films,
                                                               "run.json")
    vus = {}
    monkeypatch.setattr(atelier.filedialog, "askopenfilename",
                        lambda **kw: vus.update(kw) or "")
    fenetre.ouvrir()
    assert os.path.normpath(vus["initialdir"]) == films


def test_geler_sans_issue_choisie_est_refuse(fenetre, tmp_path, monkeypatch):
    erreurs = []
    monkeypatch.setattr(atelier.messagebox, "showerror",
                        lambda titre, texte, **kw: erreurs.append(texte))
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    assert not fenetre._geler_vers(str(tmp_path / "x.json"), "", "", None)
    assert erreurs and "choose the run's outcome" in erreurs[0]
    assert not fenetre.atelier.gele
    assert not (tmp_path / "x.json").exists()


def test_le_dialogue_geler_ne_preselectionne_aucune_issue(fenetre,
                                                          monkeypatch):
    monkeypatch.setattr(atelier.tk.Toplevel, "grab_set", lambda self: None)
    fenetre.atelier.poser(50)
    essai(fenetre, [50])
    fenetre._geler()
    dialogue = [w for w in fenetre.racine.winfo_children()
                if isinstance(w, tk.Toplevel)][-1]
    boutons = [w for w in dialogue.winfo_children()[0].winfo_children()
               if w.winfo_class() == "TRadiobutton"]
    assert len(boutons) == 3
    variable = str(boutons[0].cget("variable"))
    assert fenetre.racine.getvar(variable) == ""
    dialogue.destroy()


def test_avancer_sans_run_en_pause_ne_fait_rien(fenetre):
    fenetre._avancer(10)
    assert fenetre.pilote.commandes == []
    assert not fenetre.occupe


def test_arreter_annule_la_scrutation_du_pilote(fenetre):
    """Sans quoi le rappel survit a la fenetre et tourne sur un widget detruit."""
    fenetre.arreter()
    en_attente = fenetre.racine.tk.splitlist(fenetre.racine.tk.call("after", "info"))
    assert fenetre._rappel not in en_attente


class Clic:
    """Un evenement de souris reduit a son abscisse."""

    def __init__(self, x):
        self.x = x


def test_essayer_s_arrete_au_premier_point_d_arret(fenetre):
    fenetre.atelier.poser(50)
    fenetre.atelier.poser_arret(30)
    fenetre._essayer()
    assert fenetre.pilote.commandes[-1] == ("essayer", ([50], 30, None, None))


def test_jouer_jusqu_au_bout_repart_de_l_arret_vers_le_suivant(fenetre):
    fenetre.atelier.poser(50)
    fenetre.atelier.poser_arret(30)
    fenetre.atelier.poser_arret(45)
    fenetre.pilote.tete = 30
    fenetre._jusquau_bout()
    assert fenetre.pilote.commandes[-1] == ("avancer", ([50], 45))


def test_plus_dix_s_arrete_sur_un_arret_en_chemin(fenetre):
    fenetre.atelier.poser_arret(35)
    fenetre.pilote.tete = 30
    fenetre._avancer(10)
    assert fenetre.pilote.commandes[-1] == ("avancer", ([], 35))


def test_arret_au_repere_pose_un_point_d_arret(fenetre):
    fenetre.repere = 40
    fenetre.rafraichir()
    assert etat(fenetre, "arret") == "normal"
    fenetre._arret_au_repere()
    assert fenetre.atelier.arrets == {40}
    assert fenetre.atelier.film.sauts == []


def test_sans_repere_pas_d_arret(fenetre):
    assert etat(fenetre, "arret") == "disabled"


def test_le_clic_droit_retire_l_arret_sans_toucher_aux_sauts(fenetre):
    fenetre.atelier.poser(50)
    fenetre.atelier.poser_arret(30)
    fenetre.rafraichir()
    fenetre._clic_droit(Clic(fenetre.echelle.x(30)))
    assert fenetre.atelier.arrets == set()
    assert fenetre.atelier.film.sauts == [50]


def test_le_clic_droit_sur_un_saut_retire_le_saut(fenetre):
    fenetre.atelier.poser(50)
    fenetre.atelier.poser_arret(30)
    fenetre.rafraichir()
    fenetre._clic_droit(Clic(fenetre.echelle.x(50)))
    assert fenetre.atelier.film.sauts == []
    assert fenetre.atelier.arrets == {30}


def test_un_arret_atteint_le_dit(fenetre):
    fenetre.atelier.poser(50)
    fenetre.atelier.poser_arret(30)
    fenetre.pilote.tete = 30
    fenetre._recevoir(Evenement(
        "trace", texte="try finished: paused at frame 30", image=30,
        trace=tuple(chute(30)), entrees=(), depart=(786.5624, 500.0),
        cycle=(16, 17, 17)))
    assert fenetre.message.startswith("⏸ breakpoint at frame 30")
    assert fenetre.badge.cget("text") == "DRAFT"


def test_le_bouton_s_appelle_pause_pendant_un_deroule(fenetre):
    bouton = fenetre.boutons["interrompre"][0]
    fenetre._recevoir(Evenement("occupe"))
    assert bouton.cget("text") == "⏸ Pause"
    fenetre._recevoir(Evenement("navigation", texte="Navigate..."))
    assert bouton.cget("text") == "■ Stop"
    fenetre._recevoir(Evenement("image", image=10))
    assert bouton.cget("text") == "⏸ Pause"
    fenetre._recevoir(Evenement("libre"))
    assert bouton.cget("text") == "■ Stop"


def test_pendant_un_rejouer_le_bouton_reste_interrompre(fenetre, tmp_path):
    """Interrompre un passage de film gele rend le jeu : ce n'est pas une
    pause, le libelle ne doit pas le promettre."""
    fenetre.ouvrir(film_sur_disque(tmp_path))
    fenetre._recevoir(Evenement("occupe"))
    assert fenetre.boutons["interrompre"][0].cget("text") == "■ Stop"


# ----- integration : la vraie fenetre sur le vrai pilote -----

import time  # noqa: E402

from controller.movie import load_movie  # noqa: E402
from controller.pilote import Pilote  # noqa: E402
from controller.session import EXPECTED_VERSION_CODE  # noqa: E402
from tests.test_pilote import FauxSession  # noqa: E402


@pytest.fixture
def fenetre_reelle(racine):
    haut = tk.Toplevel(racine)
    haut.withdraw()
    p = Pilote(FauxSession(), relance=lambda: None, taper=lambda: None,
               dormir=lambda s: None)
    f = atelier.Fenetre(haut, p)
    yield f
    p.fermer(delai=5)
    f.arreter()
    haut.destroy()


def pomper(f, delai=10.0):
    """Fait tourner tkinter jusqu'a la fin de l'operation, [J'y suis] compris.

    Le delai borne tout : un pilote qui ne rend jamais la main fait echouer le
    test au lieu de le bloquer.
    """
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        f.racine.update()
        if f.bouton_y_suis.winfo_manager() == "pack":
            f.pilote.confirmer()
        if (not f.occupe and not f.pilote.occupe
                and f.pilote.evenements.empty()):
            return
        time.sleep(0.005)
    raise AssertionError(f"operation pas terminee en {delai} s : "
                         f"{f.message!r}")


def test_essayer_sauter_ici_puis_geler_sur_le_vrai_pilote(fenetre_reelle,
                                                          tmp_path):
    f = fenetre_reelle
    f.atelier.poser(50)
    f._essayer()
    pomper(f)
    assert f.badge.cget("text") == "TRIED"
    assert f.pilote.tete == 54

    f._avancer(10)
    pomper(f)
    f._lancer(f.pilote.sauter)
    pomper(f)
    assert f.atelier.film.sauts == [50, 64]
    assert f.badge.cget("text") == "DRAFT"
    assert "not yet played" in f.ligne_raison.cget("text")
    assert etat(f, "geler") == "disabled"

    f._avancer(10)
    pomper(f)
    assert f.pilote.tete == 74
    assert f.badge.cget("text") == "TRIED"

    chemin = str(tmp_path / "integration.json")
    f.atelier.geler(chemin, "win")
    f.rafraichir()
    assert f.badge.cget("text") == "❄ FROZEN"
    movie = load_movie(chemin, EXPECTED_VERSION_CODE)
    assert movie.run_frames == 74
    assert [i.frame for i in movie.inputs] == [50, 64]
    assert all(i.frame < movie.run_frames for i in movie.inputs)


def test_un_point_d_arret_fige_l_essai_puis_jouer_jusqu_au_bout_finit(
        fenetre_reelle):
    f = fenetre_reelle
    f.atelier.poser(50)
    f.atelier.poser_arret(30)
    f._essayer()
    pomper(f)
    assert f.pilote.tete == 30
    assert f.badge.cget("text") == "DRAFT"
    assert f.message.startswith("⏸ breakpoint at frame 30")

    f._jusquau_bout()
    pomper(f)
    assert f.pilote.tete == 54
    assert f.pilote.run.entrees == [50]
    assert f.badge.cget("text") == "TRIED"
