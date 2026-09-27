"""Thin, read-only client for the official Plane REST API (v1).

Endpoints used (all under {base_url}/api/v1, header `X-API-Key`):
  GET users/me/
  GET workspaces/{slug}/members/
  GET workspaces/{slug}/projects/
  GET workspaces/{slug}/projects/{project_id}/
  GET workspaces/{slug}/projects/{project_id}/states/
  GET workspaces/{slug}/projects/{project_id}/labels/
  GET workspaces/{slug}/projects/{project_id}/cycles/
  GET workspaces/{slug}/projects/{project_id}/cycles/{cycle_id}/cycle-issues/
  GET workspaces/{slug}/projects/{project_id}/work-items/
  GET workspaces/{slug}/projects/{project_id}/work-items/{work_item_id}/relations/
  GET workspaces/{slug}/projects/{project_id}/estimates/{estimate_id}/estimate-points/

List endpoints may return a plain list or Plane's cursor-paginated envelope
({"results": [...], "next_cursor": ..., "next_page_results": bool}); both are handled.
Plane allows 60 requests per minute per client; `request_count` lets callers budget.
"""
from __future__ import annotations

import httpx

API_PREFIX = "/api/v1/"
PAGE_SIZE = 100
MAX_PAGES = 50


class PlaneError(Exception):
    pass


class PlaneAuthError(PlaneError):
    pass


class PlaneNotFound(PlaneError):
    pass


class PlaneRateLimited(PlaneError):
    pass


class PlaneClient:
    def __init__(self, base_url: str, api_key: str, workspace_slug: str, transport: httpx.BaseTransport | None = None):
        self.workspace_slug = workspace_slug
        self.request_count = 0
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + API_PREFIX,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=15.0,
            transport=transport,
        )

    def _get(self, path: str, params: dict | None = None):
        self.request_count += 1
        try:
            response = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise PlaneError(f"could not reach Plane ({exc.__class__.__name__})") from exc
        if response.status_code in (401, 403):
            raise PlaneAuthError("Plane rejected the API key or it lacks access to this workspace")
        if response.status_code == 404:
            raise PlaneNotFound(f"not found: {path}")
        if response.status_code == 429:
            raise PlaneRateLimited("Plane rate limit reached (60 requests/minute); wait a minute and try again")
        if response.status_code >= 400:
            raise PlaneError(f"Plane returned HTTP {response.status_code} for {path}")
        try:
            return response.json()
        except ValueError as exc:
            raise PlaneError(f"Plane returned a non-JSON response for {path}; check the base URL") from exc

    def _list(self, path: str, params: dict | None = None) -> list[dict]:
        params = {**(params or {}), "per_page": PAGE_SIZE}
        results: list[dict] = []
        for _ in range(MAX_PAGES):
            data = self._get(path, params)
            if isinstance(data, list):
                return results + data
            results.extend(data.get("results", []))
            if not data.get("next_page_results") or not data.get("next_cursor"):
                break
            params["cursor"] = data["next_cursor"]
        return results

    def _ws(self, path: str = "") -> str:
        return f"workspaces/{self.workspace_slug}/{path}"

    def _project(self, project_id: str, path: str = "") -> str:
        return self._ws(f"projects/{project_id}/{path}")

    def me(self) -> dict:
        return self._get("users/me/")

    def list_members(self) -> list[dict]:
        return self._list(self._ws("members/"))

    def list_projects(self) -> list[dict]:
        return self._list(self._ws("projects/"))

    def get_project(self, project_id: str) -> dict:
        return self._get(self._project(project_id))

    def list_states(self, project_id: str) -> list[dict]:
        return self._list(self._project(project_id, "states/"))

    def list_labels(self, project_id: str) -> list[dict]:
        return self._list(self._project(project_id, "labels/"))

    def list_cycles(self, project_id: str) -> list[dict]:
        return self._list(self._project(project_id, "cycles/"))

    def list_cycle_work_items(self, project_id: str, cycle_id: str) -> list[dict]:
        return self._list(self._project(project_id, f"cycles/{cycle_id}/cycle-issues/"))

    def list_work_items(self, project_id: str) -> list[dict]:
        return self._list(self._project(project_id, "work-items/"))

    def list_relations(self, project_id: str, work_item_id: str) -> dict:
        return self._get(self._project(project_id, f"work-items/{work_item_id}/relations/"))

    def list_estimate_points(self, project_id: str, estimate_id: str) -> list[dict]:
        return self._list(self._project(project_id, f"estimates/{estimate_id}/estimate-points/"))
