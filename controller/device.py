"""Lecture de l'etat de l'appareil via adb.

Les fonctions d'analyse sont pures : elles prennent une chaine et rendent une
valeur. Le lancement effectif d'adb est isole dans `run_adb`, pour que
l'analyse reste testable sans appareil.
"""

from __future__ import annotations

import lzma
import os
import re
import shutil
import subprocess
import urllib.request

CHEMIN_ADB_PAR_DEFAUT = r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe"

# L'installeur de MEmu inscrit ici son dossier (valeur InstallLocation, par
# exemple D:\Program Files\Microvirt) ; adb.exe est dans le sous-dossier MEmu.
CLE_MEMU = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\MEmu"


def dossier_memu() -> str | None:
    """Le dossier d'installation de MEmu lu dans le registre, ou None.

    winreg est importe ici et non en tete : il n'existe que sous Windows, et
    son absence veut seulement dire qu'il n'y a pas de MEmu a trouver.
    """
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLE_MEMU) as cle:
            valeur, _ = winreg.QueryValueEx(cle, "InstallLocation")
    except OSError:
        return None
    return valeur or None


def resoudre_adb(environ=None, which=shutil.which, memu=dossier_memu,
                 isfile=os.path.isfile) -> str:
    """Trouve adb.exe : SDK Android, PATH, adb fourni par MEmu, puis repli.

    Le chemin en dur ne vaut que pour l'installation d'origine ; sur une
    autre machine (SDK ailleurs, ou seul platform-tools installe sans
    Android Studio), `adb devices` levait un FileNotFoundError peu
    explicite (WinError 2) au lieu de dire que l'adb attendu est absent.

    L'adb de MEmu passe apres le PATH : un adb que l'utilisateur a choisi
    d'y mettre l'emporte. C'est souvent le seul adb d'un nouvel utilisateur.
    Les sources sont injectables pour que les tests ne touchent pas au
    systeme.
    """
    environ = os.environ if environ is None else environ
    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        racine = environ.get(variable)
        if racine:
            candidat = os.path.join(racine, "platform-tools", "adb.exe")
            if isfile(candidat):
                return candidat
    depuis_le_path = which("adb")
    if depuis_le_path:
        return depuis_le_path
    dossier = memu()
    if dossier:
        candidat = os.path.join(dossier, "MEmu", "adb.exe")
        if isfile(candidat):
            return candidat
    return CHEMIN_ADB_PAR_DEFAUT


ADB = resoudre_adb()
PACKAGE = "com.zeptolab.thieves.google"

# Chaque instance MEmu a son port adb : MEmu 127.0.0.1:21503, MEmu_1 (kot2)
# 127.0.0.1:21513, puis +10 par instance. KOT_SERIAL force le choix quand
# plusieurs instances sont ouvertes ; sinon on prend la seule connectee.
VARIABLE_SERIAL = "KOT_SERIAL"


class DeviceError(Exception):
    """Une information attendue est absente de la sortie adb."""


class GameNotRunning(DeviceError):
    """`pidof` n'a rendu aucun pid : le jeu ne tourne pas.

    Distinct des autres DeviceError (adb hors ligne, non autorise, serveur
    adb mort...), qui ne veulent pas dire la meme chose et ne doivent pas
    etre rapportes comme si le jeu etait arrete.
    """


def parse_version_code(dumpsys_output: str) -> int:
    match = re.search(r"\bversionCode=(\d+)", dumpsys_output)
    if match is None:
        raise DeviceError("versionCode missing from dumpsys output")
    return int(match.group(1))


def parse_version_name(dumpsys_output: str) -> str:
    match = re.search(r"\bversionName=(\S+)", dumpsys_output)
    if match is None:
        raise DeviceError("versionName missing from dumpsys output")
    return match.group(1)


def parse_package_paths(pm_path_output: str) -> list[str]:
    return [
        line[len("package:") :].strip()
        for line in pm_path_output.splitlines()
        if line.startswith("package:")
    ]


