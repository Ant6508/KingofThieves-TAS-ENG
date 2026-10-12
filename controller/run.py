"""Derouler un run : ancrage, avance image par image, taps dates a l'image.

Unique endroit qui sait dans quel ordre parler a l'agent. La seance
interactive et le rejeu automatique s'en servent tous les deux : c'est ce qui
garantit qu'un run enregistre et un run rejoue suivent la meme sequence
d'appels. Sans cette garantie, comparer leurs empreintes ne voudrait rien
dire.

Le controleur ne connait aucune adresse memoire ; il ne parle a l'agent que
par RPC.
"""

from __future__ import annotations

import time

from controller import entree
from controller.trace import Etat, decode

# Images entre l'emission d'un tap et le pas de simulation qui le recoit.
# Mesure du 2026-09-18 : un tap date a l'image N atteint le pas N + 2, trois
# predictions sur trois. Voir NOTES.md, jalon 5, section 5.
LATENCE_TAP_IMAGES = 2

# Temps reel au-dela duquel on considere que le jeu n'avance plus.
ATTENTE_MAX = 30.0

PAS_DE_SCRUTATION = 0.05


class RunError(Exception):
    """Le run ne peut pas se derouler."""


class AncrageError(RunError):
    """L'ancrage a echoue : on n'est pas la ou on croit."""


class Run:
    """Un run en cours : sa trace, ses entrees, et son issue."""

    def __init__(
        self,
        api,
        taper=entree.taper,
        dormir=time.sleep,
        attente_max: float = ATTENTE_MAX,
    ) -> None:
        self.api = api
        self._taper = taper
        self._dormir = dormir
        self.attente_max = attente_max
        self.etats: list[Etat] = []
        self.entrees: list[int] = []
        self.mort_a: int | None = None
        self._absentes = 0

    @property
    def image(self) -> int:
        """Numero de la prochaine image a enregistrer.

        Egal au nombre d'images deja enregistrees, les images etant numerotees
        depuis zero.
        """
        return len(self.etats)

    @property
    def trace(self) -> list[Etat]:
        return list(self.etats)

    def ancrer(self) -> dict:
        """Ferme la barriere sur l'ecran de commencement et demarre le run.

        L'ordre compte, et chaque etape supprime une source de variance :

        1. `pause` : le temps de jeu s'arrete, tout ce qui suit est gratuit ;
        2. `horloge` : le delta de frame est impose, et sa phase repart de
           zero avec le run (voir agent/pump.js) ;
        3. `probe_resolve` : 0,7 s de temps reel, zero image de jeu ;
        4. `record_start` : la prochaine image relachee portera le numero 0 ;
        5. le tap de demarrage, emis barriere fermee.

        Rien entre 4 et 5 ne laisse passer une image : le tap de demarrage est
        donc date de l'image 0 par construction.
        """
        self.api.pause()
        self.api.rythme(0)
        self.api.horloge(True)

        resolution = self.api.probe_resolve()
        if resolution["objets"] != 1:
            raise AncrageError(
                f"exactly one hero is expected at the starting screen, "
                f"found {resolution['objets']} out of {resolution['vus']} "
                f"objects carrying the vtable. The navigation didn't land, "
                f"or the game changed menus: take over with the mouse and "
                f"start again."
            )

        self.api.record_start()
        self._taper()
        return resolution

    def avancer(self, images: int) -> list[Etat]:
        """Relache `images` images et rend celles qui ont ete enregistrees.

        En rend moins que demande si le heros disparait de la memoire : ce
        n'est pas une panne, c'est la fin de ce qu'on peut enregistrer. Ce
        n'est pas une mort non plus -- voir issue().
        """
        if images <= 0 or self.mort_a is not None:
            return []

        self.api.step(images)
        etat = self._attendre(images)
        nouveaux = decode(self.api.record_drain())
        self.etats.extend(nouveaux)

        if etat["absentes"] > self._absentes:
            self._absentes = etat["absentes"]
            self.mort_a = len(self.etats)
            self.api.pause()
        return nouveaux

    def rattraper(self) -> list[Etat]:
        """Draine ce que l'agent a enregistre sans qu'on l'ait cadence.

        Sert apres une marche libre : le jeu a tourne a sa propre vitesse, et
        la trace doit rattraper ce qui s'est passe.
        """
        nouveaux = decode(self.api.record_drain())
        self.etats.extend(nouveaux)
        return nouveaux

    def relacher(self) -> None:
        """Rend le jeu a sa vitesse, l'enregistrement continuant."""
        self.api.resume()

    def figer(self) -> list[Etat]:
        """Referme la barriere et ramasse les images de la marche libre."""
        self.api.pause()
        return self.rattraper()

    def turbo(self, actif: bool) -> bool:
        """Allume ou coupe la neutralisation d'eglSwapBuffers.

        `terminer` la coupe de toute facon : un run interrompu ne doit jamais
        rendre la main sur une fenetre figee.
        """
        return bool(self.api.turbo(actif))

    def verifier_depart(self, x: float | None = None, y: float | None = None,
                        tolerance: float = 0.5) -> Etat:
        """Avance d'une image et rend l'etat du heros a l'image 0.

        Sans `x` ni `y`, se contente de relever : c'est le premier essai d'une
        boucle, ou personne ne sait encore quelle position attendre. Avec eux,
        verifie que le heros y est.

        Rien ne distingue l'ecran de commencement du menu principal : la sonde
        rend un heros et un seul dans les deux cas, et sa position suit le
        cadrage de la camera (spec 1 ter I). Mais deux runs comparables portent
        la meme position a l'image 0 -- verifie sur tous les rejeux du
        2026-09-18.

        Ce controle coute une image et attrape en vingt millisecondes ce qui,
        sans lui, se decouvre au bout de dix secondes de trace vide.
        """
        nouveaux = self.avancer(1)
        if not nouveaux:
            raise AncrageError(
                "no frame recorded at the anchor: the game no longer "
                "renders frames, or the hero is already unreadable"
            )
        etat = nouveaux[0]
        if x is None or y is None:
            return etat
        if abs(etat.x - x) > tolerance or abs(etat.y - y) > tolerance:
            raise AncrageError(
                f"at frame 0 the hero is at ({etat.x}, {etat.y}), but was "
                f"expected at ({x}, {y}). The anchor landed elsewhere: let "
                f"the game return to its starting point and start again."
            )
        return etat

    def attendre_repos(self, stable: int = 3, pas: float = 0.3,
                       maximum: float = 20.0) -> tuple[float, float]:
        """Attend que le heros cesse de bouger, jeu en marche libre.

        Apres un essai, le jeu finit de jouer la mort et de remettre le niveau
        en place. Ancrer pendant ce temps produit une trace divergente des
        l'image 0 -- mesure du 2026-09-18.

        Le heros au repos a une vitesse exactement nulle (NOTES.md, "Vitesse au
        repos"), donc l'attente ne demande de connaitre ni le niveau ni la
        position : on attend que la position cesse de changer.

        `probe_state` d'abord, qui ne coute rien ; `probe_resolve` seulement
        s'il rend None, parce que le niveau a pu reconstruire son heros. Une
        resolution a chaque tour couterait 0,7 s.
        """
        precedente = None
        immobiles = 0
        debut = time.monotonic()
        while time.monotonic() - debut < maximum:
            etat = self.api.probe_state()
            if etat is None:
                self.api.probe_resolve()
                etat = self.api.probe_state()
            position = None if etat is None else (etat["x"], etat["y"])

            if position is not None and position == precedente:
                immobiles += 1
                if immobiles >= stable:
                    return position
            else:
                immobiles = 0
            precedente = position
            self._dormir(pas)

        raise RunError(
            f"the hero is still moving after {maximum:.0f} s: the level "
            f"won't stop replaying, or the game is elsewhere"
        )

    def _attendre(self, attendues: int) -> dict:
        debut = time.monotonic()
        while time.monotonic() - debut < self.attente_max:
            etat = self.api.record_status()
            if etat["deborde"]:
                raise RunError(
                    "the agent's buffer overflowed: the run is too long "
                    "for a single advance"
                )
            if etat["ecrits"] >= attendues or etat["absentes"] > self._absentes:
                return etat
            self._dormir(PAS_DE_SCRUTATION)
        raise RunError(
            f"{self.api.record_status()['ecrits']} frames out of {attendues} "
            f"after {self.attente_max:.0f} s. Is the game in the "
            f"background, or frozen somewhere other than the barrier?"
        )

    def sauter(self) -> int:
        """Emet un tap barriere fermee, et le date de l'image courante."""
        if self.mort_a is not None:
            raise RunError(
                f"the hero has been unreadable since frame {self.mort_a}: "
                f"nothing left to make jump"
            )
        self._taper()
        self.entrees.append(self.image)
        return self.image

    @staticmethod
    def decollage(image: int) -> int:
        return image + LATENCE_TAP_IMAGES

    def issue(self) -> tuple[str, int | None]:
        """L'issue telle qu'on peut l'observer, sans la deviner.

        `disparu` ne veut pas dire `mort` : mesure du 2026-09-18, un heros tue
        par un piege reste parfaitement lisible en memoire, et le run continue
        de s'enregistrer. La disparition de l'objet signale donc une sortie du
        niveau, pas une mort -- et une mort ne la declenche pas.

        Ni la victoire ni la mort ne sont observables ici : c'est l'operateur
        qui qualifie son run. Ce que l'outil sait dire, c'est "le heros n'est
        plus lisible, on ne peut plus rien enregistrer".
        """
        if self.mort_a is not None:
            return ("disparu", self.mort_a)
        return ("incomplete", None)

    def terminer(self) -> None:
        """Rend le jeu a l'operateur, quoi qu'il arrive.

        Un run rate ne doit jamais laisser la partie figee, ni le temps de jeu
        detache du temps reel, ni la fenetre sans synchronisation verticale.
        """
        try:
            self.api.record_stop()
        finally:
            self.api.turbo(False)
            self.api.horloge(False)
            self.api.resume()


