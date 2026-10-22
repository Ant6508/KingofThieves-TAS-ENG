"""Controleur du TAS. Le noyau commun (`kotnoyau`) vient du venv (depot prive), ou de la copie
de `_noyau/` a la racine du depot publie (scripts/publier.py)."""
import sys
from pathlib import Path

try:
    import kotnoyau  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_noyau"))
