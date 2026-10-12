"""Un agent simule : la surface RPC, sans appareil ni jeu.

Il rend des enregistrements sur commande et sait faire disparaitre le heros,
ce qui permet de tester le deroulement d'un run -- y compris une mort -- sans
sortir de pytest.
"""

from controller.trace import Etat, decode, encode


class FauxApi:
    """La surface que `controller/run.py` utilise, et rien de plus.

    `trajectoire` est ce que le jeu "rendra", image par image. `mort_a` est
    l'indice a partir duquel le heros n'est plus lisible : l'agent compte
    alors des images absentes au lieu d'ecrire des enregistrements.
    """

    def __init__(self, trajectoire, mort_a=None, objets=1):
        self.trajectoire = list(trajectoire)
        self.mort_a = mort_a
        self.objets = objets
        self.curseur = 0
        self.en_attente = []
        self.absentes = 0
        self.appels = []
        self.en_pause = False
        self.enregistre = False
        self.horloge_active = False
        self.turbo_actif = False
        # Positions rendues par probe_state, une par appel, la derniere se
        # repetant. None : probe_state suit la trajectoire courante.
        self.positions_rendues = None
        self.etats_lus = 0

    def pause(self):
        self.en_pause = True
        self.appels.append("pause")
        return self.curseur

    def resume(self):
        self.en_pause = False
        self.appels.append("resume")
        return self.curseur

    def step(self, n):
        self.appels.append(("step", n))
        for _ in range(n):
            fini = self.mort_a is not None and self.curseur >= self.mort_a
            if fini or self.curseur >= len(self.trajectoire):
                self.absentes += 1
                continue
            self.en_attente.append(self.trajectoire[self.curseur])
            self.curseur += 1
        return self.curseur

    def probe_resolve(self):
        self.appels.append("probe_resolve")
        return {"vus": max(self.objets, 1), "objets": self.objets,
                "heros": "0x1"}

    def probe_state(self):
        if self.positions_rendues:
            indice = min(self.etats_lus, len(self.positions_rendues) - 1)
            self.etats_lus += 1
            x, y = self.positions_rendues[indice]
            return {"x": x, "y": y, "px": x, "py": y}
        if self.curseur == 0 or not self.trajectoire:
            return None
        etat = self.trajectoire[min(self.curseur, len(self.trajectoire)) - 1]
        return {"x": etat.x, "y": etat.y, "px": etat.x, "py": etat.y}

    def record_start(self):
        self.appels.append("record_start")
        self.enregistre = True
        self.en_attente = []
        self.absentes = 0

    def record_stop(self):
        self.enregistre = False

    def record_status(self):
        return {
            "enregistre": self.enregistre,
            "ecrits": len(self.en_attente),
            "deborde": False,
            "absentes": self.absentes,
            "ancre": 0,
            "frame": self.curseur,
        }

    def record_drain(self):
        octets = encode(self.en_attente)
        self.en_attente = []
        return octets

    def horloge(self, actif):
        self.appels.append(("horloge", bool(actif)))
        self.horloge_active = bool(actif)
        return self.horloge_active

    def rythme(self, ms):
        return ms

    def cycle(self):
        return [16, 17, 17]

    def turbo(self, actif):
        self.appels.append(("turbo", bool(actif)))
        self.turbo_actif = bool(actif)
        return self.turbo_actif


def chute(images, x=786.5624, y0=500.0, gravite=0.4183):
    """Une chute libre plausible, passee par l'encodage.

    L'aller-retour par encode/decode ramene les valeurs a ce qu'un float32
    peut porter : sans lui, les comparaisons de traces echoueraient sur des
    chiffres que l'agent n'aurait jamais pu produire.
    """
    etats = []
    vy = 0.0
    y = y0
    for k in range(images):
        etats.append(Etat(frame=k, x=x, y=y, vx=0.0, vy=vy))
        vy += gravite
        y += vy
    return decode(encode(etats))
