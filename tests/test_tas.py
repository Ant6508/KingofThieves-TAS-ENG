"""Les deux garde-fous de coherence du balayage, dans scripts/tas.py.

`tas.py` etait le seul fichier du projet sans tests, et c'etait assume : il ne
fait que de la colle entre des pieces deja testees. Exception pour ces deux
garde-fous, qui repondent a des questions que personne d'autre ne peut poser
-- et que la relecture a chaque fois attrapees une fois, alors qu'un test les
attrape toujours.

`_balayage_perime` : un Balayage fige a sa construction le saut qu'il
travaille et la longueur du run. Les fleches haut et bas deplacent le curseur
sans etre des editions, donc sans effacer le balayage ; repris tel quel, il
travaillerait un autre saut que celui que l'ecran surligne. Une avance
manuelle allonge le run, et la borne figee fait alors mentir le compte
d'essais par le bas.

`trace_regardee` : un balayage remplace `self.run` a chaque couple, donc il
laisse derriere lui la trace de son dernier essai -- un coin de l'espace de
recherche, joue en turbo plein, que personne n'a vu, et portant un film
different de celui qu'on vient d'appliquer. `proposer_cible` promet de lire
"l'essai que l'operateur vient de regarder" : sans ce drapeau, un second F4
sans repasser par F2 en tirait une cible valide et fausse.

La Seance se construit ici par `__new__` : son `__init__` demande une session
Frida, donc un appareil, et aucun des deux garde-fous n'en a besoin.
"""

