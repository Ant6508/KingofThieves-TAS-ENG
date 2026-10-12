import frida
import pytest

from controller import session as module_session
from controller.device import DeviceError, GameNotRunning
from controller.session import Session, SessionError


class FauxDevice:
    """Imite un appareil ou l'attache par nom echoue, comme sous ART.

    `echoue_aussi_par_pid` imite en plus la course ou le jeu meurt entre
    l'appel a `pidof` et l'attache Frida : l'attache par pid echoue aussi.
    """

    def __init__(self, echoue_aussi_par_pid: bool = False):
        self.essais = []
        self.echoue_aussi_par_pid = echoue_aussi_par_pid

    def attach(self, cible):
        self.essais.append(cible)
        if isinstance(cible, str) or self.echoue_aussi_par_pid:
            raise frida.ProcessNotFoundError("unable to find process")
        return f"session-{cible}"


def test_attache_par_nom_puis_retombe_sur_le_pid(monkeypatch):
    monkeypatch.setattr(module_session, "game_pid", lambda package: 4724)
    appareil = FauxDevice()

    assert Session()._attach_to(appareil) == "session-4724"
    assert appareil.essais == ["com.zeptolab.thieves.google", 4724]


def test_jeu_absent_donne_un_message_exploitable(monkeypatch):
    def pas_de_pid(package):
        raise GameNotRunning("aucun pid : le jeu ne tourne pas")

    monkeypatch.setattr(module_session, "game_pid", pas_de_pid)

    with pytest.raises(SessionError) as excinfo:
        Session()._attach_to(FauxDevice())
    assert "MEmu" in str(excinfo.value)


def test_echec_adb_ne_pretend_pas_que_le_jeu_est_arrete(monkeypatch):
    """Un DeviceError qui n'est pas GameNotRunning vient d'un echec adb (hors
    ligne, non autorise, serveur adb mort...) : il ne doit pas se travestir
    en "le jeu ne tourne pas", ce serait faux et ca enverrait l'operateur
    verifier MEmu au lieu d'adb.
    """

    def echec_adb(package):
        raise DeviceError("adb shell pidof a echoue : device offline")

    monkeypatch.setattr(module_session, "game_pid", echec_adb)

    with pytest.raises(DeviceError) as excinfo:
        Session()._attach_to(FauxDevice())
    assert "MEmu" not in str(excinfo.value)


def test_processus_disparu_entre_pidof_et_attache_donne_un_message_exploitable(
    monkeypatch,
):
    """Course reelle : deux allers-retours adb separent `pidof` de l'attache.
    Si le jeu meurt entre les deux, l'attache par pid echoue aussi et
    l'exception frida brute ne doit pas s'echapper telle quelle.
    """
    monkeypatch.setattr(module_session, "game_pid", lambda package: 4724)

    with pytest.raises(SessionError) as excinfo:
        Session()._attach_to(FauxDevice(echoue_aussi_par_pid=True))
    assert "4724" in str(excinfo.value)


def test_le_rattachement_reessaie_tant_que_l_agent_refuse(monkeypatch):
    """Apres un relancement, le processus existe avant que libthieves.so soit
    chargee : l'agent refuse alors de demarrer, et c'est le bon comportement.
    Le rattachement doit donc reessayer au lieu d'abandonner."""
    essais = []

    def attache():
        essais.append(len(essais))
        if len(essais) < 3:
            raise SessionError("symboles absents ou offsets invalides")

    session = Session()
    monkeypatch.setattr(session, "attach", attache)
    monkeypatch.setattr(session, "detach", lambda: None)

    session.attacher_avec_reessais(essais=5, delai=0.0, dormir=lambda s: None)

    assert len(essais) == 3


def test_le_rattachement_reessaie_si_le_serveur_frida_est_indisponible(monkeypatch):
    """frida-server peut etre injoignable un instant apres un relancement
    (connexion adb qui se retablit, appareil qui redemarre) : c'est le meme
    genre de panne transitoire que TransportError, et le rattachement doit
    reessayer au lieu de laisser l'exception frida brute remonter."""
    essais = []

    def attache():
        essais.append(len(essais))
        if len(essais) < 3:
            raise frida.ServerNotRunningError(
                "unable to connect to remote frida-server: closed"
            )

    session = Session()
    monkeypatch.setattr(session, "attach", attache)
    monkeypatch.setattr(session, "detach", lambda: None)

    session.attacher_avec_reessais(essais=5, delai=0.0, dormir=lambda s: None)

    assert len(essais) == 3


