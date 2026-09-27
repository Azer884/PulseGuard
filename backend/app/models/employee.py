"""Employee source data. Every onboarding method (manual form now; Slack and
JSON import later) must produce this same model before a twin is generated."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

OnboardingSource = Literal["manual", "slack", "json_import"]
TwinStatus = Literal["not_generated", "generated", "outdated"]


def _clean_list(values: list[str]) -> list[str]:
    """Strip entries, drop blanks, dedupe case-insensitively keeping first spelling."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            cleaned.append(item)
    return cleaned


class EmployeeInput(BaseModel):
    name: str = Field(max_length=120)
    current_role: str = Field(max_length=120)
    skills: list[str] = Field(default_factory=list, max_length=50)
    experience_years: float = Field(ge=0, le=60)
    available_roles: list[str] = Field(default_factory=list, max_length=20)
    current_workload_hours: float = Field(ge=0, le=168)
    weekly_available_hours: float = Field(gt=0, le=168)

    @field_validator("name", "current_role")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("skills", "available_roles")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        return _clean_list(values)

    @model_validator(mode="after")
    def _current_role_is_available(self) -> "EmployeeInput":
        # The analysis engine flags "role mismatch" when current_role is not in
        # available_roles, so an employee's own role is always kept available.
        if self.current_role.lower() not in {r.lower() for r in self.available_roles}:
            self.available_roles = [self.current_role, *self.available_roles]
        return self


class Employee(EmployeeInput):
    employee_id: str
    source: OnboardingSource = "manual"
    external_ref: str | None = None


class EmployeeSummary(Employee):
    twin_status: TwinStatus
