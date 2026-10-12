# -*- coding: utf-8 -*-
"""tas.py - l'editeur de run.

Console au premier plan, MEmu visible a cote : les taps partent par adb, donc
le jeu n'a jamais besoin du focus.

Une seance commence par F1 : le jeu se relance, tu navigues jusqu'a l'ecran de
commencement, tu confirmes, et l'image 0 est la premiere image relachee.

Ensuite, la boucle : F2 rejoue le film depuis l'endroit ou le jeu vient de te
ramener -- en turbo jusqu'a trente images avant le saut travaille, puis a
vitesse normale. Tu regardes, tu decales d'une image, tu recommences. Deux
secondes par essai.

L'empreinte ne vient que de F3, qui relance le jeu : les deux chemins d'entree
ne donnent pas le meme etat d'ancrage -- 690 px d'ecart sur la position lue,
mesure du 2026-09-18 --, donc l'empreinte d'un essai rapide ne sera jamais
celle du film.

Usage :
    python scripts/tas.py
    python scripts/tas.py --film=films/mon_run.json --label="ma base"
"""

import os
import sys

# Lance depuis scripts/, la racine du depot n'est pas dans sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import frida  # noqa: E402

from controller.cible import (  # noqa: E402
    PAS_DE_CIBLE_PX,
    CibleError,
    proposer_cible,
)
from controller.depart import confirmer_le_depart  # noqa: E402
from controller.device import PACKAGE  # noqa: E402
from controller.film_edite import EditionError, FilmEdite  # noqa: E402
from controller.hud import (  # noqa: E402
    LARGEUR_LIGNE,
    aide,
    ecrire_en_place,
    ligne_balayage,
    ligne_cible,
    ligne_decalage,
    ligne_etat,
    ligne_sauts,
    lignes_podium,
)
from controller.keys import frappe_en_attente, lire_touche  # noqa: E402
from controller.movie import (  # noqa: E402
    GameBuild,
    Movie,
    StartConditions,
    TapInput,
    save_movie,
)
from controller.relance import relancer  # noqa: E402
from controller.run import AncrageError, Run, derouler  # noqa: E402
from controller.session import (  # noqa: E402
    EXPECTED_VERSION_CODE,
    EXPECTED_VERSION_NAME,
    Session,
)
from controller.solveur import (  # noqa: E402
    RAYON_PRECEDENT,
    RAYON_TRAVAILLE,
    Balayage,
    Couple,
    balayer,
    espace,
)
from controller.trace import empreinte, encode  # noqa: E402

DT = 1.0 / 60.0

CHEMIN = "films/run.json"
LABEL = ""
for _arg in sys.argv[1:]:
    if _arg.startswith("--film="):
        CHEMIN = _arg.split("=", 1)[1]
    elif _arg.startswith("--label="):
        LABEL = _arg.split("=", 1)[1]

MORTES = (frida.InvalidOperationError, frida.TransportError)


