import os
import sys

BASE_DIR = os.path.dirname(__file__)
VENV_PY = os.path.join(BASE_DIR, ".venv", "bin", "python")

if os.path.exists(VENV_PY) and sys.executable != VENV_PY:
    os.execl(VENV_PY, VENV_PY, *sys.argv)

sys.path.insert(0, BASE_DIR)

from app import app as application # noqa
