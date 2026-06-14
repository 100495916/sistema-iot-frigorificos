import os

from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

# MongoDB
MONGODB_URI: str = os.getenv("MONGODB_URI", "")
DB_NAME: str = os.getenv("DB_NAME", "iot_tfg")

# ThingsBoard
THINGSBOARD_HOST: str = os.getenv("THINGSBOARD_HOST", "localhost")
THINGSBOARD_HTTP_PORT: str = os.getenv("THINGSBOARD_HTTP_PORT", "8080")
TB_USERNAME: str = os.getenv("TB_USERNAME", "tenant@thingsboard.org")
TB_PASSWORD: str = os.getenv("TB_PASSWORD", "tenant")
TB_API_KEY: str | None = os.getenv("TB_API_KEY")
TB_QUERY_LIMIT: int = int(os.getenv("TB_QUERY_LIMIT", "100000"))
TB_SYNC_START_TS: int = int(os.getenv("TB_SYNC_START_TS", "0"))

# API
BACKEND_CORS_ORIGINS: list[str] = os.getenv("BACKEND_CORS_ORIGINS", "*").split(",")
OPENFOODFACTS_USER_AGENT: str = os.getenv("OPENFOODFACTS_USER_AGENT", "TFG-IoT-Frigorifico/1.0")
