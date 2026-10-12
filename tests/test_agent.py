import pytest

from controller.agent import AGENT_FILES, build_agent_source, AgentError


def test_ordre_des_modules_respecte_les_dependances():
    # symbols doit preceder tous ceux qui l'utilisent, rpc doit etre dernier
    assert AGENT_FILES[0] == "symbols.js"
    assert AGENT_FILES[-1] == "rpc.js"


def test_assemblage_concatene_dans_l_ordre(tmp_path):
    (tmp_path / "symbols.js").write_text("var A = 1;\n", encoding="utf8")
    (tmp_path / "rpc.js").write_text("var B = 2;\n", encoding="utf8")

    source = build_agent_source(tmp_path, files=["symbols.js", "rpc.js"])

    assert source.index("var A = 1;") < source.index("var B = 2;")


def test_assemblage_insere_un_marqueur_de_fichier(tmp_path):
    (tmp_path / "symbols.js").write_text("var A = 1;\n", encoding="utf8")

    source = build_agent_source(tmp_path, files=["symbols.js"])

    assert "symbols.js" in source


def test_fichier_manquant_leve_une_erreur(tmp_path):
    with pytest.raises(AgentError) as excinfo:
        build_agent_source(tmp_path, files=["absent.js"])
    assert "absent.js" in str(excinfo.value)


def test_la_liste_par_defaut_ne_designe_que_des_fichiers_existants():
    from controller.agent import AGENT_DIR

    manquants = [nom for nom in AGENT_FILES if not (AGENT_DIR / nom).is_file()]
    assert manquants == [], f"fichiers declares mais absents : {manquants}"


def test_assemblage_par_defaut_reussit():
    source = build_agent_source()
    assert "KOT.pump" in source


# Tout ce que le controleur appelle sur `session.api`. Les clefs de
# rpc.exports s'ecrivent en camelCase cote JavaScript et s'appellent en
# snake_case cote Python : frida fait la conversion, pas nous. Ce test
# attrape l'oubli au moment du commit, et non en pleine seance sur un
# frida.RPCException.
APPELS_DU_CONTROLEUR = [
    "ping",
    "symbols",
    "probeResolve",
    "probeState",
    "recordStart",
    "recordStop",
    "recordDrain",
    "recordStatus",
    "frame",
    "pause",
    "resume",
    "step",
    "paused",
    "heartbeat",
    "rythme",
    "horloge",
    "cycle",
    "turbo",
]


def test_l_agent_expose_tout_ce_que_le_controleur_appelle():
    from controller.agent import AGENT_DIR

    source = (AGENT_DIR / "rpc.js").read_text(encoding="utf8")
    manquants = [nom for nom in APPELS_DU_CONTROLEUR if f"{nom}:" not in source]

    assert manquants == [], f"exports absents de agent/rpc.js : {manquants}"


def test_la_phase_de_l_horloge_repart_avec_le_run():
    """Indexee sur le compteur global de l'agent, la phase du cycle
    dependrait du nombre d'images ecoulees depuis le chargement du script.
    Elle doit repartir de zero a chaque activation de l'horloge."""
    from controller.agent import AGENT_DIR

    source = (AGENT_DIR / "pump.js").read_text(encoding="utf8")

    assert "cycleIndex" in source
    assert "frame % CYCLE_MS.length" not in source