def test_le_rattachement_abandonne_en_nommant_la_derniere_erreur(monkeypatch):
    def attache():
        raise SessionError("libthieves.so introuvable")

    session = Session()
    monkeypatch.setattr(session, "attach", attache)
    monkeypatch.setattr(session, "detach", lambda: None)

    with pytest.raises(SessionError) as excinfo:
        session.attacher_avec_reessais(essais=2, delai=0.0,
                                       dormir=lambda s: None)

    assert "libthieves.so introuvable" in str(excinfo.value)
    assert "2 tries" in str(excinfo.value)


def test_attach_appelle_ensure_frida_server_running_avant_de_se_connecter(
    monkeypatch,
):
    """ensure_frida_server_running doit tourner avant tout appel a
    l'appareil Frida : sinon un frida-server absent redonnerait la meme
    ServerNotRunningError qu'avant ce changement."""
    ordre = []
    monkeypatch.setattr(Session, "check_version", lambda self: None)
    monkeypatch.setattr(module_session, "ensure_frida_server_running",
                        lambda: ordre.append("ensure"))
    monkeypatch.setattr(module_session, "active_serial",
                        lambda: "127.0.0.1:21513")

    class Stop(Exception):
        pass

    def get_device(id, timeout=0):
        ordre.append("get_device")
        raise Stop()

    monkeypatch.setattr(frida, "get_device", get_device)

    with pytest.raises(Stop):
        Session().attach()

    assert ordre == ["ensure", "get_device"]


def test_attach_vise_dans_frida_l_appareil_vise_par_adb(monkeypatch):
    """Avec deux instances MEmu ouvertes, get_usb_device prendrait la
    premiere venue : Frida pourrait s'attacher a un autre jeu que celui dont
    adb vient de lire la version et vers lequel partent les taps."""
    monkeypatch.setattr(Session, "check_version", lambda self: None)
    monkeypatch.setattr(module_session, "ensure_frida_server_running",
                        lambda: None)
    monkeypatch.setattr(module_session, "active_serial",
                        lambda: "127.0.0.1:21513")
    vises = []

    class Stop(Exception):
        pass

    def get_device(id, timeout=0):
        vises.append(id)
        raise Stop()

    monkeypatch.setattr(frida, "get_device", get_device)

    with pytest.raises(Stop):
        Session().attach()

    assert vises == ["127.0.0.1:21513"]


def test_attach_refuse_un_frida_discordant_avant_tout_appel_adb(monkeypatch):
    """La version de frida se lit sans appareil : la verifier en premier
    evite d'envoyer l'operateur verifier MEmu pour une panne de pip."""
    monkeypatch.setattr(frida, "__version__", "17.19.0")

    def interdit(*args, **kwargs):
        raise AssertionError("aucun appel adb attendu")

    monkeypatch.setattr(Session, "check_version", interdit)
    monkeypatch.setattr(module_session, "ensure_frida_server_running", interdit)

    with pytest.raises(SessionError) as excinfo:
        Session().attach()

    assert "17.19.0" in str(excinfo.value)
    assert 'pip install "frida==17.18.0"' in str(excinfo.value)


def test_le_rattachement_ne_reessaie_pas_un_frida_discordant(monkeypatch):
    """Un frida discordant ne se repare pas en attendant : quinze essais
    d'une seconde ne feraient que retarder le message."""
    monkeypatch.setattr(frida, "__version__", "17.19.0")
    essais = []
    session = Session()
    monkeypatch.setattr(session, "attach", lambda: essais.append(1))
    monkeypatch.setattr(session, "detach", lambda: None)

    with pytest.raises(SessionError) as excinfo:
        session.attacher_avec_reessais(essais=5, delai=0.0,
                                       dormir=lambda s: None)

    assert essais == []
    assert "17.19.0" in str(excinfo.value)
