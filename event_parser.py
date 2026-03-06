from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from calendar_client import CalendarEvent


@dataclass
class ParsedEvent:
    event_id: str
    title: str
    start: datetime
    end: datetime
    description: str


class EventParser:
    def __init__(self, title_keywords: tuple[str, ...]):
        self.title_keywords = tuple(k.lower() for k in title_keywords if k.strip())

    def filter_upcoming_events(
        self,
        events: list[CalendarEvent],
        *,
        now: datetime,
        lookahead_hours: int,
    ) -> list[ParsedEvent]:
        window_end = now + timedelta(hours=lookahead_hours)
        matching: list[ParsedEvent] = []

        for event in events:
            parsed = self._parse(event)
            if not parsed:
                continue
            if parsed.start < now or parsed.start > window_end:
                continue
            if not self._matches_title(parsed.title):
                continue
            matching.append(parsed)

        return sorted(matching, key=lambda ev: ev.start)

    def _matches_title(self, title: str) -> bool:
        if not self.title_keywords:
            return False
        normalized = title.lower()
        return all(keyword in normalized for keyword in self.title_keywords)

    @staticmethod
    def _parse(event: CalendarEvent) -> ParsedEvent | None:
        start = _parse_google_datetime(event.start_raw)
        end = _parse_google_datetime(event.end_raw)
        if not start or not end:
            return None

        if end <= start:
            end = start + timedelta(hours=2)

        return ParsedEvent(
            event_id=event.event_id,
            title=event.title,
            start=start,
            end=end,
            description=event.description,
        )


def _parse_google_datetime(value: str) -> datetime | None:
    if not value:
        return None

    if "T" not in value:
        # All-day events are ignored for stream scheduling.
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)
