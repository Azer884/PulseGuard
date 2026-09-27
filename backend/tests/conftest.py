import pytest

from app.dependencies import get_employee_service, get_plane_service, get_project_service
from app.integrations.plane.service import PlaneService
from app.main import app
from app.services.employee_service import EmployeeService
from app.services.project_service import ProjectService


@pytest.fixture(autouse=True)
def isolated_services(tmp_path):
    """Every test gets fresh stores in a temp dir; real data files are never touched."""
    employees = EmployeeService(tmp_path / "team.json")
    projects = ProjectService(tmp_path / "projects.json")
    plane = PlaneService(tmp_path / "plane.json", projects)
    app.dependency_overrides[get_employee_service] = lambda: employees
    app.dependency_overrides[get_project_service] = lambda: projects
    app.dependency_overrides[get_plane_service] = lambda: plane
    yield {"employees": employees, "projects": projects, "plane": plane}
    app.dependency_overrides.clear()
