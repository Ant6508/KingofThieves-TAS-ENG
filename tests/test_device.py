import pytest

from controller.device import (
    parse_version_code,
    parse_version_name,
    parse_package_paths,
    DeviceError,
)

# Sortie reelle de : adb shell dumpsys package com.zeptolab.thieves.google
DUMPSYS = """
    legacyNativeLibraryDir=/data/app/com.zeptolab.thieves.google-jqDmngohl1nFE-ZtzvLfOg==/lib
    primaryCpuAbi=x86_64
    versionCode=4755263 minSdk=24 targetSdk=35
    versionName=2.83
    dataDir=/data/user/0/com.zeptolab.thieves.google
    firstInstallTime=2026-07-09 19:37:23
"""

# Sortie reelle de : adb shell pm path com.zeptolab.thieves.google
PM_PATH = """package:/data/app/com.zeptolab.thieves.google-jqDmngohl1nFE-ZtzvLfOg==/base.apk
package:/data/app/com.zeptolab.thieves.google-jqDmngohl1nFE-ZtzvLfOg==/split_config.fr.apk
package:/data/app/com.zeptolab.thieves.google-jqDmngohl1nFE-ZtzvLfOg==/split_config.x86_64.apk
"""


def test_parse_version_code():
    assert parse_version_code(DUMPSYS) == 4755263


def test_parse_version_name():
    assert parse_version_name(DUMPSYS) == "2.83"


def test_parse_version_code_absent_leve_une_erreur():
    with pytest.raises(DeviceError):
        parse_version_code("rien d'utile ici")


def test_parse_version_name_absent_leve_une_erreur():
    with pytest.raises(DeviceError):
        parse_version_name("rien d'utile ici")


def test_parse_package_paths():
    paths = parse_package_paths(PM_PATH)
    assert len(paths) == 3
    assert paths[0].endswith("/base.apk")
    assert any(p.endswith("/split_config.x86_64.apk") for p in paths)


def test_parse_package_paths_paquet_absent():
    assert parse_package_paths("") == []


from controller.device import parse_pid, GameNotRunning

# Sortie reelle de : adb shell pidof com.zeptolab.thieves.google
PIDOF = "4724\n"
PIDOF_MULTIPLE = "4724 4801\n"


def test_parse_pid():
    assert parse_pid(PIDOF) == 4724


def test_parse_pid_retient_le_premier_quand_il_y_en_a_plusieurs():
    assert parse_pid(PIDOF_MULTIPLE) == 4724


def test_parse_pid_sans_pid_leve_une_erreur():
    with pytest.raises(DeviceError):
        parse_pid("\n")


def test_parse_pid_sans_pid_leve_specifiquement_game_not_running():
    # Distinct de DeviceError : _attach_to doit pouvoir dire "le jeu ne
    # tourne pas" seulement quand c'est vrai, pas pour tout echec adb.
    with pytest.raises(GameNotRunning):
        parse_pid("\n")


def test_parse_pid_illisible_leve_une_erreur_pas_un_valueerror():
    with pytest.raises(DeviceError):
        parse_pid("pas-un-nombre\n")


from controller.device import parse_frida_server_running

# Sortie reelle (tronquee) de : adb shell ps -A
PS_A_AVEC_FRIDA = """USER          PID  PPID     VSZ    RSS WCHAN            ADDR S NAME
root            1     0   14056   2100 SyS_epoll_wait      0 S init
root         4821     1   45080   6132 SyS_epoll_wait      0 S frida-server
u0_a123      5210   456  987654  65432 SyS_epoll_wait      0 S com.zeptolab.thieves.google
"""

PS_A_SANS_FRIDA = """USER          PID  PPID     VSZ    RSS WCHAN            ADDR S NAME
root            1     0   14056   2100 SyS_epoll_wait      0 S init
u0_a123      5210   456  987654  65432 SyS_epoll_wait      0 S com.zeptolab.thieves.google
"""


def test_parse_frida_server_running_present():
    assert parse_frida_server_running(PS_A_AVEC_FRIDA) is True


def test_parse_frida_server_running_absent():
    assert parse_frida_server_running(PS_A_SANS_FRIDA) is False


from controller.device import parse_frida_server_present


def test_parse_frida_server_present_quand_le_test_e_reussit():
    assert parse_frida_server_present("present\n") is True


def test_parse_frida_server_present_quand_le_test_e_echoue():
    assert parse_frida_server_present("absent\n") is False


import controller.device as module_device
from controller.device import ensure_frida_server_running


