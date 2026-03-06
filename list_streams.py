import json

from config import load_settings
from youtube_client import YouTubeSchedulerClient


def main() -> None:
    settings = load_settings()
    client = YouTubeSchedulerClient(
        client_secrets_file=settings.youtube_client_secrets_file,
        token_file=settings.youtube_token_file,
    )

    service = client.service
    all_items = []
    page_token = None

    while True:
        response = (
            service.liveStreams()
            .list(
                part="id,snippet,cdn,status",
                mine=True,
                maxResults=50,
                pageToken=page_token,
            )
            .execute()
        )
        all_items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if not all_items:
        print("No live streams found for this channel.")
        return

    print("YouTube live streams:")
    for item in all_items:
        stream_id = item.get("id", "")
        title = item.get("snippet", {}).get("title", "")
        status = item.get("status", {}).get("streamStatus", "")
        ingestion = item.get("cdn", {}).get("ingestionType", "")
        reusable = item.get("cdn", {}).get("isReusable", "")

        print(
            f"- id={stream_id} | title={title} | status={status} | "
            f"ingestionType={ingestion} | isReusable={reusable}"
        )

    print("\nRaw JSON (for troubleshooting):")
    print(json.dumps(all_items, indent=2))


if __name__ == "__main__":
    main()
