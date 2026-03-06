import logging
from datetime import datetime, timedelta, timezone

from calendar_client import GoogleCalendarClient
from config import load_settings, validate_settings
from database import StateStore
from event_parser import EventParser
from retry import run_with_retries
from youtube_client import YouTubeSchedulerClient


def configure_logging(log_file: str) -> None:
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def build_title(template: str, default_title: str, event_title: str) -> str:
    if "{event_title}" not in template:
        return default_title
    rendered = template.format(event_title=event_title).strip()
    return rendered or default_title


def run_once() -> None:
    settings = load_settings()
    validate_settings(settings)
    configure_logging(str(settings.log_file))

    logging.info("scheduler_start")

    now = datetime.now(timezone.utc)
    lookahead_end = now + timedelta(hours=settings.lookahead_hours)

    state_store = StateStore(settings.state_file)
    parser = EventParser(settings.title_keywords)

    calendar_client = GoogleCalendarClient(
        calendar_id=settings.google_calendar_id,
        api_key=settings.google_api_key,
    )

    youtube_client = YouTubeSchedulerClient(
        client_secrets_file=settings.youtube_client_secrets_file,
        token_file=settings.youtube_token_file,
    )

    events = run_with_retries(
        lambda: calendar_client.fetch_events(start=now, end=lookahead_end),
        max_retries=settings.max_retries,
        base_delay_seconds=settings.retry_base_seconds,
    )

    candidates = parser.filter_upcoming_events(
        events,
        now=now,
        lookahead_hours=settings.lookahead_hours,
    )

    if not candidates:
        logging.info("no_matching_events_found")
        return

    for event in candidates:
        scheduled_start_iso = event.start.isoformat().replace("+00:00", "Z")
        scheduled_end_iso = event.end.isoformat().replace("+00:00", "Z")

        if not event.event_id:
            logging.warning("skip_event_missing_id | title=%s", event.title)
            continue

        if state_store.has_event(event.event_id):
            logging.info(
                "skip_already_processed | calendar_event_id=%s | title=%s",
                event.event_id,
                event.title,
            )
            continue

        if state_store.has_scheduled_start(scheduled_start_iso):
            logging.info(
                "skip_duplicate_start_time | calendar_event_id=%s | title=%s | scheduled_start=%s",
                event.event_id,
                event.title,
                scheduled_start_iso,
            )
            continue

        stream_title = build_title(
            settings.stream_title_template,
            settings.default_stream_title,
            event.title,
        )

        try:
            broadcast_id = run_with_retries(
                lambda: youtube_client.create_broadcast(
                    title=stream_title,
                    description=settings.stream_description_template,
                    scheduled_start_iso=scheduled_start_iso,
                    scheduled_end_iso=scheduled_end_iso,
                    privacy_status=settings.youtube_privacy_status,
                    category_id=settings.youtube_category_id,
                ),
                max_retries=settings.max_retries,
                base_delay_seconds=settings.retry_base_seconds,
            )

            run_with_retries(
                lambda: youtube_client.bind_broadcast_to_stream(
                    broadcast_id=broadcast_id,
                    stream_id=settings.youtube_stream_id,
                ),
                max_retries=settings.max_retries,
                base_delay_seconds=settings.retry_base_seconds,
            )

            state_store.record_event(
                calendar_event_id=event.event_id,
                youtube_broadcast_id=broadcast_id,
                event_title=event.title,
                scheduled_start=scheduled_start_iso,
            )

            logging.info(
                "scheduled_success | calendar_event_id=%s | youtube_broadcast_id=%s | status=created",
                event.event_id,
                broadcast_id,
            )
        except Exception as exc:
            logging.exception(
                "scheduled_error | calendar_event_id=%s | title=%s | error=%s",
                event.event_id,
                event.title,
                str(exc),
            )


if __name__ == "__main__":
    run_once()