def test_ensure_frida_server_running_ne_fait_rien_si_deja_lance(monkeypatch):
    appels = []
    monkeypatch.setattr(module_device, "frida_server_running",
                        lambda serial=None: True)
    monkeypatch.setattr(module_device, "frida_server_present",
                        lambda serial=None: appels.append("present"))
    monkeypatch.setattr(module_device, "push_frida_server",
                        lambda serial=None: appels.append("push"))
    monkeypatch.setattr(module_device, "start_frida_server",
                        lambda serial=None: appels.append("start"))

    ensure_frida_server_running()

    assert appels == []


def test_ensure_frida_server_running_pousse_le_binaire_absent_puis_le_lance(monkeypatch):
    appels = []
    monkeypatch.setattr(module_device, "frida_server_running",
                        lambda serial=None: False)
    monkeypatch.setattr(module_device, "frida_server_present",
                        lambda serial=None: False)
    monkeypatch.setattr(module_device, "push_frida_server",
                        lambda serial=None: appels.append("push"))
    monkeypatch.setattr(module_device, "start_frida_server",
                        lambda serial=None: appels.append("start"))

    ensure_frida_server_running()

    assert appels == ["push", "start"]


def test_ensure_frida_server_running_ne_pousse_pas_si_deja_present(monkeypatch):
    appels = []
    monkeypatch.setattr(module_device, "frida_server_running",
                        lambda serial=None: False)
    monkeypatch.setattr(module_device, "frida_server_present",
                        lambda serial=None: True)
    monkeypatch.setattr(module_device, "push_frida_server",
                        lambda serial=None: appels.append("push"))
    monkeypatch.setattr(module_device, "start_frida_server",
                        lambda serial=None: appels.append("start"))

    ensure_frida_server_running()

    assert appels == ["start"]


from controller.device import parse_adb_devices, pick_serial

# Sortie reelle de : adb devices, avec seule l'instance MEmu_1 (kot2) ouverte
ADB_DEVICES_KOT2 = """List of devices attached
127.0.0.1:21513\tdevice

"""

ADB_DEVICES_DEUX_INSTANCES = """List of devices attached
127.0.0.1:21503\tdevice
127.0.0.1:21513\tdevice

"""

ADB_DEVICES_PAS_PRETS = """List of devices attached
127.0.0.1:21503\toffline
127.0.0.1:21513\tunauthorized

"""


def test_parse_adb_devices_rend_le_serial_de_l_instance_ouverte():
    assert parse_adb_devices(ADB_DEVICES_KOT2) == ["127.0.0.1:21513"]


def test_parse_adb_devices_rend_toutes_les_instances_ouvertes():
    assert parse_adb_devices(ADB_DEVICES_DEUX_INSTANCES) == [
        "127.0.0.1:21503", "127.0.0.1:21513",
    ]


def test_parse_adb_devices_ignore_les_appareils_pas_prets():
    assert parse_adb_devices(ADB_DEVICES_PAS_PRETS) == []


def test_pick_serial_prend_le_seul_appareil():
    assert pick_serial(["127.0.0.1:21513"]) == "127.0.0.1:21513"


def test_pick_serial_sans_appareil_dit_de_lancer_memu():
    with pytest.raises(DeviceError) as excinfo:
        pick_serial([])
    assert "MEmu" in str(excinfo.value)


def test_pick_serial_refuse_de_deviner_entre_plusieurs_appareils():
    with pytest.raises(DeviceError) as excinfo:
        pick_serial(["127.0.0.1:21503", "127.0.0.1:21513"])
    message = str(excinfo.value)
    assert "127.0.0.1:21503" in message
    assert "127.0.0.1:21513" in message
    assert "KOT_SERIAL" in message


from controller.device import active_serial


def test_active_serial_prefere_kot_serial_sans_interroger_adb(monkeypatch):
    monkeypatch.setattr(module_device, "_active_serial", None)
    monkeypatch.setenv("KOT_SERIAL", "127.0.0.1:21503")

    def interdit():
        raise AssertionError("adb devices ne doit pas etre appele")

    monkeypatch.setattr(module_device, "connected_serials", interdit)

    assert active_serial() == "127.0.0.1:21503"


def test_active_serial_prend_le_seul_appareil_connecte(monkeypatch):
    monkeypatch.setattr(module_device, "_active_serial", None)
    monkeypatch.delenv("KOT_SERIAL", raising=False)
    monkeypatch.setattr(module_device, "connected_serials",
                        lambda: ["127.0.0.1:21513"])

    assert active_serial() == "127.0.0.1:21513"


