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
PLAYLIST_CREATE_DELAY = float(os.environ.get("PLAYLIST_CREATE_DELAY_SECONDS", "10"))


def _is_quota_exceeded(e: HttpError) -> bool:
    """Detect 403 quotaExceeded — once seen, all subsequent writes will fail."""
    if e.resp.status != 403:
        return False
    msg = str(e).lower()
    return "quotaexceeded" in msg or "quota" in msg


def _load_categories(client_name: str) -> dict:
    cat_path = Path(f"clients/{client_name}/categories.json")
    with open(cat_path) as f:
        return json.load(f)


def _get_existing_playlists(youtube, channel_id: str) -> dict[str, str]:
    """Return {playlist_title: playlist_id} for all playlists on the channel.

    Uses channelId rather than mine=True so it works for Channel Editors —
    Editors do not own the playlists, so mine=True returns an empty list.
    """
    playlists = {}
    next_page = None
    while True:
        resp = youtube.playlists().list(
            part="snippet",
            channelId=channel_id,
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


def _load_ledger(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_ledger(path: Path, ledger: dict[str, str]) -> None:
    with open(path, "w") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)


def playlists(client_name: str) -> None:
    output_dir = Path(f"clients/{client_name}/output")
    proposed_path = output_dir / "proposed_metadata.json"
    errors_path = output_dir / "push_errors.json"
    created_path = output_dir / "created_playlists.json"
    assigned_path = output_dir / "playlist_assignments.json"

    if not proposed_path.exists():
        raise FileNotFoundError(f"{proposed_path} not found. Run rewrite.py first.")

    with open(proposed_path) as f:
        proposed_data: dict = json.load(f)

    categories = _load_categories(client_name)

    cat_meta: dict[str, dict[str, str]] = {}
    cats_field = categories.get("categories", categories)
    if isinstance(cats_field, list):
        for cat in cats_field:
            key = cat.get("key")
            if not key:
                continue
            cat_meta[key] = {
                "title": cat.get("title_es") or cat.get("title") or key,
                "description": cat.get("description", ""),
            }
    elif isinstance(cats_field, dict):
        for key, cat in cats_field.items():
            if isinstance(cat, dict):
                title = cat.get("title_es") or cat.get("title") or cat.get("label") or key
                description = cat.get("description", "")
            else:
                title = key
                description = ""
            cat_meta[key] = {"title": title, "description": description}

    if DRY_RUN:
        print("[DRY RUN] Would create/ensure playlists:")
        for key, meta in cat_meta.items():
            print(f"  [{key}] {meta['title']}")
        category_counts: dict[str, int] = {}
        for vid_id, proposed in proposed_data.items():
            cat = proposed.get("playlist_category", "")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        print("\n[DRY RUN] Would assign videos:")
        for cat, count in sorted(category_counts.items()):
            print(f"  {cat}: {count} videos")
        print("\nSet DRY_RUN=false to push live.")
        return

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("YOUTUBE_CHANNEL_ID is not set in env.")

    youtube = get_youtube_client()

    # Resume-safe: load any prior runs' state from disk.
    # created: {category_key: playlist_id} — playlists we have already created
    # assigned: {video_id: category_key} — items we have already added to a playlist
    created: dict[str, str] = _load_ledger(created_path)
    assigned: dict[str, str] = _load_ledger(assigned_path)

    # Cross-check the channel for any title-matching playlists not in our ledger
    # (e.g. created in a prior run that crashed before writing the ledger).
    try:
        existing = _get_existing_playlists(youtube, channel_id)
    except HttpError as e:
        if _is_quota_exceeded(e):
            print(f"  ABORT: quota exhausted on initial playlists.list. Try again after midnight Pacific.")
            return
        raise

    for key, meta in cat_meta.items():
        if key in created:
            continue
        if meta["title"] in existing:
            created[key] = existing[meta["title"]]
            print(f"  Reconciled from channel: {meta['title']} ({created[key]})")
    _save_ledger(created_path, created)

    # Create missing playlists, abort cleanly on quota exhaustion
    quota_hit = False
    for key, meta in cat_meta.items():
        if key in created:
            print(f"  Playlist exists: {meta['title']}")
            continue

        try:
            pl_id = _create_playlist(youtube, meta["title"], meta["description"])
        except HttpError as e:
            if _is_quota_exceeded(e):
                print(f"  ABORT: quota exhausted while creating playlists. {len(created)} of {len(cat_meta)} done. Resume tomorrow.")
                quota_hit = True
                break
            if e.resp.status == 429:
                print(f"  ERROR 429 on '{meta['title']}' ({key}); skipping. Re-run later to retry.")
                continue
            print(f"  ERROR creating '{meta['title']}' ({key}): {e}")
            continue

        created[key] = pl_id
        _save_ledger(created_path, created)
        print(f"  Created playlist: {meta['title']} ({pl_id})")
        time.sleep(PLAYLIST_CREATE_DELAY)

    if quota_hit:
        return

    # Assign videos to playlists
    for vid_id, proposed in proposed_data.items():
        if vid_id in assigned:
            continue

        cat_key = proposed.get("playlist_category", "")
        pl_id = created.get(cat_key)
        if not pl_id:
            print(f"  WARNING: no playlist for category {cat_key!r}, skipping {vid_id}")
            continue

        try:
            _add_to_playlist(youtube, pl_id, vid_id)
            assigned[vid_id] = cat_key
            _save_ledger(assigned_path, assigned)
            print(f"  Added {vid_id} to {cat_key}")
            time.sleep(RATE_LIMIT)
        except HttpError as e:
            if _is_quota_exceeded(e):
                print(f"  ABORT: quota exhausted while assigning videos. {len(assigned)} of {len(proposed_data)} done. Resume tomorrow.")
                return
            if "duplicate" in str(e).lower() or e.resp.status == 409:
                print(f"  {vid_id} already in {cat_key}, marking assigned")
                assigned[vid_id] = cat_key
                _save_ledger(assigned_path, assigned)
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
