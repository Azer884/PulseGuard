from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..dependencies import get_employee_service, get_plane_service
from ..integrations.plane.client import PlaneAuthError, PlaneError, PlaneNotFound, PlaneRateLimited
from ..integrations.plane.models import (
    ImportReport,
    MemberMappingRequest,
    PlaneConfig,
    PlaneMember,
    PlaneProjectDetail,
    PlaneProjectSummary,
    PlaneStatus,
)
from ..integrations.plane.service import PlaneMappingError, PlaneNotConfigured, PlaneService
from ..services.employee_service import EmployeeService

integration_router = APIRouter(prefix="/api/integrations/plane", tags=["plane"])
router = APIRouter(prefix="/api/plane", tags=["plane"])

Plane = Depends(get_plane_service)
Employees = Depends(get_employee_service)


@contextmanager
def plane_errors():
    """Maps Plane integration failures to HTTP errors with actionable messages."""
    try:
        yield
    except PlaneNotConfigured:
        raise HTTPException(status_code=503, detail="Plane is not connected. Connect it under Projects or set PLANE_* in backend/.env.")
    except PlaneAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PlaneRateLimited as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PlaneNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Plane resource {exc}")
    except PlaneMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PlaneError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@integration_router.get("/status", response_model=PlaneStatus)
def plane_status(plane: PlaneService = Plane):
    return plane.status()


@integration_router.post("/connect", response_model=PlaneStatus)
def plane_connect(config: PlaneConfig, plane: PlaneService = Plane):
    with plane_errors():
        return plane.connect(config)


@integration_router.delete("/connect", status_code=status.HTTP_204_NO_CONTENT)
def plane_disconnect(plane: PlaneService = Plane):
    plane.disconnect()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects", response_model=list[PlaneProjectSummary])
def plane_projects(plane: PlaneService = Plane):
    with plane_errors():
        return plane.list_projects()


@router.get("/projects/{plane_project_id}", response_model=PlaneProjectDetail)
def plane_project(plane_project_id: str, plane: PlaneService = Plane):
    with plane_errors():
        return plane.get_project(plane_project_id)


@router.post("/projects/{plane_project_id}/import", response_model=ImportReport)
def plane_import(plane_project_id: str, plane: PlaneService = Plane):
    """Imports the project, or re-syncs it if already imported (matched by Plane IDs)."""
    with plane_errors():
        return plane.import_project(plane_project_id)


@router.get("/members", response_model=list[PlaneMember])
def plane_members(refresh: bool = True, plane: PlaneService = Plane, employees: EmployeeService = Employees):
    with plane_errors():
        return plane.members(employees.list(), refresh=refresh)


@router.put("/members/mapping", response_model=list[PlaneMember])
def plane_member_mapping(request: MemberMappingRequest, plane: PlaneService = Plane, employees: EmployeeService = Employees):
    team = employees.list()
    with plane_errors():
        plane.set_mapping(request, {e.employee_id for e in team})
        return plane.members(team, refresh=False)
