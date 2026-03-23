# Stream Scheduler

Automates creation of scheduled YouTube livestreams from Google Calendar events.

## What It Does

- Fetches calendar events in the next `LOOKAHEAD_HOURS` (default: 12)
- Only schedules streams when the start time is within 12 hours
- Filters only events whose title contains all configured keywords (default: both):
  - `Actual Education`
  - `Office Hours`
- Creates a scheduled YouTube broadcast for each qualifying event
- Binds the broadcast to your persistent stream key (`YOUTUBE_STREAM_ID`)
- Loads stream title/description from:
  - `streamTitle.txt`
  - `streamDescription.txt`
- Prevents duplicates via `data/state.json`
- Logs all activity to `logs/stream_scheduler.log`

## Files

- `scheduler.py`: main executable
- `reAuth.py`: one-time YouTube OAuth repair helper
- `calendar_client.py`: Google Calendar API fetcher
- `youtube_client.py`: YouTube broadcast create/bind
- `event_parser.py`: event filtering and time parsing
- `database.py`: local duplicate-prevention store
- `config.py`: environment loading + validation
- `retry.py`: exponential backoff helper

## Setup

1. Install dependencies:

```bash
cd stream_scheduler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure env:

```bash
cp .env.example .env
# Edit .env values
```

3. Place your OAuth client file at `stream_scheduler/client_secret.json` (or set `YOUTUBE_CLIENT_SECRETS_FILE`).

4. Run once to authenticate and schedule events:

```bash
python3 scheduler.py
```

On first run, OAuth will open a browser for consent and store token at `data/youtube_token.json`.

## Re-Auth If YouTube Fails

If `logs/stream_scheduler.log` shows an error like `invalid_grant: Token has been expired or revoked.`, refresh the YouTube OAuth token manually:

```bash
.venv/bin/python reAuth.py
```

The script will print a Google authorization URL. Open it, approve access, then paste the full redirected `http://localhost/?code=...` URL back into the prompt. A successful run ends with:

```text
YouTube auth OK
```

After that, rerun the scheduler once to verify recovery:

```bash
.venv/bin/python scheduler.py
```

## Cron (Every 4 Hours)

```cron
0 */4 * * * cd /path/to/repo/stream_scheduler && /path/to/repo/stream_scheduler/.venv/bin/python scheduler.py >> logs/cron.log 2>&1
```

## Notes

- Duplicate prevention key is Google Calendar event ID.
- API retries are automatic (`MAX_RETRIES`, exponential backoff).
- All-day events are ignored.
- If template files are missing/empty, `.env` values are used as fallback.
- If a stored YouTube refresh token is revoked, the client now falls back to the manual OAuth flow instead of failing permanently.
