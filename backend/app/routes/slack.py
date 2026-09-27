from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ..dependencies import get_employee_service, get_slack_client
from ..models.employee import EmployeeInput
from ..models.onboarding import ImportResult, SlackImportRequest, SlackMember, SlackStatus
from ..services.employee_service import EmployeeService, NewEmployee
from ..services.slack_client import SlackClient, SlackError, slack_ref

router = APIRouter(prefix="/api/integrations/slack", tags=["slack"])

NOT_CONFIGURED = "Slack is not connected. Set SLACK_BOT_TOKEN in backend/.env and restart the backend."


def _require(client: SlackClient | None) -> SlackClient:
    if client is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
    return client


@router.get("/status", response_model=SlackStatus)
def slack_status(client: SlackClient | None = Depends(get_slack_client)):
    if client is None:
        return SlackStatus(configured=False, connected=False)
    try:
        return SlackStatus(configured=True, connected=True, workspace=client.workspace_name())
    except SlackError as exc:
        return SlackStatus(configured=True, connected=False, error=str(exc))


@router.get("/members", response_model=list[SlackMember])
def slack_members(
    client: SlackClient | None = Depends(get_slack_client),
    service: EmployeeService = Depends(get_employee_service),
):
    try:
        members = _require(client).list_members()
    except SlackError as exc:
        raise HTTPException(status_code=502, detail=f"Slack error: {exc}")
    refs = service.external_refs()
    return [m.model_copy(update={"existing_employee_id": refs.get(slack_ref(m.slack_user_id))}) for m in members]


@router.post("/import", response_model=ImportResult)
def slack_import(
    request: SlackImportRequest,
    client: SlackClient | None = Depends(get_slack_client),
    service: EmployeeService = Depends(get_employee_service),
):
    slack = _require(client)
    entries: list[NewEmployee] = []
    errors: list[dict] = []
    for index, member in enumerate(request.members):
        try:
            # Identity comes from Slack itself, never from the client payload.
            profile = slack.get_member(member.slack_user_id)
        except SlackError as exc:
            raise HTTPException(status_code=502, detail=f"Slack error: {exc}")
        if profile is None:
            errors.append({"loc": ["body", "members", index, "slack_user_id"], "msg": "Slack user not found or not a person"})
            continue
        try:
            payload = EmployeeInput(
                name=profile.name,
                current_role=member.current_role or profile.title or "",
                skills=member.skills,
                experience_years=member.experience_years,
                available_roles=member.available_roles,
                current_workload_hours=member.current_workload_hours,
                weekly_available_hours=member.weekly_available_hours,
            )
        except ValidationError as exc:
            errors.extend(
                {"loc": ["body", "members", index, *err["loc"]], "msg": err["msg"]} for err in exc.errors()
            )
            continue
        entries.append(NewEmployee(payload, external_ref=slack_ref(member.slack_user_id)))

    if errors:
        raise HTTPException(status_code=422, detail=errors)
    created, skipped = service.create_many(entries, source="slack", generate_twins=request.generate_twins)
    return ImportResult(created=created, skipped=skipped)
