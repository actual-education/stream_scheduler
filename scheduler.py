import logging
from typing import NamedTuple
from datetime import datetime, timedelta, timezone

from calendar_client import GoogleCalendarClient
from config import load_settings, validate_settings
from database import StateStore
from event_parser import EventParser
from retry import run_with_retries
from youtube_client import YouTubeSchedulerClient


class StreamTarget(NamedTuple):
    variant: str
    stream_id: str
    title_suffix: str


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

    targets = [StreamTarget("horizontal", settings.youtube_stream_id, "")]
    if settings.youtube_vertical_stream_id:
        targets.append(
            StreamTarget(
                "vertical",
                settings.youtube_vertical_stream_id,
                settings.vertical_title_suffix,
            )
        )

    usable_targets = []
    for target in targets:
        stream_ok = run_with_retries(
            lambda: youtube_client.stream_exists(target.stream_id),
            max_retries=settings.max_retries,
            base_delay_seconds=settings.retry_base_seconds,
        )
        if stream_ok:
            usable_targets.append(target)
        else:
            logging.error(
                "stream_key_missing | variant=%s | youtube_stream_id=%s | action=skip_variant "
                "| fix=update the stream ID in .env (run list_streams.py)",
                target.variant,
                target.stream_id,
            )

    if not usable_targets:
        return

    scheduling_window = timedelta(hours=12)

    for event in candidates:
        time_until_start = event.start - now
        if time_until_start > scheduling_window:
            logging.info(
                "skip_too_far_in_future | calendar_event_id=%s | title=%s | starts_in_hours=%.2f",
                event.event_id,
                event.title,
                time_until_start.total_seconds() / 3600,
            )
            continue

        if not event.event_id:
            logging.warning("skip_event_missing_id | title=%s", event.title)
            continue

        for target in usable_targets:
            schedule_event_for_target(
                event=event,
                target=target,
                settings=settings,
                state_store=state_store,
                youtube_client=youtube_client,
            )


def schedule_event_for_target(*, event, target, settings, state_store, youtube_client) -> None:
    # Horizontal keeps the bare calendar id so existing state entries still match.
    state_key = event.event_id if target.variant == "horizontal" else f"{event.event_id}::{target.variant}"
    scheduled_start_iso = event.start.isoformat().replace("+00:00", "Z")
    scheduled_end_iso = event.end.isoformat().replace("+00:00", "Z")

    if state_store.has_event(state_key):
        recorded_event = state_store.get_event(state_key) or {}
        recorded_broadcast_id = recorded_event.get("youtube_broadcast_id", "")
        if recorded_broadcast_id and not run_with_retries(
            lambda: youtube_client.broadcast_exists(recorded_broadcast_id),
            max_retries=settings.max_retries,
            base_delay_seconds=settings.retry_base_seconds,
        ):
            logging.warning(
                "stale_state_missing_broadcast | calendar_event_id=%s | variant=%s | youtube_broadcast_id=%s | action=delete_state_and_reschedule",
                event.event_id,
                target.variant,
                recorded_broadcast_id,
            )
            state_store.delete_event(state_key)
        else:
            logging.info(
                "skip_already_processed | calendar_event_id=%s | variant=%s | title=%s",
                event.event_id,
                target.variant,
                event.title,
            )
            return

    if state_store.has_scheduled_start(scheduled_start_iso, target.variant):
        logging.info(
            "skip_duplicate_start_time | calendar_event_id=%s | variant=%s | title=%s | scheduled_start=%s",
            event.event_id,
            target.variant,
            event.title,
            scheduled_start_iso,
        )
        return

    stream_title = build_title(
        settings.stream_title_template,
        settings.default_stream_title,
        event.title,
    )
    if target.title_suffix:
        # YouTube titles max out at 100 characters.
        stream_title = stream_title[: 100 - len(target.title_suffix)].rstrip() + target.title_suffix

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

        try:
            run_with_retries(
                lambda: youtube_client.bind_broadcast_to_stream(
                    broadcast_id=broadcast_id,
                    stream_id=target.stream_id,
                ),
                max_retries=settings.max_retries,
                base_delay_seconds=settings.retry_base_seconds,
            )
        except Exception:
            # Don't leave an unbound broadcast behind: the next run would create another one.
            try:
                youtube_client.delete_broadcast(broadcast_id)
                logging.warning(
                    "bind_failed_broadcast_deleted | calendar_event_id=%s | variant=%s | youtube_broadcast_id=%s",
                    event.event_id,
                    target.variant,
                    broadcast_id,
                )
            except Exception:
                logging.exception(
                    "bind_failed_cleanup_failed | calendar_event_id=%s | variant=%s | youtube_broadcast_id=%s",
                    event.event_id,
                    target.variant,
                    broadcast_id,
                )
            raise

        state_store.record_event(
            calendar_event_id=state_key,
            youtube_broadcast_id=broadcast_id,
            event_title=event.title,
            scheduled_start=scheduled_start_iso,
            variant=target.variant,
        )

        if settings.youtube_enable_monetization:
            try:
                run_with_retries(
                    lambda: youtube_client.enable_broadcast_monetization(
                        broadcast_id=broadcast_id,
                        optimization_mode=settings.youtube_monetization_optimization,
                    ),
                    max_retries=settings.max_retries,
                    base_delay_seconds=settings.retry_base_seconds,
                )
            except Exception:
                logging.exception(
                    "monetization_failed | calendar_event_id=%s | variant=%s | youtube_broadcast_id=%s",
                    event.event_id,
                    target.variant,
                    broadcast_id,
                )

        logging.info(
            "scheduled_success | calendar_event_id=%s | variant=%s | youtube_broadcast_id=%s | title=%s | status=created",
            event.event_id,
            target.variant,
            broadcast_id,
            stream_title,
        )
    except Exception as exc:
        logging.exception(
            "scheduled_error | calendar_event_id=%s | variant=%s | title=%s | error=%s",
            event.event_id,
            target.variant,
            event.title,
            str(exc),
        )

if __name__ == "__main__":
    run_once()
