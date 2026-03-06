import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"processed_events": {}}

        try:
            with self.path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {"processed_events": {}}

        if not isinstance(payload, dict):
            return {"processed_events": {}}

        payload.setdefault("processed_events", {})
        if not isinstance(payload["processed_events"], dict):
            payload["processed_events"] = {}
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        tmp_path.replace(self.path)

    def has_event(self, calendar_event_id: str) -> bool:
        payload = self._read()
        return calendar_event_id in payload["processed_events"]

    def has_scheduled_start(self, scheduled_start: str) -> bool:
        payload = self._read()
        for event_data in payload["processed_events"].values():
            if not isinstance(event_data, dict):
                continue
            if event_data.get("scheduled_start") == scheduled_start:
                return True
        return False

    def record_event(
        self,
        calendar_event_id: str,
        youtube_broadcast_id: str,
        event_title: str,
        scheduled_start: str,
    ) -> None:
        payload = self._read()
        payload["processed_events"][calendar_event_id] = {
            "youtube_broadcast_id": youtube_broadcast_id,
            "event_title": event_title,
            "scheduled_start": scheduled_start,
            "creation_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._write(payload)