def parse_pid(pidof_output: str) -> int:
    """Rend le premier pid de la sortie de `pidof`.

    ART tronque le nom du processus a 15 caracteres, donc l'attache Frida par
    nom echoue alors que le jeu tourne. Le pid est le seul identifiant fiable.
    """
    champs = pidof_output.split()
    if not champs:
        raise GameNotRunning("no pid: the game isn't running")
    try:
        return int(champs[0])
    except ValueError as exc:
        raise DeviceError(
            f"unreadable pid in pidof output: {champs[0]!r}"
        ) from exc


def parse_adb_devices(devices_output: str) -> list[str]:
    """Rend les serials prets de la sortie de `adb devices`.

    Un appareil `offline` ou `unauthorized` est ecarte : adb -s echouerait
    dessus de toute facon.
    """
    serials = []
    for ligne in devices_output.splitlines()[1:]:
        champs = ligne.split()
        if len(champs) >= 2 and champs[1] == "device":
            serials.append(champs[0])
    return serials


def pick_serial(serials: list[str]) -> str:
    """Rend le seul appareil connecte. Ne devine pas entre plusieurs."""
    if not serials:
        raise DeviceError("no adb device connected: launch MEmu.")
    if len(serials) > 1:
        raise DeviceError(
            f"several adb devices connected ({', '.join(serials)}). "
            f"Pick one with the {VARIABLE_SERIAL} variable, for example "
            f'$env:{VARIABLE_SERIAL}="{serials[0]}"'
        )
    return serials[0]