import importlib.util
import os
import sys
import types

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def charger_tas():
    """Charge scripts/tas.py comme un module, sans l'executer comme script.

    Son analyse d'arguments tourne a l'import et lit sys.argv, celui de pytest
    en l'occurrence : elle ignore ce qu'elle ne reconnait pas, donc rien a
    neutraliser.
    """
    if RACINE not in sys.path:
        sys.path.insert(0, RACINE)
    chemin = os.path.join(RACINE, "scripts", "tas.py")
    spec = importlib.util.spec_from_file_location("tas_pour_test", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tas = charger_tas()

from controller.cible import Cible  # noqa: E402
from controller.film_edite import FilmEdite  # noqa: E402
from controller.solveur import Balayage, espace  # noqa: E402


def seance(sauts, index, longueur, balayage_index=None, balayage_images=None):
    """Une Seance reduite a ce que `_balayage_perime` regarde.

    `balayage_index` et `balayage_images` decrivent le balayage en cours ; par
    defaut il colle au film, donc il est reprenable.
    """
    s = tas.Seance.__new__(tas.Seance)
    s.film = FilmEdite(sauts)
    s.film.index = index
    s.longueur = longueur
    s.balayage = Balayage(
        sauts,
        index if balayage_index is None else balayage_index,
        longueur if balayage_images is None else balayage_images,
        espace(1, 1),
    )
    return s


def test_un_balayage_qui_colle_au_film_est_reprenable():
    assert seance([100, 200], index=1, longueur=400)._balayage_perime() is None


def test_sans_balayage_il_n_y_a_rien_a_perimer():
    s = seance([100, 200], index=1, longueur=400)
    s.balayage = None

    assert s._balayage_perime() is None


def test_un_balayage_termine_n_est_plus_a_reprendre():
    """Il sera reconstruit, donc sa coherence ne se juge plus."""
    s = seance([100, 200], index=1, longueur=400)
    for couple in list(s.balayage.restants()):
        s.balayage.noter(couple, progression=-700.0, reussi=False)

    assert s._balayage_perime() is None


def test_le_curseur_deplace_perime_le_balayage():
    """Les fleches haut et bas ne sont pas des editions, donc elles
    n'effacent pas le balayage -- et il travaillerait le saut de l'image 200
    pendant que l'ecran surligne celui de l'image 100."""
    s = seance([100, 200], index=1, longueur=400)
    s.film.choisir(100)

    message = s._balayage_perime()

    assert message is not None
    assert "200" in message and "100" in message


def test_le_run_allonge_perime_le_balayage():
    """La borne figee reste plus petite, donc des couples que le run plus
    long rendrait valides resteraient ecartes -- un total qui ment par le
    bas, sans le dire."""
    s = seance([100, 200], index=1, longueur=400, balayage_images=300)

    message = s._balayage_perime()

    assert message is not None
    assert "400" in message and "300" in message


def test_une_liste_de_sauts_differente_perime_le_balayage():
    """Ceinture et bretelles : une edition efface deja le balayage, mais
    l'invariant merite d'etre verifie plutot que suppose."""
    s = seance([100, 200], index=1, longueur=400)
    s.film = FilmEdite([100, 250])
    s.film.index = 1

    assert s._balayage_perime() is not None


@pytest.mark.parametrize("nom", [
    "balayer",
    "_essayer_sauts",
    "_regler_la_cible",
    "_interrompu",
    "_dire_balayage",
    "_appliquer_le_meilleur",
    "_balayage_perime",
])
def test_la_seance_porte_les_methodes_du_balayage(nom):
    """Le module se charge et la classe est complete : c'est tout ce qu'on
    peut verifier sans appareil, et ca attrape une faute de frappe dans la
    table de dispatch."""
    assert hasattr(tas.Seance, nom)


def test_la_touche_f4_est_branchee_sur_le_balayage():
    """La table de dispatch de main() n'est pas lisible sans lancer la
    seance : on verifie au moins que le decodeur et la methode se
    rencontrent sous le meme nom."""
    from controller.keys import TOUCHES_ETENDUES

    assert TOUCHES_ETENDUES[b">"] == "balayage"
    assert hasattr(tas.Seance, "balayer")


# ----- la trace regardee -----

def seance_pour_cible(trace_regardee, balayage=None):
    """Une Seance reduite a ce que la precondition de `balayer` regarde."""
    s = tas.Seance.__new__(tas.Seance)
    s.depart = (96.0, 548.0)
    s.film = FilmEdite([100, 200])
    s.film.index = 1
    s.longueur = 400
    s.balayage = balayage
    s.cible = None
    s.trace_regardee = trace_regardee
    s.run = types.SimpleNamespace(etats=[object()])
    s.dits = []
    s.dire = s.dits.append
    return s


def test_f4_refuse_une_trace_que_personne_n_a_regardee():
    """Un balayage remplace self.run a chaque couple : il laisse derriere lui
    la trace de son dernier essai, jouee en turbo plein, sur un film qui a
    change depuis. proposer_cible promet de lire l essai que l operateur
    vient de REGARDER -- elle rendrait ici une cible valide et fausse."""
    s = seance_pour_cible(trace_regardee=False)

    s.balayer()

    assert len(s.dits) == 1
    assert "F2" in s.dits[0]


def test_f4_accepte_une_trace_regardee():
    """Le refus ne doit pas mordre sur le cas nominal : on verifie qu il
    laisse passer, en s arretant a l appel suivant."""
    s = seance_pour_cible(trace_regardee=True)
    s._regler_la_cible = lambda: None      # l operateur annule aussitot

    s.balayer()

    assert s.dits == ["sweep cancelled"]


def test_reprendre_un_balayage_ne_relit_aucune_trace():
    """Une reprise reutilise la cible deja validee : exiger un essai regarde
    la rendrait impossible apres l ancrage rate qu elle sert justement a
    rattraper."""
    balayage = Balayage([100, 200], index=1, images=400, couples=espace(1, 1))
    s = seance_pour_cible(trace_regardee=False, balayage=balayage)
    s.cible = Cible("x", -1, 500.0, 400)
    s._essayer_sauts = lambda sauts: (_ for _ in ()).throw(
        AssertionError("on ne devait pas aller jusqu a l essai"))

    with pytest.raises(AssertionError):
        s.balayer()

    # Le message de refus n a pas ete emis : la precondition a laisse passer.
    assert all("F2" not in dit for dit in s.dits)