def derouler(run: Run, entrees: list[int], images: int,
             frontiere_turbo: int | None = None) -> list[Etat]:
    """Deroule un run : avance, tape aux images voulues, coupe le turbo.

    Les numeros sont des images d'EMISSION du tap. Le tap part quand le
    compteur d'images enregistrees les atteint, barriere fermee.

    Le deroule reprend a l'image ou le run en est, et non a zero : le controle
    de l'image 0 en a deja consomme une.

    `frontiere_turbo` est l'image ou le turbo doit se couper. Le turbo ne
    s'allume que s'il reste vraiment quelque chose a passer en vitesse rapide :
    l'allumer pour une frontiere deja depassee ne l'eteindrait jamais.
    """
    taps = [n for n in sorted(entrees) if n < images]
    faites = run.image

    arrets = set(taps)
    if frontiere_turbo is not None and faites < frontiere_turbo < images:
        arrets.add(frontiere_turbo)
        run.turbo(True)
    else:
        frontiere_turbo = None

    for numero in sorted(arrets):
        if numero < faites:
            continue
        if numero > faites:
            run.avancer(numero - faites)
            faites = numero
        if run.mort_a is not None:
            return run.trace
        if numero == frontiere_turbo:
            run.turbo(False)
        if numero in taps:
            run.sauter()

    if images > faites:
        run.avancer(images - faites)
    return run.trace
