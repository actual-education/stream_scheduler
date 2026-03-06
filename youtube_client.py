from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]


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

    def _credentials(self) -> Credentials:
        creds = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)
            return creds

        if not self.client_secrets_file.exists():
            raise RuntimeError(
                f"Client secrets file not found at {self.client_secrets_file}. "
                "Create one in Google Cloud and set YOUTUBE_CLIENT_SECRETS_FILE."
            )

        flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets_file), SCOPES)
        creds = flow.run_local_server(port=0)
        self._save_credentials(creds)
        return creds

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

    def bind_broadcast_to_stream(self, *, broadcast_id: str, stream_id: str) -> None:
        self.service.liveBroadcasts().bind(
            part="id,contentDetails",
            id=broadcast_id,
            streamId=stream_id,
        ).execute()