def test_active_serial_n_interroge_adb_qu_une_fois(monkeypatch):
    """Chaque tap passe par run_adb : un adb devices par appel doublerait
    le cout d'un tap, qui fixe la cadence de l'autoclic."""
    monkeypatch.setattr(module_device, "_active_serial", None)
    monkeypatch.delenv("KOT_SERIAL", raising=False)
    appels = []

    def connectes():
        appels.append("devices")
        return ["127.0.0.1:21513"]

    monkeypatch.setattr(module_device, "connected_serials", connectes)

    active_serial()
    active_serial()

    assert appels == ["devices"]


def test_active_serial_ne_retient_pas_un_echec(monkeypatch):
    """MEmu lance apres l'atelier : l'essai suivant doit trouver l'appareil."""
    monkeypatch.setattr(module_device, "_active_serial", None)
    monkeypatch.delenv("KOT_SERIAL", raising=False)
    reponses = [[], ["127.0.0.1:21513"]]
    monkeypatch.setattr(module_device, "connected_serials",
                        lambda: reponses.pop(0))

    with pytest.raises(DeviceError):
        active_serial()
    assert active_serial() == "127.0.0.1:21513"


def test_run_adb_sans_serial_vise_l_appareil_actif(monkeypatch):
    monkeypatch.setattr(module_device, "active_serial",
                        lambda: "127.0.0.1:21513")
    commandes = []

    class Rendu:
        returncode = 0
        stdout = "4724\n"
        stderr = ""

    def faux_run(commande, **kwargs):
        commandes.append(commande)
        return Rendu()

    monkeypatch.setattr(module_device.subprocess, "run", faux_run)

    module_device.run_adb("shell", "pidof", "x")

    assert commandes[0][1:3] == ["-s", "127.0.0.1:21513"]


from controller.device import FRIDA_SERVER_VERSION, message_frida_discordant


def test_message_frida_discordant_rien_quand_les_versions_concordent():
    assert message_frida_discordant(FRIDA_SERVER_VERSION) is None


def test_message_frida_discordant_donne_la_commande_de_reparation():
    """Vecu : un `uv run` avait monte frida en 17.19 contre un serveur 17.18,
    et l'attache echouait sur une erreur de protocole qui ne disait pas que
    la cause etait une version."""
    message = message_frida_discordant("17.19.0")

    assert "17.19.0" in message
    assert f'pip install "frida=={FRIDA_SERVER_VERSION}"' in message


import os
import sys

from controller.device import CHEMIN_ADB_PAR_DEFAUT, dossier_memu, resoudre_adb

MEMU = r"D:\Program Files\Microvirt"
ADB_MEMU = os.path.join(MEMU, "MEmu", "adb.exe")
ADB_SDK = os.path.join(r"C:\sdk", "platform-tools", "adb.exe")
ADB_PATH = r"C:\ailleurs\adb.exe"


def _resoudre(environ=None, which=None, memu=None, existants=()):
    """resoudre_adb sans toucher au systeme : rien n'existe sauf `existants`."""
    return resoudre_adb(
        environ={} if environ is None else environ,
        which=which or (lambda nom: None),
        memu=memu or (lambda: None),
        isfile=lambda chemin: chemin in existants,
    )


def test_resoudre_adb_prefere_le_sdk():
    assert _resoudre(environ={"ANDROID_SDK_ROOT": r"C:\sdk"},
                     which=lambda nom: ADB_PATH,
                     memu=lambda: MEMU,
                     existants={ADB_SDK, ADB_MEMU}) == ADB_SDK


def test_resoudre_adb_prend_le_path_sans_sdk():
    assert _resoudre(which=lambda nom: ADB_PATH,
                     memu=lambda: MEMU,
                     existants={ADB_MEMU}) == ADB_PATH


def test_resoudre_adb_trouve_l_adb_de_memu_par_le_registre():
    """Le cas d'un nouvel utilisateur : ni SDK Android ni adb dans le PATH,
    seulement MEmu, qui fournit son propre adb.exe."""
    assert _resoudre(memu=lambda: MEMU, existants={ADB_MEMU}) == ADB_MEMU


def test_resoudre_adb_ignore_un_dossier_memu_sans_adb():
    assert _resoudre(memu=lambda: MEMU) == CHEMIN_ADB_PAR_DEFAUT


def test_resoudre_adb_sans_rien_rend_le_chemin_par_defaut():
    assert _resoudre() == CHEMIN_ADB_PAR_DEFAUT


class _FausseCle:
    def __init__(self, valeurs):
        self.valeurs = valeurs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FauxWinreg:
    """Imite le module winreg : `cles` associe (racine, chemin) a ses valeurs."""

    HKEY_LOCAL_MACHINE = "HKLM"

    def __init__(self, cles):
        self.cles = cles

    def OpenKey(self, racine, chemin):
        if (racine, chemin) not in self.cles:
            raise FileNotFoundError(chemin)
        return _FausseCle(self.cles[(racine, chemin)])

    @staticmethod
    def QueryValueEx(cle, nom):
        if nom not in cle.valeurs:
            raise FileNotFoundError(nom)
        return cle.valeurs[nom], 1


