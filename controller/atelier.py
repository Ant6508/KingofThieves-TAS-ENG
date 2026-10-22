"""L'etat de l'atelier : le film, sa derniere trace, et ce qu'on a le droit d'en faire.

Pur : ni tkinter, ni jeu. L'ecriture du film est injectee, donc tout se teste
sans appareil ni disque.

L'etat n'est jamais deduit de l'historique des clics : il se recalcule a
partir de la trace et des sauts (spec 2026-09-24, section 3). C'est ce qui le
rend vrai quel que soit le chemin par lequel on y est arrive -- et c'est
precisement l'historique des touches, dans tas.py, que l'operateur ne savait
plus suivre.

Toutes les traces que l'atelier note partent d'une relance : l'essai rapide
sans relance n'existe pas ici. Le seul rejeu sans relance est le deuxieme
passage d'un film gele, et il ne passe pas par `noter_trace`.
"""

from __future__ import annotations

import os
import re

from controller.device import PACKAGE
from controller.film_edite import MARGE_TURBO_IMAGES, EditionError, FilmEdite
from controller.movie import (
    CYCLE_HORLOGE_MS,
    ISSUES_CONNUES,
    GameBuild,
    Movie,
    StartConditions,
    TapInput,
    save_movie,
)
from controller.run import LATENCE_TAP_IMAGES
from controller.session import version_attendue
from controller.trace import Etat, empreinte, encode

BROUILLON = "brouillon"
ESSAYE = "essaye"
GELE = "gele"

DT = 1.0 / 60.0

# Tout ce qu'un bouton de la fenetre peut demander. `editer` couvre retirer et
# decaler ; `poser` couvre le double-clic et Poser au repere.
ACTIONS = (
    "essayer", "avancer", "sauter", "jusquau_bout", "reprendre",
    "poser", "editer", "arret", "geler", "ouvrir", "rejouer", "rejouer_encore",
    "degeler", "interrompre",
)


class AtelierError(Exception):
    """L'action demandee n'a pas de sens dans l'etat courant."""


# L'image 0 porte le tap de demarrage, et `verifier_depart` la consomme avant
# que `derouler` ne commence : un saut pose la ne partirait jamais, en silence.
IMAGE_0_PRISE = ("frame 0 already carries the starting tap and the start "
                 "check: place the jump at frame 1 at the earliest")


def nom_suggere(chemin: str, existe=os.path.exists) -> str:
    """Le premier `<nom>_vN.json` libre a cote de `chemin`, N partant de 2.

    Un chemin deja suffixe repart de son propre numero : la copie de
    `run_v2.json` se propose en `run_v3.json`, pas en `run_v2_v2.json`.
    """
    racine, extension = os.path.splitext(chemin)
    trouve = re.fullmatch(r"(.*)_v(\d+)", racine)
    if trouve:
        base, numero = trouve.group(1), int(trouve.group(2)) + 1
    else:
        base, numero = racine, 2
    while existe(f"{base}_v{numero}{extension}"):
        numero += 1
    return f"{base}_v{numero}{extension}"


def chemin_libre(chemin: str, existe=os.path.exists) -> str:
    """`chemin` s'il est libre, sinon le premier nom suggere a cote."""
    return nom_suggere(chemin, existe) if existe(chemin) else chemin


