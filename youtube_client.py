import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]


class AuthRequiredError(RuntimeError):
    """Raised when YouTube OAuth needs manual re-authentication."""

    retryable = False


class YouTubeSchedulerClient:
    def __init__(
        self,
        *,
        client_secrets_file: Path,
        token_file: Path,
    ):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self._service = None

    def _run_manual_oauth_flow(self) -> Credentials:
        if not self.client_secrets_file.exists():
            raise RuntimeError(
                f"Client secrets file not found at {self.client_secrets_file}. "
                "Create one in Google Cloud and set YOUTUBE_CLIENT_SECRETS_FILE."
            )

        if not sys.stdin.isatty():
            raise AuthRequiredError(
                "YouTube OAuth token is missing or expired and this run is non-interactive. "
                "Run `.venv/bin/python reAuth.py` in a terminal to refresh credentials, "
                "then rerun the scheduler."
            )

        # Always use a headless/manual OAuth flow to avoid localhost callback issues.
        manual_flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file),
            SCOPES,
            redirect_uri="http://localhost",
        )
        auth_url, _ = manual_flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        print("Open this URL in any browser and authorize the app:")
        print(auth_url)
        print(
            "After approval, copy the FULL redirected URL "
            "(it starts with http://localhost/?code=...) and paste it below."
        )
        try:
            redirected_url = input("Paste redirected URL here: ").strip()
        except EOFError as exc:
            raise AuthRequiredError(
                "YouTube OAuth re-authentication was started but no redirected URL was provided. "
                "Run `.venv/bin/python reAuth.py` in an interactive terminal and complete the prompt."
            ) from exc
        parsed = urlparse(redirected_url)
        code = parse_qs(parsed.query).get("code", [None])[0]
        if not code:
            raise RuntimeError(
                "Could not find an OAuth code in the pasted URL. "
                "Expected something like http://localhost/?code=...&state=..."
            )
        manual_flow.fetch_token(code=code)
        creds = manual_flow.credentials
        self._save_credentials(creds)
        return creds

    def _credentials(self) -> Credentials:
        creds = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(creds)
                return creds
            except RefreshError:
                pass

        return self._run_manual_oauth_flow()

    def _save_credentials(self, creds: Credentials) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(creds.to_json(), encoding="utf-8")

    @property
    def service(self):
        if self._service is None:
            self._service = build("youtube", "v3", credentials=self._credentials(), cache_discovery=False)
        return self._service

    def create_broadcast(
        self,
        *,
        title: str,
        description: str,
        scheduled_start_iso: str,
        scheduled_end_iso: str,
        privacy_status: str,
        category_id: str,
    ) -> str:
        request = self.service.liveBroadcasts().insert(
            part="snippet,status,contentDetails",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "scheduledStartTime": scheduled_start_iso,
                    "scheduledEndTime": scheduled_end_iso,
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
                "contentDetails": {
                    "enableAutoStart": False,
                    "enableAutoStop": False,
                    "enableDvr": True,
                    "recordFromStart": True,
                    "monitorStream": {
                        "enableMonitorStream": False,
                    },
                },
            },
        )
        response = request.execute()
        broadcast_id = response["id"]

        # live broadcasts are also videos; this updates category metadata.
        self.service.videos().update(
            part="snippet",
            body={
                "id": broadcast_id,
                "snippet": {
                    "title": title,
                    "description": description,
                    "categoryId": category_id,
                },
            },
        ).execute()

        return broadcast_id

    def enable_broadcast_monetization(
        self,
        *,
        broadcast_id: str,
        optimization_mode: str,
    ) -> None:
        self.service.liveBroadcasts().update(
            part="id,monetizationDetails",
            body={
                "id": broadcast_id,
                "monetizationDetails": {
                    "adsMonetizationStatus": "on",
                    "cuepointSchedule": {
                        "enabled": True,
                        "ytOptimizedCuepointConfig": optimization_mode,
                    },
                },
            },
        ).execute()

    def broadcast_exists(self, broadcast_id: str) -> bool:
        if not broadcast_id:
            return False

        response = (
            self.service.liveBroadcasts()
            .list(
                part="id",
                id=broadcast_id,
                maxResults=1,
            )
            .execute()
        )
        return bool(response.get("items"))

    def bind_broadcast_to_stream(self, *, broadcast_id: str, stream_id: str) -> None:
        self.service.liveBroadcasts().bind(
            part="id,contentDetails",
            id=broadcast_id,
            streamId=stream_id,
        ).execute()
