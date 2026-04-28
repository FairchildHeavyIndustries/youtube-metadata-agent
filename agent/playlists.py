"""Create playlists and assign videos to categories."""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from agent.fetch import get_youtube_client

load_dotenv()

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
RATE_LIMIT = float(os.environ.get("WRITE_RATE_LIMIT_SECONDS", "1"))


def _load_categories(client_name: str) -> dict:
    cat_path = Path(f"clients/{client_name}/categories.json")
    with open(cat_path) as f:
        return json.load(f)


def _get_existing_playlists(youtube) -> dict[str, str]:
    """Return {playlist_title: playlist_id} for all channel playlists."""
    playlists = {}
    next_page = None
    while True:
        resp = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50,
            pageToken=next_page,
        ).execute()
        for item in resp.get("items", []):
            playlists[item["snippet"]["title"]] = item["id"]
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return playlists


def _create_playlist(youtube, title: str, description: str = "") -> str:
    resp = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description, "defaultLanguage": "es"},
            "status": {"privacyStatus": "public"},
        },
    ).execute()
    return resp["id"]


def _add_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()


def playlists(client_name: str) -> None:
    output_dir = Path(f"clients/{client_name}/output")
    proposed_path = output_dir / "proposed_metadata.json"
    errors_path = output_dir / "push_errors.json"

    if not proposed_path.exists():
        raise FileNotFoundError(f"{proposed_path} not found. Run rewrite.py first.")

    with open(proposed_path) as f:
        proposed_data: dict = json.load(f)

    categories = _load_categories(client_name)

    # Build category_key -> playlist_title mapping
    cat_titles = {}
    for key, cat in categories.items():
        cat_titles[key] = cat.get("title_es") or cat.get("title") or key

    if DRY_RUN:
        print("[DRY RUN] Would create/ensure playlists:")
        for key, title in cat_titles.items():
            print(f"  [{key}] {title}")
        category_counts: dict[str, int] = {}
        for vid_id, proposed in proposed_data.items():
            cat = proposed.get("playlist_category", "")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        print("\n[DRY RUN] Would assign videos:")
        for cat, count in sorted(category_counts.items()):
            print(f"  {cat}: {count} videos")
        print("\nSet DRY_RUN=false to push live.")
        return

    youtube = get_youtube_client()
    existing = _get_existing_playlists(youtube)

    # Create missing playlists
    playlist_ids: dict[str, str] = {}
    for key, title in cat_titles.items():
        if title in existing:
            playlist_ids[key] = existing[title]
            print(f"  Playlist exists: {title}")
        else:
            pl_id = _create_playlist(youtube, title)
            playlist_ids[key] = pl_id
            print(f"  Created playlist: {title} ({pl_id})")
            time.sleep(RATE_LIMIT)

    # Assign videos
    for vid_id, proposed in proposed_data.items():
        cat_key = proposed.get("playlist_category", "")
        pl_id = playlist_ids.get(cat_key)
        if not pl_id:
            print(f"  WARNING: no playlist for category {cat_key!r}, skipping {vid_id}")
            continue

        try:
            _add_to_playlist(youtube, pl_id, vid_id)
            print(f"  Added {vid_id} to {cat_key}")
            time.sleep(RATE_LIMIT)
        except HttpError as e:
            if "duplicate" in str(e).lower() or e.resp.status == 409:
                print(f"  {vid_id} already in {cat_key}, skipping")
            else:
                print(f"  ERROR adding {vid_id} to {cat_key}: {e}")
                errors = []
                if errors_path.exists():
                    with open(errors_path) as f:
                        errors = json.load(f)
                errors.append({"video_id": vid_id, "playlist": cat_key, "error": str(e)})
                with open(errors_path, "w") as f:
                    json.dump(errors, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--approve", action="store_true",
                        help="Required to confirm review before pushing.")
    args = parser.parse_args()

    if not args.approve:
        print("Pass --approve to confirm you have reviewed the proposed metadata before pushing.")
        raise SystemExit(1)

    playlists(args.client)
