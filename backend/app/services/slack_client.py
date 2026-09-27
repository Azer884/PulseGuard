"""Minimal read-only Slack Web API client (bot token, `users:read` scope).

Only workspace identity data is read: display name and profile title. No
messages, presence, or activity are ever requested.
"""
from __future__ import annotations

import httpx

from ..models.onboarding import SlackMember

SLACK_API_BASE = "https://slack.com/api/"
MAX_PAGES = 50


class SlackError(Exception):
    pass


def slack_ref(slack_user_id: str) -> str:
    return f"slack:{slack_user_id}"


def _to_member(user: dict) -> SlackMember:
    profile = user.get("profile") or {}
    name = profile.get("real_name") or user.get("real_name") or profile.get("display_name") or user.get("name") or user["id"]
    return SlackMember(slack_user_id=user["id"], name=name.strip(), title=(profile.get("title") or "").strip() or None)


def _is_person(user: dict) -> bool:
    return not (user.get("deleted") or user.get("is_bot") or user.get("is_app_user") or user.get("id") == "USLACKBOT")


class SlackClient:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=SLACK_API_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
            transport=transport,
        )

    def _call(self, method: str, params: dict | None = None) -> dict:
        try:
            response = self._http.get(method, params=params)
        except httpx.HTTPError as exc:
            raise SlackError(f"network error contacting Slack: {exc.__class__.__name__}") from exc
        if response.status_code == 429:
            raise SlackError("rate limited by Slack; try again shortly")
        try:
            data = response.json()
        except ValueError as exc:
            raise SlackError(f"unexpected Slack response (HTTP {response.status_code})") from exc
        if not data.get("ok"):
            raise SlackError(data.get("error", "unknown Slack error"))
        return data

    def workspace_name(self) -> str | None:
        return self._call("auth.test").get("team")

    def list_members(self) -> list[SlackMember]:
        members: list[SlackMember] = []
        cursor = None
        for _ in range(MAX_PAGES):
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._call("users.list", params)
            members.extend(_to_member(u) for u in data.get("members", []) if _is_person(u))
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return sorted(members, key=lambda m: (m.name.lower(), m.slack_user_id))

    def get_member(self, slack_user_id: str) -> SlackMember | None:
        try:
            user = self._call("users.info", {"user": slack_user_id})["user"]
        except SlackError as exc:
            if str(exc) == "user_not_found":
                return None
            raise
        return _to_member(user) if _is_person(user) else None
