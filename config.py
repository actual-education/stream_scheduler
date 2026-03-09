import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    google_calendar_id: str
    google_api_key: str
    youtube_client_secrets_file: Path
    youtube_token_file: Path
    youtube_stream_id: str
    youtube_channel_id: str
    youtube_privacy_status: str
    youtube_category_id: str
    youtube_enable_monetization: bool
    youtube_monetization_optimization: str
    poll_interval_hours: int
    lookahead_hours: int
    title_keywords: tuple[str, ...]
    default_stream_title: str
    stream_title_template: str
    stream_description_template: str
    stream_title_file: Path
    stream_description_file: Path
    state_file: Path
    log_file: Path
    timezone: str
    max_retries: int
    retry_base_seconds: float


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_path(path_value: str, fallback: Path) -> Path:
    if not path_value:
        return fallback
    path = Path(path_value)
    return path if path.is_absolute() else (Path.cwd() / path)


def _split_keywords(raw: str) -> tuple[str, ...]:
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(parts)


def _multiline_env(name: str, default: str) -> str:
    # Allow .env values to contain \n escape sequences for readable templates.
    return _env(name, default).replace("\\n", "\n")


def _load_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent

    title_file = _resolve_path(_env("STREAM_TITLE_FILE"), base_dir / "streamTitle.txt")
    description_file = _resolve_path(
        _env("STREAM_DESCRIPTION_FILE"), base_dir / "streamDescription.txt"
    )

    env_title_template = _env(
        "STREAM_TITLE_TEMPLATE", "{event_title} | Live Office Hours"
    )
    env_description_template = _multiline_env(
        "STREAM_DESCRIPTION_TEMPLATE",
        "Live math and physics homework help stream.\\n\\n"
        "Submit your question:\\n"
        "https://actualofficehours.com\\n\\n"
        "Questions are selected using a weighted spinner system where older questions "
        "and upvotes increase the odds of being selected.\\n\\n"
        "Join the queue:\\n"
        "https://actualofficehours.com",
    )

    file_title_template = _load_text_file(title_file)
    file_description_template = _load_text_file(description_file)

    return Settings(
        google_calendar_id=_env("GOOGLE_CALENDAR_ID"),
        google_api_key=_env("GOOGLE_CALENDAR_API_KEY"),
        youtube_client_secrets_file=_resolve_path(
            _env("YOUTUBE_CLIENT_SECRETS_FILE"),
            base_dir / "client_secret.json",
        ),
        youtube_token_file=_resolve_path(
            _env("YOUTUBE_TOKEN_FILE"),
            base_dir / "data" / "youtube_token.json",
        ),
        youtube_stream_id=_env("YOUTUBE_STREAM_ID"),
        youtube_channel_id=_env("YOUTUBE_CHANNEL_ID"),
        youtube_privacy_status=_env("YOUTUBE_PRIVACY_STATUS", "public") or "public",
        youtube_category_id=_env("YOUTUBE_CATEGORY_ID", "27") or "27",
        youtube_enable_monetization=_env_bool("YOUTUBE_ENABLE_MONETIZATION", True),
        youtube_monetization_optimization=(
            _env("YOUTUBE_MONETIZATION_OPTIMIZATION", "MEDIUM").upper() or "MEDIUM"
        ),
        poll_interval_hours=int(_env("POLL_INTERVAL_HOURS", "4") or "4"),
        lookahead_hours=int(_env("LOOKAHEAD_HOURS", "12") or "12"),
        title_keywords=_split_keywords(
            _env("EVENT_TITLE_KEYWORDS", "Actual Education,Office Hours")
        ),
        default_stream_title=_env(
            "DEFAULT_STREAM_TITLE", "Math & Physics Homework Help | Live Office Hours"
        ),
        stream_title_template=file_title_template or env_title_template,
        stream_description_template=file_description_template or env_description_template,
        stream_title_file=title_file,
        stream_description_file=description_file,
        state_file=_resolve_path(_env("STATE_FILE"), base_dir / "data" / "state.json"),
        log_file=_resolve_path(
            _env("STREAM_SCHEDULER_LOG_FILE"), base_dir / "logs" / "stream_scheduler.log"
        ),
        timezone=_env("SCHEDULER_TIMEZONE", "America/Los_Angeles") or "America/Los_Angeles",
        max_retries=int(_env("MAX_RETRIES", "3") or "3"),
        retry_base_seconds=float(_env("RETRY_BASE_SECONDS", "2") or "2"),
    )


def validate_settings(settings: Settings) -> None:
    missing = []
    if not settings.google_calendar_id:
        missing.append("GOOGLE_CALENDAR_ID")
    if not settings.google_api_key:
        missing.append("GOOGLE_CALENDAR_API_KEY")
    if not settings.youtube_stream_id:
        missing.append("YOUTUBE_STREAM_ID")

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    if settings.youtube_monetization_optimization not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError(
            "YOUTUBE_MONETIZATION_OPTIMIZATION must be one of: LOW, MEDIUM, HIGH"
        )

    settings.state_file.parent.mkdir(parents=True, exist_ok=True)
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
