import logging
from functools import lru_cache

from pydantic import ValidationError

from .config import (
    PLANE_API_KEY,
    PLANE_BASE_URL,
    PLANE_STATE_FILE,
    PLANE_WORKSPACE_SLUG,
    PROJECTS_DATA_FILE,
    SLACK_BOT_TOKEN,
    TEAM_DATA_FILE,
)
from .integrations.plane.models import DEFAULT_PLANE_BASE_URL, PlaneConfig
from .integrations.plane.service import PlaneService
from .services.employee_service import EmployeeService
from .services.project_service import ProjectService
from .services.slack_client import SlackClient

logger = logging.getLogger(__name__)


@lru_cache
def get_employee_service() -> EmployeeService:
    return EmployeeService(TEAM_DATA_FILE)


@lru_cache
def get_project_service() -> ProjectService:
    return ProjectService(PROJECTS_DATA_FILE)


def _plane_env_config() -> PlaneConfig | None:
    if not (PLANE_API_KEY and PLANE_WORKSPACE_SLUG):
        return None
    try:
        return PlaneConfig(base_url=PLANE_BASE_URL or DEFAULT_PLANE_BASE_URL, api_key=PLANE_API_KEY, workspace_slug=PLANE_WORKSPACE_SLUG)
    except ValidationError as exc:
        logger.warning("Ignoring invalid PLANE_* environment settings: %s", exc)
        return None


@lru_cache
def get_plane_service() -> PlaneService:
    return PlaneService(PLANE_STATE_FILE, get_project_service(), env_config=_plane_env_config())


def get_slack_client() -> SlackClient | None:
    return SlackClient(SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None
