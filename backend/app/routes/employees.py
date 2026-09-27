from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..dependencies import get_employee_service, get_project_service
from ..models.employee import EmployeeInput, EmployeeSummary
from ..models.onboarding import BulkDeleteRequest, BulkDeleteResult, ImportResult, JsonImportRequest
from ..models.twin import AITwin
from ..services.employee_service import EmployeeNotFound, EmployeeService, NewEmployee, TwinNotFound
from ..services.project_service import ProjectService

router = APIRouter(prefix="/api/employees", tags=["employees"])


Service = Depends(get_employee_service)
Project = Depends(get_project_service)


def _not_found(employee_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")


@router.post("", response_model=EmployeeSummary, status_code=status.HTTP_201_CREATED)
def create_employee(payload: EmployeeInput, service: EmployeeService = Service):
    return service.create(payload, source="manual")


@router.post("/import", response_model=ImportResult)
def import_employees(request: JsonImportRequest, service: EmployeeService = Service):
    # All rows are validated by the request model first, so a bad row imports nothing.
    created, skipped = service.create_many(
        [NewEmployee(payload) for payload in request.employees], source="json_import", generate_twins=request.generate_twins
    )
    return ImportResult(created=created, skipped=skipped)


@router.post("/bulk-delete", response_model=BulkDeleteResult)
def bulk_delete_employees(request: BulkDeleteRequest, service: EmployeeService = Service, project: ProjectService = Project):
    deleted, not_found = service.delete_many(request.employee_ids)
    project.unassign_employees(deleted)
    return BulkDeleteResult(deleted=deleted, not_found=not_found)


@router.get("", response_model=list[EmployeeSummary])
def list_employees(service: EmployeeService = Service):
    return service.list()


@router.get("/{employee_id}", response_model=EmployeeSummary)
def get_employee(employee_id: str, service: EmployeeService = Service):
    try:
        return service.get(employee_id)
    except EmployeeNotFound:
        raise _not_found(employee_id)


@router.put("/{employee_id}", response_model=EmployeeSummary)
def update_employee(employee_id: str, payload: EmployeeInput, service: EmployeeService = Service):
    try:
        return service.update(employee_id, payload)
    except EmployeeNotFound:
        raise _not_found(employee_id)


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: str, service: EmployeeService = Service, project: ProjectService = Project):
    try:
        service.delete(employee_id)
    except EmployeeNotFound:
        raise _not_found(employee_id)
    project.unassign_employees([employee_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{employee_id}/generate-twin", response_model=AITwin)
def generate_twin(employee_id: str, service: EmployeeService = Service):
    try:
        return service.generate_twin(employee_id)
    except EmployeeNotFound:
        raise _not_found(employee_id)


@router.get("/{employee_id}/twin", response_model=AITwin)
def get_twin(employee_id: str, service: EmployeeService = Service):
    try:
        return service.get_twin(employee_id)
    except EmployeeNotFound:
        raise _not_found(employee_id)
    except TwinNotFound:
        raise HTTPException(status_code=404, detail=f"No AI Twin generated yet for '{employee_id}'")
