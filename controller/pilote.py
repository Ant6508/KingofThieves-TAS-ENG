"""Le pilote de l'atelier : les operations bloquantes, dans un thread.

Relancer, attendre que l'operateur ait navigue, derouler : cela prend des
secondes, parfois des minutes, et la fenetre doit rester vivante pendant ce
temps. Le pilote fait ce travail dans un thread et ne parle a la fenetre que
par une file d'evenements. Il ne connait pas tkinter.

Il ne connait pas non plus l'Atelier : il recoit les sauts a jouer et rend ce
que le jeu a joue. C'est la fenetre qui recopie l'un dans l'autre, dans le
thread de tkinter -- l'etat du film n'est donc jamais touche par deux threads.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

import frida

from controller import entree
from controller.depart import DepartError, confirmer_le_depart
from controller.device import DeviceError
from controller.movie import IncompatibleMovie, verifier_rejouable
from controller.relance import relancer
from controller.run import Run, RunError, derouler
from controller.session import SessionError
from controller.trace import empreinte, encode

# Images relachees d'un coup entre deux regards sur le bouton Interrompre. Une
# seconde de jeu : assez pour que le turbo ne passe pas son temps a scruter
# (chaque tranche coute au moins une attente de PAS_DE_SCRUTATION), assez peu
# pour qu'une interruption soit prise sans delai sensible. Couper une avance en
# tranches ne change pas la trace : la barriere retient le jeu entre deux, et
# un gel ne provoque aucun rattrapage (NOTES.md, "Le gel ne provoque aucun
# rattrapage -- confirme finement").
TRANCHE_IMAGES = 60

# Ce qui veut dire que le jeu ou sa session sont perdus, pas que le run a rate.
PERTES = (DeviceError, SessionError, frida.InvalidOperationError,
          frida.TransportError)


class Interrompu(Exception):
    """L'operateur a demande l'arret."""


class RunPilote(Run):
    """Un Run dont l'avance se decoupe en tranches, et s'interrompt entre deux.

    `progression` recoit l'image courante apres chaque tranche : la fenetre
    fait avancer le curseur de la frise avec.
    """

    def __init__(self, api, interruption, progression, **kwargs) -> None:
        super().__init__(api, **kwargs)
        self._interruption = interruption
        self._progression = progression

    def avancer(self, images: int):
        rendus = []
        while images > 0:
            if self._interruption.is_set():
                raise Interrompu()
            tranche = min(images, TRANCHE_IMAGES)
            nouveaux = super().avancer(tranche)
            rendus.extend(nouveaux)
            images -= tranche
            self._progression(self.image)
            if len(nouveaux) < tranche:
                break   # le heros n'est plus lisible : rien de plus a relever
        return rendus


@dataclass(frozen=True)
class Evenement:
    """Ce que le pilote dit a la fenetre.

    genres : `occupe` et `libre` encadrent chaque operation ; `message` est a
    afficher ; `navigation` demande [J'y suis] ; `image` fait avancer le
    curseur ; `trace` rend ce que le jeu a joue, le run restant en pause a
    `image` ; `passage` rend l'empreinte d'un rejeu de film gele ; `erreur`
    dit ce qui a rate, `perdu` si le jeu ou sa session sont a relancer.

    `fin`, sur une trace, est l'image ou le heros est sorti du niveau
    (`Run.mort_a`), None s'il est encore lisible.
    """

    genre: str
    texte: str = ""
    image: int | None = None
    trace: tuple = ()
    entrees: tuple = ()
    depart: tuple | None = None
    cycle: tuple | None = None
    saut: int | None = None
    numero: int | None = None
    empreinte: str | None = None
    perdu: bool = False
    fin: int | None = None


class Pilote:
    def __init__(self, session, evenements=None, relance=relancer,
                 taper=entree.taper, dormir=time.sleep) -> None:
        self.session = session
        self.evenements = (evenements if evenements is not None
                           else queue.Queue())
        self._relance = relance
        self._taper = taper
        self._dormir = dormir
        self.run: RunPilote | None = None
        self.depart: tuple[float, float] | None = None
        self.cycle: tuple[int, ...] | None = None
        self._fil: threading.Thread | None = None
        self._en_cours = False
        self._confirmation = threading.Event()
        self._interruption = threading.Event()

    # ----- ce que la fenetre lit -----

    @property
    def occupe(self) -> bool:
        """Une operation est en cours.

        Pas `is_alive()` : le thread vit encore un instant apres avoir emis
        `libre`, et la fenetre qui reagit a `libre` en lancant la commande
        suivante se la verrait refuser.
        """
        return self._en_cours

    @property
    def tete(self) -> int | None:
        """Image ou le run vivant est en pause, None s'il n'y en a pas."""
        # Une seule lecture : le thread du pilote peut remettre `run` a None
        # entre le test et l'acces.
        run = self.run
        return None if run is None else run.image

    # ----- commandes, appelees depuis la fenetre -----

    def essayer(self, sauts, jusqua, frontiere, depart_attendu) -> None:
        """Relance, navigation, deroule jusqu'a `jusqua`, pause.

        Sert aussi a Reprendre d'ici : `jusqua` est alors l'image choisie, et
        les sauts posterieurs ne sont pas emis -- `derouler` n'emet que ceux
        d'avant `jusqua`. Ils restent au film.
        """
        self._lancer(self._essayer, list(sauts), jusqua, frontiere,
                     depart_attendu)

    def avancer(self, sauts, jusqua) -> None:
        """Prolonge le run vivant jusqu'a `jusqua` : +1, +10, jusqu'au bout.

        Les sauts du film que l'avance rencontre partent au passage, sauf ceux
        deja emis dans ce run.
        """
        self._lancer(self._avancer, list(sauts), jusqua)

    def sauter(self) -> None:
        """Sauter ici : un tap a l'image ou le run est en pause."""
        self._lancer(self._sauter)

    def rejouer(self, movie) -> None:
        """Premier passage d'un film gele : relance, navigation, vitesse normale."""
        self._lancer(self._rejouer, movie)

    def rejouer_encore(self, movie, numero: int) -> None:
        """Passage suivant, sans relance : le jeu exige deux reussites d'affilee."""
        self._lancer(self._rejouer_encore, movie, numero)

    def liberer(self) -> None:
        """Rend le jeu a l'operateur, sans rien jouer : avant d'ouvrir un film."""
        self._lancer(self._liberer)

    def fermer(self, delai: float = 5.0) -> None:
        """A la fermeture de la fenetre : arrete tout et rend le jeu."""
        self.interrompre()
        self.attendre(delai)
        self._rendre_le_jeu()
        try:
            self.session.detach()
        except PERTES:
            pass

    def confirmer(self) -> None:
        """[J'y suis]."""
        self._confirmation.set()

    def interrompre(self) -> None:
        self._interruption.set()

    def attendre(self, delai: float | None = None) -> None:
        if self._fil is not None:
            self._fil.join(delai)

    # ----- mecanique -----

    def _lancer(self, travail, *args) -> None:
        if self.occupe:
            raise RuntimeError("an operation is already in progress")
        self._interruption.clear()
        self._confirmation.clear()
        self._fil = threading.Thread(target=self._executer,
                                     args=(travail, *args), daemon=True,
                                     name="kot-pilote")
        self._en_cours = True
        self._fil.start()

    def _executer(self, travail, *args) -> None:
        self._emettre("occupe")
        try:
            travail(*args)
        except Interrompu:
            self._arret_sur_interruption()
        except PERTES as exc:
            # Une perte d'adb ne dit pas que Frida est mort, ni l'inverse : le
            # jeu est peut-etre encore la, fige dans la barriere. On essaie de
            # le rendre ; _rendre_le_jeu avale les pertes si c'est trop tard.
            self._rendre_le_jeu()
            self._emettre("erreur", texte=f"game lost: {exc}", perdu=True)
        except (RunError, IncompatibleMovie) as exc:
            self._rendre_le_jeu()
            self._emettre("erreur", texte=str(exc))
        except Exception as exc:  # noqa: BLE001 -- un thread ne meurt pas en silence
            self._rendre_le_jeu()
            self._emettre("erreur", texte=f"unexpected error: {exc!r}")
        finally:
            # Avant `libre`, jamais apres : qui lit `libre` doit trouver le
            # pilote disponible.
            self._en_cours = False
            self._emettre("libre")

    def _emettre(self, genre: str, **champs) -> None:
        self.evenements.put(Evenement(genre, **champs))

    def _emettre_trace(self, texte: str, saut: int | None = None) -> None:
        run = self.run
        self._emettre("trace", texte=texte, image=run.image,
                      trace=tuple(run.trace), entrees=tuple(run.entrees),
                      depart=self.depart, cycle=self.cycle, saut=saut,
                      fin=run.mort_a)

    def _nouveau_run(self) -> RunPilote:
        return RunPilote(
            self.session.api, self._interruption,
            lambda image: self._emettre("image", image=image),
            taper=self._taper, dormir=self._dormir,
        )

    def _rendre_le_jeu(self) -> bool:
        """Termine le run vivant, s'il y en a un : barriere, horloge, turbo.

        Ne leve jamais : on l'appelle depuis les handlers d'erreur de
        `_executer`, et une exception qui en sortirait tuerait le thread sans
        emettre `libre`. Rend False si le jeu n'a pas pu etre rendu.
        """
        run, self.run = self.run, None
        if run is None:
            return True
        try:
            run.terminer()
        except PERTES:
            return False   # la session est morte avec le jeu : rien a rendre
        except Exception as exc:  # noqa: BLE001 -- voir la docstring
            self._emettre("message",
                          texte=f"the game could not be returned: {exc!r}")
            return False
        return True

    def _arret_sur_interruption(self) -> None:
        if self.run is None:
            # Soit aucun run n'a commence, soit c'etait le passage d'un film
            # gele, que son finally a deja rendu : il n'y a juste rien en pause.
            self._emettre("message", texte="interrupted: no run paused")
            return
        if self.run.image == 0:
            # Entre ancrer et la premiere image : le tap de demarrage est parti
            # mais rien n'est releve. Rien a garder en pause, et une trace vide
            # ecraserait la courbe de l'essai precedent : on rend le jeu.
            self._rendre_le_jeu()
            self._emettre("message", texte="interrupted before the first "
                                           "frame: Try again")
            return
        try:
            self.run.turbo(False)
        except PERTES:
            self.run = None
            self._emettre("erreur", texte="game lost during interruption",
                          perdu=True)
            return
        self._emettre_trace(
            f"interrupted at frame {self.run.image}: the game stays paused")

    def _relancer_le_jeu(self) -> None:
        self._rendre_le_jeu()
        self.session.detach()
        self._emettre("message", texte="relaunching the game...")
        # Une relance et une attache durent des secondes, parfois des
        # dizaines : c'est la qu'un Interrompre -- ou une fermeture de la
        # fenetre -- a le plus de chances de tomber. On le prend des qu'elles
        # rendent la main, sans attacher ni demander de navigation pour rien.
        self._relance()
        self._verifier_interruption()
        self.session.attacher_avec_reessais()
        self._verifier_interruption()

    def _verifier_interruption(self) -> None:
        if self._interruption.is_set():
            raise Interrompu()

    def _attendre_clic(self) -> None:
        self._confirmation.clear()
        self._emettre("navigation",
                      texte="Navigate to the starting screen in "
                            "MEmu, then [Ready].")
        while not self._confirmation.wait(0.05):
            if self._interruption.is_set():
                raise Interrompu()

    def _attendre_navigation(self, attendu) -> tuple[float, float]:
        """Attend [J'y suis], puis releve la position du heros.

        Une DepartError ne coute rien a rattraper : aucun tap n'est parti, le
        niveau n'a pas commence. On le dit, et on attend un nouveau clic.
        """
        while True:
            try:
                return confirmer_le_depart(
                    self.session.api, attendu=attendu,
                    demander=self._attendre_clic,
                    dire=lambda texte: self._emettre("message", texte=texte))
            except DepartError as exc:
                self._emettre("message",
                              texte=f"{exc} Navigate again, then [Ready].")

    # ----- les operations, dans le thread -----

    def _essayer(self, sauts, jusqua, frontiere, depart_attendu) -> None:
        self._relancer_le_jeu()
        self.depart = self._attendre_navigation(depart_attendu)
        self.cycle = tuple(self.session.api.cycle())
        self.run = self._nouveau_run()
        self.run.ancrer()
        # Une AncrageError ici veut dire que le tap de demarrage est parti :
        # le niveau a commence, et seule une relance ramene l'etat d'origine.
        # Elle remonte donc jusqu'a _executer, qui rend le jeu.
        self.run.verifier_depart(*self.depart)
        derouler(self.run, sauts, jusqua, frontiere_turbo=frontiere)
        # derouler rend la main des que le heros sort du niveau, sans passer
        # par la frontiere : le turbo resterait allume sur un jeu en pause, et
        # la fenetre de MEmu figee jusqu'au prochain essai. Sans disparition,
        # la frontiere l'a deja coupe, ou il n'a jamais ete allume.
        if self.run.mort_a is not None:
            self.run.turbo(False)
        self._emettre_trace(f"try finished: paused at frame "
                            f"{self.run.image}")

    def _run_vivant(self) -> RunPilote:
        if self.run is None:
            raise RunError("no run in progress: Try first")
        return self.run

    def _avancer(self, sauts, jusqua) -> None:
        run = self._run_vivant()
        restants = [s for s in sauts if s not in run.entrees]
        derouler(run, restants, jusqua)
        self._emettre_trace(f"paused at frame {run.image}")

    def _sauter(self) -> None:
        run = self._run_vivant()
        if run.image in run.entrees:
            # Pas une erreur : rendre le jeu pour si peu tuerait le run.
            self._emettre("message", texte=f"a jump was already fired at "
                                           f"frame {run.image}")
            return
        image = run.sauter()
        self._emettre_trace(f"jump fired at frame {image}", saut=image)

    def _rejouer(self, movie) -> None:
        self._relancer_le_jeu()
        # Avant la navigation : inutile de faire naviguer l'operateur pour un
        # film qu'on refusera de toute facon.
        verifier_rejouable(movie, tuple(self.session.api.cycle()))
        self._attendre_navigation((movie.start.hero_x, movie.start.hero_y))
        self._un_passage(movie, 1)

    def _rejouer_encore(self, movie, numero: int) -> None:
        # Le run du passage precedent -- ou de l'essai qu'on vient de geler --
        # est encore en pause : le rendre laisse le jeu finir le donjon.
        self._rendre_le_jeu()
        # [J'y suis] ici aussi : apres une victoire, le jeu passe par l'ecran
        # d'apres-run, et c'est l'operateur qui ramene a l'ecran de
        # commencement. Pas de position attendue : la camera d'apres-run est
        # cadree 690 px plus loin.
        self._attendre_navigation(None)
        self._emettre("message", texte="waiting for the hero to settle...")
        Run(self.session.api, taper=lambda: None,
            dormir=self._dormir).attendre_repos()
        self._un_passage(movie, numero)

    def _un_passage(self, movie, numero: int) -> None:
        self.run = self._nouveau_run()
        try:
            self.run.ancrer()
            self.run.verifier_depart()
            derouler(self.run, [i.frame for i in movie.inputs],
                     movie.run_frames)
            obtenue = empreinte(encode(self.run.trace))
        finally:
            self._rendre_le_jeu()
        self._emettre("passage", numero=numero, empreinte=obtenue)

    def _liberer(self) -> None:
        # Pas de "jeu rendu" apres un "n'a pas pu etre rendu" : le bandeau se
        # contredirait.
        if self._rendre_le_jeu():
            self._emettre("message", texte="game returned to the operator")