class Atelier:
    def __init__(self) -> None:
        self.film = FilmEdite()
        self.longueur = 0
        self.trace: list[Etat] = []
        self.joues: tuple[int, ...] = ()
        # Image ou le heros est sorti du niveau dans la derniere trace.
        self.sortie: int | None = None
        self.depart: tuple[float, float] | None = None
        self.cycle: tuple[int, ...] = CYCLE_HORLOGE_MS
        self.chemin: str | None = None
        self.source: str | None = None
        self.label = ""
        self.gele = False
        self.movie: Movie | None = None
        self.passages = 0
        self.passage_reussi = False
        self.derniere_edition: str | None = None
        # Points d'arret de l'outil : ni gele, ni enregistre, ni rejoue. Ils
        # vivent le temps de la seance ; Degeler les garde, Ouvrir (un nouvel
        # Atelier) les efface.
        self.arrets: set[int] = set()

    @classmethod
    def depuis_film(cls, movie: Movie, chemin: str) -> "Atelier":
        """Un film rouvert : gele, en lecture seule, sans trace."""
        atelier = cls()
        atelier.film = FilmEdite([i.frame for i in movie.inputs])
        atelier.longueur = movie.run_frames
        atelier.depart = (movie.start.hero_x, movie.start.hero_y)
        atelier.cycle = tuple(movie.clock_cycle_ms)
        atelier.label = movie.run_label
        atelier.chemin = str(chemin)
        atelier.movie = movie
        atelier.gele = True
        return atelier

    @property
    def a_perdre(self) -> bool:
        """Une copie de travail touchee et pas encore gelee."""
        return not self.gele and (bool(self.film.sauts) or bool(self.trace))

    # ----- etat -----

    @property
    def etat(self) -> str:
        if self.gele:
            return GELE
        if self._trace_a_jour():
            return ESSAYE
        return BROUILLON

    @property
    def longueur_requise(self) -> int:
        """Nombre d'enregistrements qu'une trace doit porter pour decrire le film.

        La longueur du run, et au moins de quoi voir partir le dernier saut.
        Un tap emis a l'image N atteint le pas N + LATENCE_TAP_IMAGES ; l'etat
        d'apres ce pas est l'enregistrement N + LATENCE_TAP_IMAGES + 1, car
        l'enregistrement k est l'etat d'avant l'image k. Il faut donc
        N + LATENCE_TAP_IMAGES + 2 enregistrements. Sans cela le decollage
        n'est pas dans l'empreinte, et un film gele avec run_frames == N ne
        rejouerait meme pas le saut : derouler n'emet que les taps n < images.
        """
        if not self.film.sauts:
            return self.longueur
        return max(self.longueur,
                   max(self.film.sauts) + LATENCE_TAP_IMAGES + 2)

    def _trace_a_jour(self) -> bool:
        return (bool(self.trace)
                and len(self.trace) >= self.longueur_requise
                and tuple(self.film.sauts) == self.joues)

    @property
    def raison(self) -> str:
        """Pourquoi le film est dans son etat, en une phrase pour le bandeau."""
        if self.gele:
            return f"movie frozen: {self.chemin}, read-only"
        if not self.trace:
            return self.derniere_edition or "no try since opening"
        requise = self.longueur_requise
        if len(self.trace) < self.longueur:
            return (f"trace stopped at frame {len(self.trace)} "
                    f"of {requise}")
        if tuple(self.film.sauts) != self.joues:
            return (self.derniere_edition
                    or "the jumps changed since the last try")
        if len(self.trace) < requise:
            dernier = max(self.film.sauts)
            if self.sortie is not None:
                # Le run ne va pas plus loin : avancer n'y changera rien.
                return (f"jump at frame {dernier} too close to the level "
                        f"exit (frame {self.sortie}): its liftoff isn't in "
                        f"the trace")
            return (f"jump at frame {dernier} not yet played to its "
                    f"liftoff: advance to frame {requise}")
        if self.sortie is not None:
            return (f"trace up to date: hero exited the level at frame "
                    f"{self.sortie}, since a relaunch")
        return f"trace up to date: {len(self.trace)} frames since a relaunch"

    @property
    def empreinte(self) -> str | None:
        """L'empreinte de la trace, seulement quand elle decrit ce film."""
        if self.etat != ESSAYE:
            return None
        return empreinte(encode(self.trace))

    # ----- editions -----

    def _modifiable(self) -> None:
        if self.gele:
            raise AtelierError("movie frozen: unfreeze it to edit it")

    def choisir(self, image: int) -> None:
        try:
            self.film.choisir(image)
        except EditionError as exc:
            raise AtelierError(str(exc)) from exc

    def poser(self, image: int) -> None:
        self._modifiable()
        if image == 0:
            raise AtelierError(IMAGE_0_PRISE)
        try:
            self.film.poser(image)
        except EditionError as exc:
            raise AtelierError(str(exc)) from exc
        self.derniere_edition = f"jump placed at frame {image}"

    def retirer(self, image: int) -> None:
        self._modifiable()
        self.choisir(image)
        self.film.retirer()
        self.derniere_edition = f"jump at frame {image} removed"

    def deplacer(self, de: int, vers: int) -> None:
        self._modifiable()
        self.choisir(de)
        if vers == 0:
            raise AtelierError(IMAGE_0_PRISE)
        rang = self.film.index + 1
        try:
            self.film.decaler(vers - de)
        except EditionError as exc:
            raise AtelierError(str(exc)) from exc
        self.derniere_edition = f"jump {rang} shifted ({de} -> {vers})"

    def decaler(self, pas: int) -> None:
        choisi = self.film.choisi
        if choisi is None:
            raise AtelierError("no jump to shift: the movie is empty")
        self.deplacer(choisi, choisi + pas)

    # ----- points d'arret -----

    def poser_arret(self, image: int) -> None:
        """Un point d'arret de l'outil : le deroule se fige a `image`.

        Ce n'est pas une entree du film : ni l'etat ni l'empreinte n'en
        dependent (spec des points d'arret, section 2).
        """
        self._modifiable()
        if image <= 0:
            raise AtelierError(
                "a breakpoint at frame 0 wouldn't freeze anything: the run "
                "hasn't started yet")
        if image in self.arrets:
            raise AtelierError(
                f"a breakpoint is already placed at frame {image}")
        self.arrets.add(image)

    def retirer_arret(self, image: int) -> None:
        if image not in self.arrets:
            raise AtelierError(f"no breakpoint at frame {image}")
        self.arrets.discard(image)

    def borne(self, depuis: int, jusqua: int) -> int:
        """L'image ou un deroule de `depuis` vers `jusqua` doit s'arreter.

        Le premier arret strictement apres `depuis` -- on repart d'un arret
        sans s'y rebloquer -- et strictement avant `jusqua`, ou `jusqua` s'il
        n'y en a pas.
        """
        return min((a for a in self.arrets if depuis < a < jusqua),
                   default=jusqua)

    # ----- traces -----

    def noter_trace(self, trace, joues, depart=None, cycle=None,
                    fin=None) -> None:
        """Enregistre ce que le jeu vient de jouer depuis une relance.

        La trace est toujours celle d'un run parti d'une relance : elle arrive
        en fin d'essai, ou apres +1, +10 ou Sauter ici dans ce meme run, et
        porte alors tout le run depuis l'image 0.

        `joues` est la liste des taps reellement emis (`Run.entrees`). La
        raison de la derniere edition ne s'efface que si la trace rattrape le
        film : sinon c'est encore elle qui explique le brouillon.

        `fin` est l'image ou le heros est sorti du niveau (`Run.mort_a`), None
        s'il est encore lisible. Un run sorti du niveau ne va pas plus loin :
        sa longueur est celle de sa trace, meme plus courte que le film, sans
        quoi il resterait en brouillon a attendre des images qui ne viendront
        jamais.
        """
        self.trace = list(trace)
        self.joues = tuple(sorted(joues))
        self.sortie = fin
        if fin is not None:
            self.longueur = len(self.trace)
        else:
            self.longueur = max(self.longueur, len(self.trace))
        if depart is not None:
            self.depart = (depart[0], depart[1])
        if cycle is not None:
            self.cycle = tuple(cycle)
        if tuple(self.film.sauts) == self.joues:
            self.derniere_edition = None

    def sauter_en_direct(self, image: int) -> None:
        """Le jeu vient d'emettre un tap a `image` : le film le porte desormais.

        Ce n'est pas une edition. Le tap a reellement ete joue dans un run
        parti d'une relance, et donne la meme trace que son rejeu (spec
        section 8, mesure de la tache 1 du plan 8). Le film reste pourtant
        Brouillon tant que la trace n'a pas atteint son decollage : voir
        `longueur_requise`. Un saut deja
        pose a cette image -- conserve apres un Reprendre d'ici -- n'est pas
        double : c'est lui qui vient de partir.
        """
        self._modifiable()
        if image in self.film.sauts:
            self.film.choisir(image)
        else:
            self.film.poser(image)

    def frontiere_turbo(self, jusqua: int) -> int | None:
        """Image ou le turbo se coupe, pour un deroule qui s'arrete a `jusqua`.

        Le saut choisi s'il tombe avant `jusqua`, sinon `jusqua` lui-meme : on
        veut voir arriver ce qu'on travaille, ou l'endroit ou l'on reprend.
        """
        cible = self.film.choisi
        if cible is None or cible > jusqua:
            cible = jusqua
        if cible <= MARGE_TURBO_IMAGES:
            return None
        return cible - MARGE_TURBO_IMAGES

    # ----- gel -----

    def geler(self, chemin: str, issue: str, label: str | None = None,
              ecrire=save_movie, premier_passage: bool = True) -> Movie:
        """Ecrit le film et le fige. Seul un film Essaye se gele.

        Geler compte comme premier passage quand le jeu est encore en pause a
        la fin de la trace qu'on fige : elle a ete jouee depuis une relance,
        et le deuxieme passage sans relance -- le jeu exige de reussir le
        donjon deux fois d'affilee -- peut suivre aussitot. Sinon
        (`premier_passage` faux : jeu rendu, perdu, ou run prolonge ailleurs)
        il n'y a rien a enchainer, et seul Rejouer, avec relance, reste.
        """
        if self.etat != ESSAYE:
            raise AtelierError(f"only a tried movie can be frozen: {self.raison}")
        if issue not in ISSUES_CONNUES:
            raise AtelierError(
                f"unknown outcome: {issue}, expected {', '.join(ISSUES_CONNUES)}")
        # Egal a la longueur requise ou plus : l'etat Essaye l'exige.
        run_frames = len(self.trace)
        # Par defense : derouler n'emet que les taps n < run_frames, un tel
        # saut serait ecrit au film sans jamais etre rejoue.
        hors_run = [n for n in self.film.sauts if n >= run_frames]
        if hors_run:
            raise AtelierError(
                f"jump at frame {hors_run[0]} beyond the run "
                f"({run_frames} frames): the replay wouldn't fire it")
        movie = Movie(
            game=GameBuild(PACKAGE, *version_attendue()),
            dt=DT,
            run_frames=run_frames,
            start=StartConditions(relaunch=True, tap_demarrage=True,
                                  hero_x=self.depart[0],
                                  hero_y=self.depart[1]),
            clock_cycle_ms=self.cycle,
            run_label=self.label if label is None else label,
            inputs=[TapInput(frame=n) for n in self.film.sauts],
            outcome_status=issue,
            outcome_frame=None,
            fingerprint=self.empreinte,
        )
        ecrire(movie, chemin)
        self.label = movie.run_label
        self.chemin = str(chemin)
        self.source = None
        self.movie = movie
        self.gele = True
        self.passages = 1 if premier_passage else 0
        self.passage_reussi = premier_passage
        return movie

    def degeler(self) -> None:
        """Une copie de travail du film gele, en Brouillon.

        Le fichier gele n'est pas touche : seul un regel explicite, avec
        Ecraser l'original, le remplacera.
        """
        if not self.gele:
            raise AtelierError("the movie isn't frozen")
        self.source = self.chemin
        self.chemin = None
        self.gele = False
        self.movie = None
        self.trace = []
        self.joues = ()
        self.sortie = None
        self.passages = 0
        self.passage_reussi = False
        self.derniere_edition = f"working copy of {self.source}, no try yet"

    # ----- rejeu d'un film gele -----

    def noter_passage(self, numero: int, empreinte_obtenue: str) -> str:
        """Rend le verdict du passage `numero` a afficher.

        Seul le premier passage se compare au film : il part d'une relance,
        comme l'essai qui a produit l'empreinte. Les suivants partent de
        l'ecran d'apres-run, dont la camera est cadree 690 px plus loin
        (kot_headless/docs/savoir/jeu/horloge.md).
        """
        if not self.gele:
            raise AtelierError("only a frozen movie can be replayed")
        self.passages = numero
        if numero > 1:
            return (f"pass {numero} finished, without relaunch. Its "
                    f"fingerprint isn't compared to the movie's: the camera "
                    f"doesn't start from the same framing.")
        attendue = self.movie.fingerprint
        if attendue is None:
            self.passage_reussi = True
            return ("1st pass finished. The movie carries no fingerprint: "
                    "nothing to compare.")
        self.passage_reussi = empreinte_obtenue == attendue
        if self.passage_reussi:
            return "1st pass: fingerprint identical to the movie's"
        return (f"1st pass: MISMATCH. Got {empreinte_obtenue}, the movie "
                f"carries {attendue}. No 2nd pass on a failed replay.")

    # ----- boutons -----

    def actions(self, occupe: bool, tete: int | None) -> dict[str, bool]:
        """Ce que chaque bouton a le droit de faire maintenant.

        `tete` est l'image ou le run vivant du pilote est en pause, ou None
        s'il n'y en a pas. Pendant une operation, seul Interrompre reste.
        """
        if occupe:
            return {nom: nom == "interrompre" for nom in ACTIONS}
        gele = self.gele
        # Un heros sorti du niveau n'est plus lisible : prolonger le run
        # leverait une RunError, et le pilote rendrait le jeu -- tuant le run
        # en pause qu'on peut encore geler.
        vivant = tete is not None and not gele and self.sortie is None
        return {
            "essayer": not gele,
            "avancer": vivant,
            "sauter": vivant,
            "jusquau_bout": vivant and tete < self.longueur_requise,
            "reprendre": not gele and self.longueur > 0,
            "poser": not gele,
            "editer": not gele,
            "arret": not gele,
            "geler": self.etat == ESSAYE,
            "ouvrir": True,
            "rejouer": gele,
            "rejouer_encore": gele and self.passage_reussi,
            "degeler": gele,
            "interrompre": False,
        }
