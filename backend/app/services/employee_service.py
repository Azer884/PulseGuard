"""Employee + twin persistence in a single JSON file.

Kept deliberately small: the project has no database yet. Writes are atomic
(temp file + replace) and serialized with a lock.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from ..models.employee import Employee, EmployeeInput, EmployeeSummary, OnboardingSource, TwinStatus
from ..models.twin import AITwin
from .twin_generator import GENERATOR_VERSION, employee_fingerprint, generate_twin


@dataclass(frozen=True)
class NewEmployee:
    payload: EmployeeInput
    # Stable ID in the source system (e.g. "slack:U0123"), used to prevent duplicate imports.
    external_ref: str | None = None


class EmployeeNotFound(Exception):
    pass


class TwinNotFound(Exception):
    pass


class EmployeeService:
    def __init__(self, store_path: Path):
        self._path = Path(store_path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not self._path.exists():
            return {"next_id": 1, "employees": {}, "twins": {}}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    @staticmethod
    def _twin_status(employee: Employee, twin: dict | None) -> TwinStatus:
        if twin is None:
            return "not_generated"
        current = twin.get("source_fingerprint") == employee_fingerprint(employee)
        return "generated" if current and twin.get("generator_version") == GENERATOR_VERSION else "outdated"

    def _summary(self, data: dict, employee_id: str) -> EmployeeSummary:
        employee = Employee(**data["employees"][employee_id])
        status = self._twin_status(employee, data["twins"].get(employee_id))
        return EmployeeSummary(**employee.model_dump(), twin_status=status)

    def list(self) -> list[EmployeeSummary]:
        with self._lock:
            data = self._load()
            return [self._summary(data, eid) for eid in data["employees"]]

    def get(self, employee_id: str) -> EmployeeSummary:
        with self._lock:
            data = self._load()
            if employee_id not in data["employees"]:
                raise EmployeeNotFound(employee_id)
            return self._summary(data, employee_id)

    def create(self, payload: EmployeeInput, source: OnboardingSource = "manual") -> EmployeeSummary:
        created, _ = self.create_many([NewEmployee(payload)], source)
        return created[0]

    def create_many(
        self, entries: list["NewEmployee"], source: OnboardingSource, generate_twins: bool = False
    ) -> tuple[list[EmployeeSummary], list[dict]]:
        """Shared entry point for every onboarding method. Written in one save.
        Entries whose external_ref is already on the team are skipped, not duplicated."""
        with self._lock:
            data = self._load()
            known_refs = {e.get("external_ref") for e in data["employees"].values()} - {None}
            created_ids: list[str] = []
            skipped: list[dict] = []
            for entry in entries:
                if entry.external_ref and entry.external_ref in known_refs:
                    skipped.append({"ref": entry.external_ref, "name": entry.payload.name, "reason": "already on the team"})
                    continue
                # IDs are never reused, even after deletion.
                employee_id = f"emp_{data['next_id']:03d}"
                data["next_id"] += 1
                employee = Employee(
                    **entry.payload.model_dump(), employee_id=employee_id, source=source, external_ref=entry.external_ref
                )
                data["employees"][employee_id] = employee.model_dump()
                if generate_twins:
                    data["twins"][employee_id] = generate_twin(employee).model_dump()
                if entry.external_ref:
                    known_refs.add(entry.external_ref)
                created_ids.append(employee_id)
            if created_ids:
                self._save(data)
            return [self._summary(data, eid) for eid in created_ids], skipped

    def external_refs(self) -> dict[str, str]:
        with self._lock:
            data = self._load()
            return {e["external_ref"]: eid for eid, e in data["employees"].items() if e.get("external_ref")}

    def update(self, employee_id: str, payload: EmployeeInput) -> EmployeeSummary:
        with self._lock:
            data = self._load()
            existing = data["employees"].get(employee_id)
            if existing is None:
                raise EmployeeNotFound(employee_id)
            data["employees"][employee_id] = Employee(
                **payload.model_dump(),
                employee_id=employee_id,
                source=existing["source"],
                external_ref=existing.get("external_ref"),
            ).model_dump()
            self._save(data)
            return self._summary(data, employee_id)

    def delete(self, employee_id: str) -> None:
        _, not_found = self.delete_many([employee_id])
        if not_found:
            raise EmployeeNotFound(employee_id)

    def delete_many(self, employee_ids: list[str]) -> tuple[list[str], list[str]]:
        with self._lock:
            data = self._load()
            deleted, not_found = [], []
            for employee_id in dict.fromkeys(employee_ids):
                if data["employees"].pop(employee_id, None) is None:
                    not_found.append(employee_id)
                    continue
                data["twins"].pop(employee_id, None)
                deleted.append(employee_id)
            if deleted:
                self._save(data)
            return deleted, not_found

    def generate_twin(self, employee_id: str) -> AITwin:
        with self._lock:
            data = self._load()
            if employee_id not in data["employees"]:
                raise EmployeeNotFound(employee_id)
            twin = generate_twin(Employee(**data["employees"][employee_id]))
            data["twins"][employee_id] = twin.model_dump()
            self._save(data)
            return twin

    def twins(self) -> dict[str, AITwin]:
        with self._lock:
            data = self._load()
            return {eid: AITwin(**twin) for eid, twin in data["twins"].items() if eid in data["employees"]}

    def get_twin(self, employee_id: str) -> AITwin:
        with self._lock:
            data = self._load()
            if employee_id not in data["employees"]:
                raise EmployeeNotFound(employee_id)
            twin = data["twins"].get(employee_id)
            if twin is None:
                raise TwinNotFound(employee_id)
            return AITwin(**twin)
