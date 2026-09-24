"""ServiceNow-style incident lookup and work-note update integration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping, Optional

from incidentpack.integrations.http import ApiError, JsonApiClient
from incidentpack.validation import validate_https_endpoint


class ServiceNowError(ApiError):
    """Raised when ServiceNow configuration or incident data is invalid."""


@dataclass(frozen=True)
class ServiceNowSettings:
    url: str
    username: str
    password: str = field(repr=False)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "ServiceNowSettings":
        values = env if env is not None else os.environ
        url = (values.get("SERVICENOW_URL") or "").strip().rstrip("/")
        username = (values.get("SERVICENOW_USER") or "").strip()
        password = values.get("SERVICENOW_PASSWORD") or ""
        missing = [
            name
            for name, value in (
                ("SERVICENOW_URL", url),
                ("SERVICENOW_USER", username),
                ("SERVICENOW_PASSWORD", password),
            )
            if not value
        ]
        if missing:
            raise ServiceNowError(
                f"Missing ServiceNow environment variable(s): {', '.join(missing)}"
            )
        try:
            url = validate_https_endpoint(url, "SERVICENOW_URL")
        except ValueError as error:
            raise ServiceNowError(str(error)) from error
        return cls(url=url, username=username, password=password)


@dataclass(frozen=True)
class ServiceNowIncident:
    sys_id: str
    number: str
    short_description: str = ""
    state: str = ""
    priority: str = ""


class ServiceNowClient:
    """Minimal incident-table client for operational ticket workflow integration."""

    def __init__(
        self,
        settings: ServiceNowSettings,
        http: Optional[JsonApiClient] = None,
    ) -> None:
        self.settings = settings
        self.http = http or JsonApiClient()

    @property
    def _auth(self) -> tuple[str, str]:
        return (self.settings.username, self.settings.password)

    def get_incident(self, number: str) -> ServiceNowIncident:
        incident_number = number.strip().upper()
        if not incident_number:
            raise ServiceNowError("ServiceNow incident number cannot be empty")
        if not re.fullmatch(r"INC\d+", incident_number):
            raise ServiceNowError(
                "ServiceNow incident number must use the form INC followed by digits"
            )

        try:
            payload = self.http.request_json(
                "GET",
                f"{self.settings.url}/api/now/table/incident",
                headers={"Accept": "application/json"},
                params={
                    "sysparm_query": f"number={incident_number}",
                    "sysparm_limit": 1,
                    "sysparm_fields": "sys_id,number,short_description,state,priority",
                },
                auth=self._auth,
            )
        except ApiError as error:
            raise ServiceNowError(f"ServiceNow lookup failed: {error}") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), list):
            raise ServiceNowError("ServiceNow incident response is missing a result list")
        results = payload["result"]
        if not results:
            raise ServiceNowError(f"Incident '{incident_number}' was not found")
        item = results[0]
        if not isinstance(item, dict):
            raise ServiceNowError("ServiceNow incident result must be a JSON object")
        sys_id = str(item.get("sys_id") or "").strip()
        if not sys_id:
            raise ServiceNowError("ServiceNow incident result is missing sys_id")
        return ServiceNowIncident(
            sys_id=sys_id,
            number=str(item.get("number") or incident_number).strip(),
            short_description=str(item.get("short_description") or "").strip(),
            state=str(item.get("state") or "").strip(),
            priority=str(item.get("priority") or "").strip(),
        )

    def add_work_notes(self, number: str, notes: str) -> ServiceNowIncident:
        """Resolve an incident number and append work notes using an explicit PATCH."""
        if not notes.strip():
            raise ServiceNowError("Work notes cannot be empty")
        incident = self.get_incident(number)
        try:
            payload = self.http.request_json(
                "PATCH",
                f"{self.settings.url}/api/now/table/incident/{incident.sys_id}",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json_body={"work_notes": notes},
                auth=self._auth,
            )
        except ApiError as error:
            raise ServiceNowError(f"ServiceNow update failed: {error}") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise ServiceNowError("ServiceNow update response is missing a result object")
        return incident
