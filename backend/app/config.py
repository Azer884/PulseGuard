import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BACKEND_DIR / ".env")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_API_BASE_URL = os.getenv("NVIDIA_API_BASE_URL", "")
CORS_ALLOW_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
TEAM_DATA_FILE = Path(os.getenv("TEAM_DATA_FILE") or BACKEND_DIR / "data" / "team.json")
PROJECTS_DATA_FILE = Path(os.getenv("PROJECTS_DATA_FILE") or BACKEND_DIR / "data" / "projects.json")
PLANE_STATE_FILE = Path(os.getenv("PLANE_STATE_FILE") or BACKEND_DIR / "data" / "plane.json")
PLANE_BASE_URL = os.getenv("PLANE_BASE_URL", "")
PLANE_API_KEY = os.getenv("PLANE_API_KEY", "")
PLANE_WORKSPACE_SLUG = os.getenv("PLANE_WORKSPACE_SLUG", "")
