"""Attache Frida au jeu et charge l'agent.

Refuse de demarrer si la version installee n'est pas celle attendue : un agent
qui pointe sur de mauvaises adresses fait plus de degats qu'un agent qui ne
demarre pas.
Version et adresses : la table du noyau (kotnoyau).
"""

from __future__ import annotations

import threading
import time

import frida
from kotnoyau.frida_ import charger_agent
from kotnoyau.table import Table, VersionInconnue, disponibles

from controller.agent import build_agent_source
from controller.device import (
    PACKAGE,
    DeviceError,
    GameNotRunning,
    active_serial,
    ensure_frida_server_running,
    game_pid,
    installed_version,
    message_frida_discordant,
)


def version_attendue() -> tuple[str, int]:
    """(versionName, versionCode) de la table la plus recente du noyau : la version des films enregistres."""
    t = Table.derniere()
    return t.nom, t.code


class SessionError(Exception):
    """L'attache ou le chargement de l'agent a echoue."""


class Session:
    def __init__(self, package: str = PACKAGE) -> None:
        self.package = package
        self.session: frida.core.Session | None = None
        self.script: frida.core.Script | None = None
        self.table: Table | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def verifier_frida(self) -> None:
        """Refuse un frida installe qui n'est pas celui de frida-server.

        Sinon l'attache echoue plus loin sur une erreur de protocole qui ne
        dit pas que la cause est une version.
        """
        discordance = message_frida_discordant(frida.__version__)
        if discordance is not None:
            raise SessionError(discordance)

    def check_version(self) -> None:
        """La table d'adresses du jeu installe, ou un refus avant toute attache."""
        name, code = installed_version(self.package)
        try:
            self.table = Table.pour(code, name)
        except VersionInconnue as exc:
            connues = ", ".join(str(c) for c in disponibles())
            raise SessionError(
                f"unexpected game version: {name} (versionCode {code}); the "
                f"core address table only knows versionCode {connues}. Run "
                f"`python -m kotnoyau.retrouver` to build the next one."
            ) from exc

    def _attach_to(self, device):
        """Attache par nom, puis par pid. Voir kot_headless/docs/savoir/methodes/frida.md :
        le nom ne suffit pas.

        Un DeviceError qui n'est pas GameNotRunning vient d'un echec adb
        (hors ligne, non autorise, serveur adb mort...) : on le laisse
        remonter tel quel, il ne veut pas dire que le jeu est arrete.
        """
        try:
            return device.attach(self.package)
        except frida.ProcessNotFoundError:
            try:
                pid = game_pid(self.package)
            except GameNotRunning as exc:
                raise SessionError(
                    f"{self.package} isn't running. Launch the game in MEmu."
                ) from exc

            try:
                return device.attach(pid)
            except frida.ProcessNotFoundError as exc:
                raise SessionError(
                    f"{self.package} (pid {pid}) disappeared between the "
                    "pid lookup and the attach. Try again."
                ) from exc

    def attach(self) -> None:
        self.verifier_frida()
        self.check_version()
        ensure_frida_server_running()

        # Frida nomme un appareil adb par son serial : on vise le meme que
        # adb, et non le premier venu, sans quoi deux instances MEmu ouvertes
        # separeraient l'attache et les taps.
        device = frida.get_device(active_serial(), timeout=5)
        self.session = self._attach_to(device)

        self.script = self.session.create_script(charger_agent(build_agent_source(), self.table))
        self.script.on("message", self._on_message)
        self.script.load()

        missing = self.script.exports_sync.symbols()["missing"]
        if missing:
            # `missing` melange deux pannes : un symbole absent, et un offset
            # qui resout mais ne pointe pas sur ce qu'il devrait. Les appeler
            # toutes "symboles non resolus" induirait en erreur.
            raise SessionError(
                "the agent refuses to start. Missing symbols or invalid "
                "offsets:\n  - " + "\n  - ".join(missing)
            )

        self._start_heartbeat()

    def attacher_avec_reessais(
        self,
        essais: int = 15,
        delai: float = 1.0,
        dormir=time.sleep,
    ) -> None:
        """Attache en reessayant, apres un relancement du jeu.

        Le processus renait avant que libthieves.so soit chargee : l'agent
        refuse alors de demarrer en nommant les symboles absents, ce qui est
        le bon comportement mais pas le bon moment. On detache entre deux
        essais, sans quoi la session a moitie ouverte fuirait.
        """
        derniere: Exception | None = None
        # Hors de la boucle : un frida discordant ne se repare pas en
        # attendant, inutile de le constater quinze fois.
        self.verifier_frida()
        for _ in range(essais):
            try:
                self.attach()
                return
            except (SessionError, DeviceError, frida.ProcessNotFoundError,
                    frida.TransportError, frida.ServerNotRunningError) as exc:
                derniere = exc
                self.detach()
                dormir(delai)
        raise SessionError(
            f"attach failed after {essais} tries. Last error: "
            f"{derniere}"
        )

    HEARTBEAT_SECONDS = 2.0

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self.HEARTBEAT_SECONDS):
            try:
                self.script.exports_sync.heartbeat()
            except Exception:
                # Session fermee ou jeu disparu : le fil s'arrete de lui-meme.
                return

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="kot-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

    @staticmethod
    def _on_message(message: dict, data: bytes | None) -> None:
        if message["type"] == "error":
            print("[agent] ERROR:", message.get("stack", message))
        else:
            print("[agent]", message.get("payload"))

    @property
    def api(self):
        if self.script is None:
            raise SessionError("session not attached")
        return self.script.exports_sync

    def detach(self) -> None:
        self._heartbeat_stop.set()
        if self.session is not None:
            self.session.detach()
            self.session = None
            self.script = None
