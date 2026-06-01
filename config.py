import logging
import os
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_DB_PATH = os.path.join(_BASE_DIR, "instance", "tracker.db")

_SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not _SECRET_KEY:
    logging.warning("SECRET_KEY not set — using insecure default. Set SECRET_KEY in .env.")
    _SECRET_KEY = "dev-secret-change-me"


def _build_db_uri() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        # Neon / older Heroku-style URLs use postgres:// — SQLAlchemy needs postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    return f"sqlite:///{_DB_PATH}"


class Config:
    SECRET_KEY = _SECRET_KEY
    SQLALCHEMY_DATABASE_URI = _build_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

    SEARCH_HOUR = int(os.environ.get("SEARCH_HOUR", 7))
