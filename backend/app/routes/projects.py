from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from ..dependencies import get_employee_service, get_plane_service, get_project_service
from ..integrations.plane.models import ImportReport
from ..integrations.plane.service import PlaneService
from ..models.project import ProjectDetail, ProjectSettings, ProjectSummary, SimulateRequest, SimulateResponse
from ..models.task import AssignmentUpdate, TaskInput, TaskOverrides, TaskView
from ..services import simulation_service
from ..services.employee_service import EmployeeService
from ..services.project_service import InvalidProjectChange, ProjectNotFound, ProjectService, TaskNotFound
from .plane import plane_errors

router = APIRouter(prefix="/api/projects", tags=["projects"])

Projects = Depends(get_project_service)
Employees = Depends(get_employee_service)
Plane = Depends(get_plane_service)


class _Context:
    def __init__(self, projects: ProjectService = Projects, employees: EmployeeService = Employees, plane: PlaneService = Plane):
        self.projects, self.employees, self.plane = projects, employees, plane

    def valid_ids(self) -> set[str]:
        return {e.employee_id for e in self.employees.list()}

    def detail(self, project_id: str) -> ProjectDetail:
        try:
            return self.projects.detail(project_id, self.plane.user_map(), self.valid_ids())
        except ProjectNotFound:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    def run(self, project_id: str, action) -> ProjectDetail:
        try:
            action()
        except ProjectNotFound:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail=f"Task '{exc}' not found")
        except InvalidProjectChange as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return self.detail(project_id)


Ctx = Depends(_Context)


@router.get("", response_model=list[ProjectSummary])
def list_projects(ctx: _Context = Ctx):
    return ctx.projects.list(ctx.plane.user_map(), ctx.valid_ids())


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, ctx: _Context = Ctx):
    return ctx.detail(project_id)


@router.get("/{project_id}/tasks", response_model=list[TaskView])
def get_tasks(project_id: str, ctx: _Context = Ctx):
    return ctx.detail(project_id).tasks


@router.post("/{project_id}/tasks", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_task(project_id: str, payload: TaskInput, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.create_task(project_id, payload))


@router.put("/{project_id}/tasks/{task_id}", response_model=ProjectDetail)
def update_task(project_id: str, task_id: str, payload: TaskInput, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.update_task(project_id, task_id, payload))


@router.put("/{project_id}/tasks/{task_id}/overrides", response_model=ProjectDetail)
def set_overrides(project_id: str, task_id: str, overrides: TaskOverrides, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.set_overrides(project_id, task_id, overrides))


@router.delete("/{project_id}/tasks/{task_id}", response_model=ProjectDetail)
def delete_task(project_id: str, task_id: str, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.delete_task(project_id, task_id))


@router.delete("/{project_id}/tasks", response_model=ProjectDetail)
def clear_tasks(project_id: str, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.clear(project_id))


@router.post("/{project_id}/sample", response_model=ProjectDetail)
def load_sample(project_id: str, ctx: _Context = Ctx):
    def action():
        if not ctx.projects.load_sample(project_id):
            raise InvalidProjectChange("the backlog is not empty; clear it before loading the sample")

    return ctx.run(project_id, action)


@router.put("/{project_id}/settings", response_model=ProjectDetail)
def update_settings(project_id: str, settings: ProjectSettings, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.update_settings(project_id, settings))


@router.put("/{project_id}/assignment", response_model=ProjectDetail)
def update_assignment(project_id: str, update: AssignmentUpdate, ctx: _Context = Ctx):
    return ctx.run(project_id, lambda: ctx.projects.apply_changes(project_id, update.changes, ctx.valid_ids()))


@router.post("/{project_id}/auto-assign", response_model=ProjectDetail)
def auto_assign(project_id: str, ctx: _Context = Ctx):
    ctx.detail(project_id)
    try:
        simulation_service.auto_assign(ctx.employees, ctx.projects, project_id, ctx.plane.user_map())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ctx.detail(project_id)


@router.post("/{project_id}/simulate", response_model=SimulateResponse)
def simulate(project_id: str, request: SimulateRequest, ctx: _Context = Ctx):
    ctx.detail(project_id)
    return simulation_service.simulate(ctx.employees, ctx.projects, project_id, request.mode, request.target_employee_id, ctx.plane.user_map())


class SyncResult(BaseModel):
    report: ImportReport
    project: ProjectDetail


@router.post("/{project_id}/sync", response_model=SyncResult)
def sync_project(project_id: str, ctx: _Context = Ctx):
    ctx.detail(project_id)
    with plane_errors():
        report = ctx.plane.sync(project_id)
    return SyncResult(report=report, project=ctx.detail(project_id))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, ctx: _Context = Ctx):
    try:
        ctx.projects.delete_project(project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    except InvalidProjectChange as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
