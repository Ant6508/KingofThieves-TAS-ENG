"""Ce que la seance affiche.

Formatage pur : ces fonctions rendent des chaines et ne savent pas ou elles
vont. Seule `ecrire_en_place` touche a un flux, et on lui passe lequel.
"""

from __future__ import annotations

import sys

from controller.trace import Etat

# Assez large pour la ligne d'etat complete. Sert a effacer ce qui precede
# quand la nouvelle ligne est plus courte que l'ancienne.
LARGEUR_LIGNE = 100


def ligne_etat(
    image: int,
    etat: Etat | None,
    sauts: int,
    en_pause: bool,
    turbo: bool = False,
) -> str:
    """La ligne reecrite en place a chaque avance.

    `etat` vaut None tant qu'aucune image n'a ete enregistree : on le dit,
    plutot que d'afficher des zeros qui passeraient pour des mesures.
    """
    if etat is None:
        mesures = "no frame recorded"
    else:
        mesures = (
            f"x={etat.x:10.4f} y={etat.y:10.4f} "
            f"vx={etat.vx:8.4f} vy={etat.vy:8.4f}"
        )
    mode = "PAUSE" if en_pause else "RUNNING"
    if turbo:
        mode += "+TURBO"
    return f"frame {image:5d} | {mesures} | {sauts} jump(s) | {mode}"


def ligne_saut(image: int, decollage: int) -> str:
    """Les deux images, toujours, pour qu'aucune convention ne reste implicite.

    Le film date le tap a l'image ou il est EMIS ; le heros decolle deux pas
    plus tard (NOTES.md, jalon 5, section 5).
    """
    return (
        f"jump placed at frame {image} -> liftoff expected at frame {decollage}"
    )


def ligne_sauts(sauts: list[int], index: int | None) -> str:
    """La liste des sauts du film, celui qu'on travaille entre crochets."""
    if not sauts:
        return "jumps  none -- Space places one at the current frame"
    marques = [
        f"[{image}]" if rang == index else f"{image}"
        for rang, image in enumerate(sauts)
    ]
    return "jumps  " + "  ".join(marques)


def ligne_decalage(rang: int, avant: int, apres: int, decollage: int) -> str:
    """Le mouvement d'un saut, avec l'image du decollage qui en decoule.

    `rang` est compte a partir de 1 : c'est un numero pour l'operateur, pas un
    indice de liste.
    """
    return (
        f"jump {rang}: {avant} -> {apres} "
        f"(liftoff expected at frame {decollage})"
    )


def ligne_issue(statut: str, image: int | None) -> str:
    if statut == "death":
        return f"the hero disappeared at frame {image}: the run stops there"
    return "run incomplete: the hero is still there"


def ligne_cible(cible) -> str:
    """La cible en clair, avec le sens de la marche dans le comparateur.

    L'operateur ne lit pas un signe : il lit "x doit descendre sous 605".

    Quatre decimales, comme `ligne_etat` en affiche pour la position du
    heros : l'operateur lit les deux sur la meme console, et un seuil arrondi
    a 605,2 en face d'un x=605,1900 se lirait comme atteint alors que le
    vrai seuil est 605,25. Le calcul, lui, a toujours ete exact -- c'est
    l'affichage qui cachait une precision que l'operateur a par ailleurs sous
    les yeux.
    """
    comparateur = ">=" if cible.sens == 1 else "<="
    return (
        f"target: {cible.axe} {comparateur} {cible.seuil:.4f} "
        f"before frame {cible.image_limite}"
    )


def ligne_balayage(faits: int, total: int, resultat, reussis: int) -> str:
    """L'avancement du balayage, reecrit en place a chaque essai.

    Attend un `resultat` mesure : `progression` a None leve une TypeError sur
    le format. Aucun chemin d'appel ne le produit -- les couples impossibles
    sont notes des la construction du Balayage, donc `prochain` ne les rend
    jamais et `balayer` ne dit que des resultats fraichement notes -- et
    l'echec bruyant vaut mieux qu'une ligne qui inventerait un chiffre.
    """
    couple = resultat.couple
    marque = "HIT" if resultat.reussi else "   "
    return (
        f"sweep {faits:3d}/{total:3d} | "
        f"({couple.precedent:+d},{couple.travaille:+d}) | "
        f"{resultat.progression:10.4f} | {marque} | {reussis} hit(s)"
    )


def lignes_podium(resultats) -> list[str]:
    """Les meilleurs essais, une chaine par ligne.

    Rend une liste et non une chaine a decouper, contrairement aux autres
    fonctions de ce module qui rendent chacune UNE ligne. Un `ligne_podium`
    qui joignait ses lignes obligeait l'appelant a les redecouper aussitot,
    et `ecrire_en_place` -- qui complete et tronque a LARGEUR_LIGNE -- ne
    sait de toute facon traiter qu'une ligne a la fois.
    """
    if not resultats:
        return ["no try measured"]
    lignes = ["podium:"]
    for rang, resultat in enumerate(resultats, 1):
        couple = resultat.couple
        marque = "  <-- reaches the target" if resultat.reussi else ""
        lignes.append(
            f"  {rang}. ({couple.precedent:+d},{couple.travaille:+d}) "
            f"progress {resultat.progression:.4f}{marque}"
        )
    return lignes


def aide() -> str:
    return (
        "n         +1 frame          Tab  +10 frames        P  play / pause\n"
        "Space     place a jump at the current frame\n"
        "up/down   pick the jump to work on\n"
        "left/right  shift that jump by one frame\n"
        "Backspace remove the selected jump\n"
        "F1        relaunch the game and start from an empty movie\n"
        "F2        quick try: no relaunch, turbo up to the worked jump\n"
        "F3        validation try: with relaunch, bit-exact\n"
        "F4        sweep the two jumps around the worked jump\n"
        "F5        write the movie     T  turbo     Q  quit"
    )


def ecrire_en_place(texte: str, sortie=None) -> None:
    """Reecrit la ligne courante du terminal.

    Le remplissage a LARGEUR_LIGNE efface la fin de la ligne precedente :
    sans lui, une ligne courte laisserait trainer la queue d'une longue.
    """
    sortie = sys.stdout if sortie is None else sortie
    sortie.write("\r" + texte.ljust(LARGEUR_LIGNE)[:LARGEUR_LIGNE])
    sortie.flush()
