"""Assemblage des fichiers JavaScript de l'agent en un script unique.

Frida charge un seul script. Plutot que d'imposer une chaine de build Node,
chaque fichier declare son module sur l'espace de noms global `KOT` et ils sont
concatenes dans un ordre de dependance fixe.
"""

from __future__ import annotations

from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"

# L'ordre est un ordre de dependance, pas un ordre alphabetique.
# input.js apparaitra ici a la tache 10, quand il existera.
AGENT_FILES = [
    "symbols.js",
    "probe.js",
    "pump.js",
    "record.js",
    "rpc.js",
]


class AgentError(Exception):
    """Un fichier de l'agent est introuvable ou illisible."""


def build_agent_source(
    directory: Path | None = None,
    files: list[str] | None = None,
) -> str:
    directory = AGENT_DIR if directory is None else Path(directory)
    files = AGENT_FILES if files is None else files

    parts: list[str] = []
    for name in files:
        path = directory / name
        if not path.is_file():
            raise AgentError(f"agent file not found: {path}")
        parts.append(f"// ===== {name} =====")
        parts.append(path.read_text(encoding="utf8"))

    return "\n".join(parts)