class Seance:
    """Une seance d'edition : un film, un curseur, et un run en cours."""

    def __init__(self, session, chemin, label=""):
        self.session = session
        self.chemin = chemin
        self.label = label
        # Position du heros a l'ecran de commencement, relevee a la premiere
        # prise. Sert au film, et au controle de l'image 0 en validation.
        self.depart = None
        # Position lue a l'image 0 des essais rapides. Elle n'est pas celle du
        # film : les deux chemins d'entree ne donnent pas le meme cadrage de
        # camera, donc pas la meme coordonnee. Apprise au premier F2.
        self.depart_boucle = None
        self.film = FilmEdite()
        self.run = None
        # Nombre d'images que rejoue un essai. Grandit quand l'operateur
        # prolonge le run au-dela de ce qu'il avait atteint.
        self.longueur = 0
        # Ecrite par un essai de validation, effacee par toute edition.
        self.empreinte = None
        self.en_pause = True
        self.turbo = False
        # Un balayage en cours, garde entre deux appuis sur F4 : un balayage
        # arrete par un ancrage douteux reprend ou il en etait. Efface par
        # toute edition, qui rendrait ses sauts de depart faux.
        self.balayage = None
        self.cible = None
        # La trace en memoire est-elle celle d'un essai que l'operateur a
        # REGARDE ? Un balayage remplace self.run a chaque couple, donc il
        # laisse derriere lui la trace de son dernier essai -- un coin de
        # l'espace de recherche, joue en turbo plein, que personne n'a vu, et
        # qui porte un film different de celui qu'on vient d'appliquer.
        # proposer_cible promet de lire "l'essai que l'operateur vient de
        # regarder" : sans ce drapeau, elle rendrait une cible valide et
        # fausse, et il n'a aucun moyen de s'en apercevoir puisqu'il ne
        # connait pas les coordonnees du niveau.
        self.trace_regardee = False

    # ----- affichage -----

    @property
    def image(self):
        return self.run.image if self.run else 0

    def dernier_etat(self):
        if self.run is None or not self.run.etats:
            return None
        return self.run.etats[-1]

    def afficher(self):
        ligne = ligne_etat(self.image, self.dernier_etat(),
                           len(self.film.sauts), self.en_pause, self.turbo)
        if self.film.sauts and self.empreinte is None:
            ligne += "  [not validated]"
        ecrire_en_place(ligne)

    def dire(self, texte):
        """Une ligne durable, au-dessus de la ligne d'etat reecrite."""
        print("\r" + texte.ljust(LARGEUR_LIGNE))
        self.afficher()

    def montrer_les_sauts(self):
        self.dire(ligne_sauts(self.film.sauts, self.film.index))

    # ----- ancrage -----

    def _relancer_et_confirmer(self):
        self.session.detach()
        self.dire("relaunching the game...")
        relancer()
        self.session.attacher_avec_reessais()
        # `dire` local et non self.dire : l'invite doit rester la derniere
        # ligne ecrite, sinon la ligne d'etat se reecrit par-dessus.
        self.depart = confirmer_le_depart(
            self.session.api, attendu=self.depart,
            dire=lambda t: print("\r" + t.ljust(LARGEUR_LIGNE)))

    def _ancrer(self, attendu):
        """Ancre un nouvel essai et controle qu'on part bien du meme endroit.

        L'essai precedent est rendu ici et non a sa propre fin : sa barriere
        restait fermee sur sa derniere image, ce qui laissait l'operateur
        prolonger le run image par image.

        `attendu` est la position que le heros doit porter a l'image 0, ou None
        au premier essai d'une boucle, quand personne ne sait encore laquelle
        attendre. Rend la position relevee, pour que l'appelant l'apprenne.
        """
        if self.run is not None:
            self.run.terminer()
            # Le jeu finit de jouer la mort et de remettre le niveau en place.
            # Ancrer pendant ce temps produit une trace divergente des
            # l'image 0 -- mesure du 2026-09-18.
            self.dire("waiting for the hero to settle...")
            Run(self.session.api, taper=lambda: None).attendre_repos()

        self.run = Run(self.session.api)
        self.run.ancrer()
        self.turbo = False
        self.en_pause = True
        if attendu is None:
            etat = self.run.verifier_depart()
        else:
            etat = self.run.verifier_depart(attendu[0], attendu[1])
        return (etat.x, etat.y)

    # ----- essais -----

    def nouvelle_prise(self):
        self._relancer_et_confirmer()
        self.film = FilmEdite()
        self.longueur = 0
        self.empreinte = None
        self.depart_boucle = None
        self.balayage = None
        self.cible = None
        self.trace_regardee = False
        self._ancrer((self.depart[0], self.depart[1]))
        self.dire("new take: frame 0, no jump")

    def _derouler(self, frontiere):
        derouler(self.run, self.film.sauts, self.longueur,
                 frontiere_turbo=frontiere)
        self.longueur = max(self.longueur, self.run.image)

    def essai_rapide(self):
        if self.depart is None:
            return self.dire("no take: F1 to start")
        # Le premier essai rapide de la seance releve le point d'ancrage de la
        # boucle ; les suivants s'y comparent.
        self.depart_boucle = self._ancrer(self.depart_boucle)
        self._derouler(self.film.frontiere_turbo())
        self.empreinte = None
        self.trace_regardee = True
        self.dire(f"try: {self.run.image} frames, "
                  f"{len(self.film.sauts)} jump(s)")

    def validation(self):
        if self.depart is None:
            return self.dire("no take: F1 to start")
        if self.run is not None:
            self.run.terminer()
            self.run = None
        self._relancer_et_confirmer()
        self.depart_boucle = None   # la relance rouvre une autre boucle
        self._ancrer((self.depart[0], self.depart[1]))
        self._derouler(None)     # vitesse normale de bout en bout
        self.empreinte = empreinte(encode(self.run.trace))
        self.trace_regardee = True
        self.dire(f"validation: {self.run.image} frames")
        self.dire(f"   {self.empreinte}")

    # ----- balayage -----

    def _essayer_sauts(self, sauts):
        """Un essai rapide sur une liste de sauts donnee, turbo plein.

        Turbo d'un bout a l'autre et non jusqu'au saut travaille : personne ne
        regarde, et l'essai retombe sous la seconde.

        `_ancrer` leve AncrageError si le heros n'est pas a l'image 0 la ou il
        etait aux essais precedents. On ne la rattrape pas : elle traverse
        `balayer` et arrete tout.
        """
        self.depart_boucle = self._ancrer(self.depart_boucle)
        self.trace_regardee = False
        self.turbo = self.run.turbo(True)
        derouler(self.run, sauts, self.longueur, frontiere_turbo=None)
        return self.run.trace

    def _regler_la_cible(self):
        """Propose une cible et laisse l'operateur la deplacer.

        Rend la cible validee, ou None s'il annule. La proposition dit "la ou
        ton dernier essai s'est arrete" : il n'a jamais a connaitre les
        coordonnees du niveau, il la pousse plus loin.
        """
        cible = proposer_cible(self.run.trace)
        print()
        # Les deux amplitudes, pour que l'operateur voie si le choix d'axe
        # etait net. Il ne connait pas les coordonnees du niveau : sans ce
        # chiffre, une cible posee sur le mauvais axe ne se distingue pas
        # d'une bonne.
        ecart_x = (max(e.x for e in self.run.trace)
                   - min(e.x for e in self.run.trace))
        ecart_y = (max(e.y for e in self.run.trace)
                   - min(e.y for e in self.run.trace))
        print(f"try ranges: x={ecart_x:.1f}  y={ecart_y:.1f}"
              f"   --   axis chosen: {cible.axe}")
        print(f"left/right: move by {PAS_DE_CIBLE_PX:.0f} px"
              f"   --   Enter: start   --   Esc: cancel")
        while True:
            ecrire_en_place(ligne_cible(cible))
            action = lire_touche()
            if action == "quitter":
                print()
                return None
            if action == "entree":
                print()
                return cible
            if action == "avancer_saut":
                cible = cible.deplacee(PAS_DE_CIBLE_PX)
            elif action == "reculer_saut":
                cible = cible.deplacee(-PAS_DE_CIBLE_PX)

    def _interrompu(self):
        """Echap entre deux essais arrete le balayage.

        `frappe_en_attente` d'abord : sans elle, il faudrait bloquer sur une
        frappe a chaque essai.
        """
        if not frappe_en_attente():
            return False
        return lire_touche() == "quitter"

    def _dire_balayage(self, balayage, resultat):
        ecrire_en_place(ligne_balayage(balayage.faits, balayage.total,
                                       resultat, len(balayage.reussis)))

    def _balayage_perime(self):
        """Pourquoi le balayage en cours ne peut plus etre repris, ou None.

        Un balayage fige a sa construction le saut qu'il travaille et la
        longueur du run. Deux choses peuvent les dementir SANS passer par
        `_edite`, qui l'aurait efface :

        - les fleches haut et bas deplacent le curseur. Ce ne sont pas des
          editions, donc le balayage survit -- et il continuerait a travailler
          le saut sur lequel il a ete ouvert pendant que l'ecran surligne un
          autre. L'operateur n'a aucun moyen de voir l'ecart.
        - une avance manuelle allonge le run. La borne figee reste alors plus
          petite, et des couples que le run plus long rendrait valides restent
          ecartes -- un `total` qui ment par le bas, en silence.

        Le second ecart est conservateur, le premier ne l'est pas. Les deux
        sont invisibles, et c'est ce qui les rend inacceptables : on refuse.
        """
        if self.balayage is None or self.balayage.prochain() is None:
            return None
        if (self.balayage.index != self.film.index
                or self.balayage.sauts != self.film.sauts):
            travaille = self.balayage.sauts[self.balayage.index]
            return (f"the current sweep works on the jump at frame "
                    f"{travaille}, and the cursor points at frame "
                    f"{self.film.choisi}. Move the cursor back onto it to "
                    f"resume, or edit a jump to drop the sweep.")
        if self.balayage.images != self.longueur:
            return (f"the run is now {self.longueur} frames long, versus "
                    f"{self.balayage.images} when the sweep was opened: "
                    f"its bound is stale and valid pairs would stay "
                    f"excluded. Edit a jump to drop the sweep, then F4.")
        return None

    def balayer(self):
        """F4 : cherche seul un couple de sauts qui atteint la cible."""
        if self.depart is None:
            return self.dire("no take: F1 to start")
        if self.run is None or not self.run.etats:
            return self.dire("no try: F2 first, a trace is needed "
                             "to propose a target")
        if self.film.choisi is None:
            return self.dire("no jump to sweep: the movie is empty")
        # Ce controle ne porte que sur l'OUVERTURE d'un balayage, pas sur sa
        # reprise : reprendre reutilise la cible deja validee et ne relit
        # aucune trace.
        if self.balayage is None and not self.trace_regardee:
            return self.dire(
                "the trace in memory is from the last try of the previous "
                "sweep -- full turbo, nobody watched it, and the movie has "
                "changed since. F2 for a try to watch, then F4.")

        perime = self._balayage_perime()
        if perime is not None:
            return self.dire(perime)

        if self.balayage is None or self.balayage.prochain() is None:
            try:
                cible = self._regler_la_cible()
            except CibleError as erreur:
                return self.dire(str(erreur))
            if cible is None:
                return self.dire("sweep cancelled")
            self.cible = cible
            # Sans saut avant celui qu'on travaille, la premiere dimension n'a
            # rien a decaler : 42 couples sur 49 seraient impossibles.
            rayon_p = RAYON_PRECEDENT if self.film.index > 0 else 0
            # `longueur` borne le balayage par le haut : un couple qui
            # pousserait un saut au-dela serait avale en silence par derouler,
            # et son essai ampute compterait comme un essai normal.
            self.balayage = Balayage(self.film.sauts, self.film.index,
                                     self.longueur,
                                     espace(rayon_p, RAYON_TRAVAILLE))
            self.dire(f"sweep of {self.balayage.total} pair(s) -- "
                      f"{ligne_cible(self.cible)}")

        try:
            fin = balayer(self.balayage, self._essayer_sauts, self.cible,
                          dire=self._dire_balayage,
                          interrompu=self._interrompu)
        except (AncrageError, CibleError) as erreur:
            # CibleError arrive ici quand un essai n'a pas bouge d'une image :
            # le heros n'a pas recu son tap, ou l'ancrage a rate sans que le
            # controle de position s'en apercoive. C'est le meme diagnostic
            # qu'un ancrage douteux, donc la meme conduite -- on ne tape plus.
            #
            # Le jeu est reste en pause, horloge virtuelle active et barriere
            # fermee, sur l'essai fautif. Lui rendre son temps reel AVANT de
            # demander a l'operateur de renaviguer : sans ca il regarderait une
            # fenetre figee en croyant l'outil casse.
            self.run.terminer()
            self.turbo = False
            self.en_pause = False
            self.dire(str(erreur))
            return self.dire(
                f"sweep stopped: navigate again to the starting "
                f"screen, F4 will resume the "
                f"{len(self.balayage.restants())} remaining pair(s)")

        etat_fin = {"termine": "finished", "interrompu": "interrupted"}
        self.dire(f"sweep {etat_fin.get(fin, fin)}: "
                  f"{self.balayage.faits} try(s), "
                  f"{len(self.balayage.reussis)} hit(s)")
        for ligne in lignes_podium(self.balayage.podium()):
            self.dire(ligne)

        if fin == "interrompu":
            return self.dire(
                f"F4 resumes the {len(self.balayage.restants())} remaining "
                f"pair(s). The movie hasn't changed.")

        self._appliquer_le_meilleur()
        # Le balayage est fini : il tombe ici et non dans `_appliquer_le_
        # meilleur`, dont deux branches rendent la main sans editer -- aucun
        # essai mesure, ou un couple (0, 0) qui ne touche a rien. La garantie
        # "la cible et le balayage vivent et meurent ensemble" ne doit pas
        # dependre du chemin qu'a pris l'application du meilleur.
        self.balayage = None
        self.cible = None

    def _appliquer_le_meilleur(self):
        """Pose le meilleur couple sur le film et rend la main a l'editeur.

        "Le meilleur" est celui de plus grande progression, qu'il ait atteint
        la cible ou non : un balayage entierement rate laisse l'operateur sur
        le moins mauvais essai, et le dit. Si c'est (0, 0), rien ne bouge et
        l'empreinte reste valide -- aucune edition n'a eu lieu.
        """
        meilleur = self.balayage.meilleur()
        if meilleur is None:
            return self.dire("no try measured: nothing to apply")
        if meilleur.couple == Couple(0, 0):
            return self.dire("the movie was already the best try: "
                             "it stays as is")

        sauts = self.balayage.sauts_de(meilleur.couple)
        travaillee = self.balayage.image_travaillee(meilleur.couple)
        self.film = FilmEdite(sauts)
        self.film.choisir(travaillee)
        verdict = "reaches the target" if meilleur.reussi else "the least bad"
        self.dire(f"applied: ({meilleur.couple.precedent:+d},"
                  f"{meilleur.couple.travaille:+d}) -- {verdict}. "
                  f"F3 to validate.")
        self._edite()

    # ----- deplacement dans le run -----

    def avancer(self, n):
        if self.run is None:
            return self.dire("no take: F1 to start")
        if not self.en_pause:
            self.basculer_pause()
        self.run.avancer(n)
        self.longueur = max(self.longueur, self.run.image)

    def basculer_pause(self):
        if self.run is None:
            return self.dire("no take: F1 to start")
        if self.en_pause:
            self.run.relacher()
            self.en_pause = False
            self.dire("running freely -- P to freeze")
        else:
            self.run.figer()
            self.en_pause = True
            self.longueur = max(self.longueur, self.run.image)
            self.dire(f"frozen at frame {self.image}")

    def basculer_turbo(self):
        if self.run is None:
            return self.dire("no take: F1 to start")
        self.turbo = self.run.turbo(not self.turbo)
        self.dire("turbo on" if self.turbo else "turbo off")

    # ----- edition du film -----

    def _edite(self):
        """Toute edition invalide l'empreinte : elle ne decrit plus ce film.

        Et elle invalide le balayage en cours : celui-ci porte la liste de
        sauts sur laquelle il a ete ouvert, donc ses couples ne designeraient
        plus les memes essais.

        La cible tombe avec lui, et les deux ne se separent jamais : un
        balayage repris avec une autre cible que celle qui a produit ses
        premiers resultats melangerait deux classements dans un seul podium,
        sans que rien ne le signale. Ils vivent et meurent ensemble.
        """
        self.empreinte = None
        self.balayage = None
        self.cible = None
        self.montrer_les_sauts()

    def sauter(self):
        if self.run is None:
            return self.dire("no take: F1 to start")
        if not self.en_pause:
            self.basculer_pause()
        image = self.run.sauter()
        self.longueur = max(self.longueur, self.run.image)
        try:
            self.film.poser(image)
        except EditionError as erreur:
            return self.dire(str(erreur))
        self._edite()

    def annuler(self):
        retire = self.film.retirer()
        if retire is None:
            return self.dire("no jump to remove")
        self.dire(f"jump at frame {retire} removed -- F2 to replay without it")
        self._edite()

    def choisir_precedent(self):
        self.film.precedent()
        self.montrer_les_sauts()

    def choisir_suivant(self):
        self.film.suivant()
        self.montrer_les_sauts()

    def decaler(self, pas):
        avant = self.film.choisi
        if avant is None:
            return self.dire("no jump to shift: the movie is empty")
        try:
            apres = self.film.decaler(pas)
        except EditionError as erreur:
            return self.dire(str(erreur))
        self.dire(ligne_decalage(self.film.index + 1, avant, apres,
                                 Run.decollage(apres)))
        self._edite()

    # ----- ecriture -----

    def ecrire(self):
        if self.run is None or not self.run.etats:
            return self.dire("nothing to write: no frame recorded")
        if self.empreinte is None:
            return self.dire(
                "movie without a fingerprint: a validation try (F3) first. "
                "A quick try doesn't start from a relaunched game, so its "
                "fingerprint would prove nothing.")
        au_dela = [n for n in self.film.sauts if n > self.longueur]
        if au_dela:
            return self.dire(
                f"{len(au_dela)} jump(s) after frame {self.longueur} where "
                f"the run stops: {au_dela}. Advance that far, or remove them.")

        # Ni la victoire ni la mort ne sont observables (NOTES.md du
        # 2026-09-18 : un heros tue reste en memoire). C'est l'operateur qui
        # qualifie son run.
        print()
        reponse = input("outcome? (w)in / (d)eath / (i)ncomplete [i]: ")
        statut = {"w": "win", "d": "death"}.get(reponse.strip().lower()[:1],
                                               "incomplete")

        movie = Movie(
            game=GameBuild(PACKAGE, EXPECTED_VERSION_NAME,
                           EXPECTED_VERSION_CODE),
            dt=DT,
            run_frames=self.longueur,
            start=StartConditions(relaunch=True, tap_demarrage=True,
                                  hero_x=self.depart[0],
                                  hero_y=self.depart[1]),
            clock_cycle_ms=tuple(self.session.api.cycle()),
            run_label=self.label,
            inputs=[TapInput(frame=n) for n in self.film.sauts],
            outcome_status=statut,
            outcome_frame=None,
            fingerprint=self.empreinte,
        )
        save_movie(movie, self.chemin)
        self.dire(f"movie written: {self.chemin} -- {len(movie.inputs)} jump(s), "
                  f"{movie.run_frames} frames, outcome {statut}")

    def fermer(self):
        print()
        if self.run is not None:
            try:
                self.run.terminer()
            except MORTES:
                pass   # la session est morte avec le jeu : rien a rendre
        self.session.detach()
        print("session over. The game is back to real time.")


def main():
    seance = Seance(Session(), CHEMIN, LABEL)

    print(aide())
    print()
    print("F1 to start.")
    seance.afficher()

    actions = {
        "relance": seance.nouvelle_prise,
        "essai": seance.essai_rapide,
        "validation": seance.validation,
        "balayage": seance.balayer,
        "avance": lambda: seance.avancer(1),
        "avance10": lambda: seance.avancer(10),
        "saut": seance.sauter,
        "annuler": seance.annuler,
        "saut_precedent": seance.choisir_precedent,
        "saut_suivant": seance.choisir_suivant,
        "reculer_saut": lambda: seance.decaler(-1),
        "avancer_saut": lambda: seance.decaler(+1),
        "pause": seance.basculer_pause,
        "turbo": seance.basculer_turbo,
        "ecrire": seance.ecrire,
    }

    try:
        while True:
            action = lire_touche()
            if action == "quitter":
                break
            if action in actions:
                actions[action]()
                seance.afficher()
    except KeyboardInterrupt:
        pass
    finally:
        seance.fermer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
