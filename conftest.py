"""Mette la radice del progetto sul path, cosi' `import rules` / `import ingest`
funziona lanciando `pytest` dalla cartella del progetto."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
