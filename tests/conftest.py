# Configuración de entorno compartida por todos los ficheros de test

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "edge"))

os.environ.setdefault("DATA_DIR", str(Path(tempfile.gettempdir()) / "tfg_tests"))
