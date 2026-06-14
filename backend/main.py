import os
import sys

import uvicorn

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Crea la aplicacion FastAPI
from backend.app import create_app

if __name__ == "__main__":
    app = create_app()
    print("Arrancando el servidor web en http://127.0.0.1:8000")

    # Arranca Uvicorn escuchando todas las interfaces
    uvicorn.run(app, host="0.0.0.0", port=8000)