def _lancer_adb(commande: list[str]) -> subprocess.CompletedProcess:
    """Lance adb. Un adb introuvable devient un DeviceError qui le nomme."""
    try:
        return subprocess.run(commande, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise DeviceError(
            f"adb not found ({commande[0]}). Install MEmu, or add adb's "
            "folder to the PATH."
        ) from exc


def connected_serials() -> list[str]:
    result = _lancer_adb([ADB, "devices"])
    if result.returncode != 0:
        raise DeviceError(f"adb devices failed: {result.stderr.strip()}")
    return parse_adb_devices(result.stdout)


_active_serial: str | None = None


def active_serial() -> str:
    """L'appareil vise par adb et Frida, resolu une fois par processus.

    Une fois seulement : chaque tap passe par run_adb, et un `adb devices`
    de plus a chaque appel doublerait son cout. Un echec n'est pas retenu,
    pour qu'un MEmu lance apres coup soit trouve a l'essai suivant.
    """
    global _active_serial
    if _active_serial is None:
        _active_serial = (os.environ.get(VARIABLE_SERIAL)
                          or pick_serial(connected_serials()))
    return _active_serial


def run_adb(*args: str, serial: str | None = None) -> str:
    """Lance adb et rend sa sortie standard. Leve DeviceError si adb echoue."""
    result = _lancer_adb([ADB, "-s", serial or active_serial(), *args])
    if result.returncode != 0:
        raise DeviceError(f"adb {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def installed_version(package: str = PACKAGE, serial: str | None = None) -> tuple[str, int]:
    """Rend (versionName, versionCode) du paquet installe."""
    output = run_adb("shell", "dumpsys", "package", package, serial=serial)
    return parse_version_name(output), parse_version_code(output)


def game_pid(package: str = PACKAGE, serial: str | None = None) -> int:
    return parse_pid(run_adb("shell", "pidof", package, serial=serial))


def parse_frida_server_running(ps_output: str) -> bool:
    """Vrai si `ps -A` montre un processus frida-server en cours."""
    return any("frida-server" in ligne for ligne in ps_output.splitlines())


FRIDA_SERVER_VERSION = "17.18.0"
FRIDA_SERVER_REMOTE_PATH = "/data/local/tmp/frida-server"
_RACINE_DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRIDA_SERVER_LOCAL_PATH = os.path.join(
    _RACINE_DEPOT, "frida-server",
    f"frida-server-{FRIDA_SERVER_VERSION}-android-x86_64",
)


def message_frida_discordant(installee: str) -> str | None:
    """Le message d'erreur si le frida installe n'est pas celui du serveur.

    Les deux doivent etre strictement identiques ; sinon l'attache echoue sur
    une erreur de protocole peu explicite. Rend None quand ils concordent.
    """
    if installee == FRIDA_SERVER_VERSION:
        return None
    return (
        f"frida {installee} is installed, but the tool expects "
        f"{FRIDA_SERVER_VERSION} (the version of the frida-server pushed to "
        f"the device). Fix it with:\n"
        f"  .venv\\Scripts\\python.exe -m pip install "
        f'"frida=={FRIDA_SERVER_VERSION}"'
    )


# L'archive officielle de la release Frida. La copie decompressee pese
# 116 Mo, au-dela de la limite de GitHub : elle n'est pas dans le depot.
FRIDA_SERVER_URL = (
    "https://github.com/frida/frida/releases/download/"
    f"{FRIDA_SERVER_VERSION}/frida-server-{FRIDA_SERVER_VERSION}-android-x86_64.xz"
)


def telecharger_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as reponse:
        return reponse.read()


def obtenir_frida_server_local(chemin: str = FRIDA_SERVER_LOCAL_PATH,
                               telecharger=telecharger_url) -> str:
    """Rend le chemin de la copie locale de frida-server, telechargee au besoin.

    L'ecriture passe par un fichier .part renomme a la fin : une copie a
    moitie ecrite (coupure reseau, fenetre fermee) n'est jamais prise pour
    la bonne au lancement suivant.
    """
    if os.path.isfile(chemin):
        return chemin
    print(f"frida-server missing: downloading version "
          f"{FRIDA_SERVER_VERSION} (34 MB)...", flush=True)
    try:
        binaire = lzma.decompress(telecharger(FRIDA_SERVER_URL))
    except (OSError, lzma.LZMAError) as exc:
        raise DeviceError(
            f"frida-server {FRIDA_SERVER_VERSION} missing and could not be "
            f"downloaded ({exc}).\n"
            f"Download it by hand: {FRIDA_SERVER_URL}\n"
            f"Unpack it (7-Zip) and put it at: {chemin}"
        ) from exc
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    partiel = chemin + ".part"
    with open(partiel, "wb") as fichier:
        fichier.write(binaire)
    os.replace(partiel, chemin)
    return chemin


def frida_server_running(serial: str | None = None) -> bool:
    return parse_frida_server_running(run_adb("shell", "ps -A", serial=serial))


def parse_frida_server_present(sortie: str) -> bool:
    """Vrai si `test -e ... && echo present || echo absent` a trouve le fichier."""
    return sortie.strip() == "present"


def frida_server_present(serial: str | None = None) -> bool:
    """Vrai si le binaire est deja pousse sur l'appareil.

    `test -e ... && echo present || echo absent` plutot qu'un exit code :
    une absence est un etat normal a detecter, pas un echec adb (meme
    logique que GameNotRunning face a DeviceError pour pidof).
    """
    sortie = run_adb(
        "shell",
        f"test -e {FRIDA_SERVER_REMOTE_PATH} && echo present || echo absent",
        serial=serial,
    )
    return parse_frida_server_present(sortie)


def push_frida_server(local_path: str | None = None,
                      serial: str | None = None) -> None:
    """Pousse la copie locale sur l'appareil et la rend executable.

    La copie locale est telechargee d'abord si elle manque.
    """
    if local_path is None:
        local_path = obtenir_frida_server_local()
    run_adb("push", local_path, FRIDA_SERVER_REMOTE_PATH, serial=serial)
    run_adb("shell", f"chmod 755 {FRIDA_SERVER_REMOTE_PATH}", serial=serial)


def start_frida_server(serial: str | None = None) -> None:
    """Lance frida-server en tache de fond sur l'appareil.

    Forme qui rend la main (scripts/setup_frida.md) : sans nohup et la
    redirection des flux, adb shell resterait bloque sur la session ouverte
    par le serveur detache.
    """
    run_adb(
        "shell",
        f"nohup {FRIDA_SERVER_REMOTE_PATH} -D </dev/null >/dev/null 2>&1 &",
        serial=serial,
    )


def ensure_frida_server_running(serial: str | None = None) -> None:
    """Lance frida-server s'il ne tourne pas deja.

    Le pousse d'abord depuis la copie locale (telechargee au besoin) s'il est
    absent de l'appareil (image MEmu neuve ou restauree sans lui) : le cas
    normal, un simple redemarrage de MEmu, garde le fichier et ne tue que le
    processus.
    """
    if frida_server_running(serial=serial):
        return
    if not frida_server_present(serial=serial):
        push_frida_server(serial=serial)
    start_frida_server(serial=serial)
