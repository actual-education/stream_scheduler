import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen


@dataclass
class CalendarEvent:
    event_id: str
    title: str
    start_raw: str
    end_raw: str
    description: str


class GoogleCalendarClient:
    BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"

    def __init__(self, calendar_id: str, api_key: str, timeout_seconds: int = 20):
        self.calendar_id = calendar_id
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        params = {
            "key": self.api_key,
            "timeMin": start.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "timeMax": end.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        }

        url = f"{self.BASE_URL}/{quote(self.calendar_id, safe='')}/events?{urlencode(params)}"
        req = Request(url=url, method="GET")

        with urlopen(req, timeout=self.timeout_seconds) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")

        if status_code != 200:
            raise RuntimeError(f"Google Calendar API error ({status_code}): {body}")

        payload = json.loads(body)
        if "items" not in payload or not isinstance(payload["items"], list):
            raise RuntimeError("Unexpected Google Calendar API payload")

        return [self._normalize_event(item) for item in payload["items"]]

    @staticmethod
    def _normalize_event(item: dict[str, Any]) -> CalendarEvent:
        start = item.get("start", {})
        end = item.get("end", {})

        start_raw = start.get("dateTime") or start.get("date") or ""
        end_raw = end.get("dateTime") or end.get("date") or ""

        return CalendarEvent(
            event_id=item.get("id", ""),
            title=item.get("summary", "(No title)"),
            start_raw=start_raw,
            end_raw=end_raw,
            description=item.get("description", ""),
        )