def test_dossier_memu_lit_install_location(monkeypatch):
    faux = FauxWinreg({("HKLM", module_device.CLE_MEMU): {"InstallLocation": MEMU}})
    monkeypatch.setitem(sys.modules, "winreg", faux)

    assert dossier_memu() == MEMU


def test_dossier_memu_sans_cle_rend_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", FauxWinreg({}))

    assert dossier_memu() is None


def test_dossier_memu_valeur_vide_rend_none(monkeypatch):
    faux = FauxWinreg({("HKLM", module_device.CLE_MEMU): {"InstallLocation": ""}})
    monkeypatch.setitem(sys.modules, "winreg", faux)

    assert dossier_memu() is None


def test_dossier_memu_sans_winreg_rend_none(monkeypatch):
    # Un module a None dans sys.modules fait echouer son import.
    monkeypatch.setitem(sys.modules, "winreg", None)

    assert dossier_memu() is None


def _adb_introuvable(commande, **kwargs):
    raise FileNotFoundError(2, "Le fichier specifie est introuvable")


def test_run_adb_introuvable_leve_un_device_error_lisible(monkeypatch):
    """Sans adb, subprocess levait un WinError 2 qui ne nommait pas adb."""
    monkeypatch.setattr(module_device.subprocess, "run", _adb_introuvable)

    with pytest.raises(DeviceError) as excinfo:
        module_device.run_adb("shell", "pidof", "x", serial="127.0.0.1:21503")

    assert "adb not found" in str(excinfo.value)
    assert "MEmu" in str(excinfo.value)


def test_connected_serials_adb_introuvable_leve_un_device_error_lisible(monkeypatch):
    monkeypatch.setattr(module_device.subprocess, "run", _adb_introuvable)

    with pytest.raises(DeviceError) as excinfo:
        module_device.connected_serials()

    assert "adb not found" in str(excinfo.value)


import lzma
import urllib.error

from controller.device import FRIDA_SERVER_URL, obtenir_frida_server_local


def test_obtenir_frida_server_local_ne_telecharge_pas_une_copie_presente(tmp_path):
    chemin = tmp_path / "frida-server" / "fs"
    chemin.parent.mkdir()
    chemin.write_bytes(b"DEJA LA")

    def interdit(url):
        raise AssertionError("pas de telechargement attendu")

    assert obtenir_frida_server_local(str(chemin), telecharger=interdit) == str(chemin)
    assert chemin.read_bytes() == b"DEJA LA"


def test_obtenir_frida_server_local_telecharge_et_decompresse(tmp_path):
    chemin = tmp_path / "frida-server" / "fs"
    urls = []

    def telecharger(url):
        urls.append(url)
        return lzma.compress(b"BINAIRE")

    assert obtenir_frida_server_local(str(chemin), telecharger=telecharger) == str(chemin)
    assert chemin.read_bytes() == b"BINAIRE"
    assert urls == [FRIDA_SERVER_URL]
    assert not (tmp_path / "frida-server" / "fs.part").exists()


def test_obtenir_frida_server_local_sans_reseau_donne_l_url(tmp_path):
    chemin = tmp_path / "frida-server" / "fs"

    def hors_ligne(url):
        raise urllib.error.URLError("pas de reseau")

    with pytest.raises(DeviceError) as excinfo:
        obtenir_frida_server_local(str(chemin), telecharger=hors_ligne)

    assert FRIDA_SERVER_URL in str(excinfo.value)
    assert str(chemin) in str(excinfo.value)
    assert not chemin.exists()


def test_obtenir_frida_server_local_archive_corrompue(tmp_path):
    chemin = tmp_path / "frida-server" / "fs"

    with pytest.raises(DeviceError):
        obtenir_frida_server_local(str(chemin), telecharger=lambda url: b"pas du xz")

    assert not chemin.exists()


def test_push_frida_server_pousse_la_copie_locale_obtenue(monkeypatch):
    monkeypatch.setattr(module_device, "obtenir_frida_server_local",
                        lambda: r"C:\copie\fs")
    commandes = []
    monkeypatch.setattr(module_device, "run_adb",
                        lambda *args, serial=None: commandes.append(args))

    module_device.push_frida_server(serial="127.0.0.1:21503")

    assert commandes == [
        ("push", r"C:\copie\fs", "/data/local/tmp/frida-server"),
        ("shell", "chmod 755 /data/local/tmp/frida-server"),
    ]
