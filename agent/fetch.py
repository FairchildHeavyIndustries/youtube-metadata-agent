"""Pull all video and channel metadata from the YouTube Data API v3."""

import argparse
import json
import os
from pathlib import Path
from googleapiclient.discovery import build
from dotenv import load_dotenv
from auth.token_store import get_credentials

load_dotenv()


def get_youtube_client():
    creds = get_credentials()
    return build("youtube", "v3", credentials=creds)


def fetch_all_video_ids(youtube, channel_id: str) -> list[str]:
    """Return all video IDs uploaded to the channel."""
    video_ids = []
    next_page_token = None

    # Get the uploads playlist ID first
    channel_resp = youtube.channels().list(
        part="contentDetails",
        id=channel_id,
    ).execute()

    if not channel_resp.get("items"):
        raise ValueError(f"Channel {channel_id} not found or not accessible")

    uploads_playlist_id = (
        channel_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    )

    while True:
        playlist_resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token,
        ).execute()

        for item in playlist_resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        next_page_token = playlist_resp.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids


def fetch_video_metadata(youtube, video_ids: list[str]) -> list[dict]:
    """Fetch full metadata for a list of video IDs in batches of 50."""
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = youtube.videos().list(
            part="snippet,localizations,statistics,status",
            id=",".join(batch),
        ).execute()
        videos.extend(resp.get("items", []))
    return videos


def fetch_channel_metadata(youtube, channel_id: str) -> dict:
    """Fetch channel-level metadata including branding settings."""
    resp = youtube.channels().list(
        part="snippet,brandingSettings,localizations",
        id=channel_id,
    ).execute()

    if not resp.get("items"):
        raise ValueError(f"Could not fetch metadata for channel {channel_id}")

    return resp["items"][0]


def fetch(client_name: str) -> None:
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        raise ValueError("YOUTUBE_CHANNEL_ID not set")

    output_dir = Path(f"clients/{client_name}/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    youtube = get_youtube_client()

    print(f"Fetching video IDs for channel {channel_id}...")
    video_ids = fetch_all_video_ids(youtube, channel_id)
    print(f"Found {len(video_ids)} videos")

    print("Fetching video metadata...")
    videos = fetch_video_metadata(youtube, video_ids)

    print("Fetching channel metadata...")
    channel = fetch_channel_metadata(youtube, channel_id)

    data = {
        "channel_id": channel_id,
        "client": client_name,
        "channel": channel,
        "videos": videos,
        "video_count": len(videos),
    }

    output_path = output_dir / "current_metadata.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(videos)} videos to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    fetch(args.client)
