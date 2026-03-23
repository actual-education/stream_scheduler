from config import load_settings
from youtube_client import YouTubeSchedulerClient


def main() -> None:
    settings = load_settings()
    client = YouTubeSchedulerClient(
        client_secrets_file=settings.youtube_client_secrets_file,
        token_file=settings.youtube_token_file,
    )
    client.service
    print("YouTube auth OK")


if __name__ == "__main__":
    main()
