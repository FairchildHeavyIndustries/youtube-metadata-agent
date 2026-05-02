"""Clean up legacy playlists when the auth user lacks delete rights.

Channel Editors can update playlist properties and remove playlist items, but
only the channel Owner can delete a playlist. This module hides legacy
playlists by emptying them and flipping privacy to Private, leaving the actual
delete to the Owner.

Workflow:
  1. Fetch all existing playlists on the channel.
  2. Determine which titles are 'new' (in categories.json) vs 'legacy'.
  3. For each legacy playlist:
       - remove every playlistItem (videos remain on the channel; only the
         playlist association is dropped)
       - set privacyStatus to 'private' so it disappears from public surfaces
  4. Write a summary to output/legacy_playlists_<date>.json so the report can
     list playlists the Owner still needs to delete manually.
"""

import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from agent.fetch import get_youtube_client
from agent.playlists import _load_categories

load_dotenv()


def _get_channel_playlists(youtube, channel_id: str) -> dict[str, str]:
    """Return {playlist_title: playlist_id} for a channel, scoped by channelId.

    Uses channelId rather than mine=True so it works when the auth user is a
    Channel Editor rather than the Owner — Editors cannot see playlists via
    mine=True because those playlists are owned by the Owner's Google account.
    """
    playlists: dict[str, str] = {}
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

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
RATE_LIMIT = float(os.environ.get("WRITE_RATE_LIMIT_SECONDS", "1"))


def _list_playlist_items(youtube, playlist_id: str) -> list[dict]:
    """Return all items in a playlist as [{'item_id', 'video_id', 'title'}]."""
    items = []
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page,
        ).execute()
        for it in resp.get("items", []):
            items.append({
                "item_id": it["id"],
                "video_id": it["snippet"]["resourceId"].get("videoId", ""),
                "title": it["snippet"].get("title", ""),
            })
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return items


def _remove_playlist_item(youtube, item_id: str) -> None:
    youtube.playlistItems().delete(id=item_id).execute()


def _set_playlist_private(youtube, playlist_id: str, title: str) -> None:
    youtube.playlists().update(
        part="snippet,status",
        body={
            "id": playlist_id,
            "snippet": {"title": title},
            "status": {"privacyStatus": "private"},
        },
    ).execute()


def cleanup(client_name: str) -> None:
    output_dir = Path(f"clients/{client_name}/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"legacy_playlists_{date.today().isoformat()}.json"
    errors_path = output_dir / "push_errors.json"

    categories = _load_categories(client_name)
    keep_titles: set[str] = set()
    cats_field = categories.get("categories", categories)
    if isinstance(cats_field, list):
        for cat in cats_field:
            title = cat.get("title_es") or cat.get("title") or cat.get("key")
            if title:
                keep_titles.add(title)
    elif isinstance(cats_field, dict):
        for key, cat in cats_field.items():
            if isinstance(cat, dict):
                title = cat.get("title_es") or cat.get("title") or cat.get("label") or key
            else:
                title = key
            keep_titles.add(title)
    fallback = categories.get("fallback_category")
    if isinstance(fallback, dict) and fallback.get("create_playlist") is True:
        fb_title = fallback.get("title_es") or fallback.get("title")
        if fb_title:
            keep_titles.add(fb_title)

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("YOUTUBE_CHANNEL_ID is not set in env.")

    youtube = get_youtube_client()
    existing = _get_channel_playlists(youtube, channel_id)

    legacy = {title: pl_id for title, pl_id in existing.items() if title not in keep_titles}

    if not legacy:
        print("No legacy playlists found. Nothing to clean up.")
        return

    print(f"Found {len(legacy)} legacy playlist(s):")
    for title in legacy:
        print(f"  - {title}")
    print(f"Keeping {len(existing) - len(legacy)} playlist(s) that match categories.json.")

    summary: list[dict] = []

    for title, pl_id in legacy.items():
        items = _list_playlist_items(youtube, pl_id)
        entry = {
            "playlist_id": pl_id,
            "title": title,
            "items_removed": 0,
            "items_total": len(items),
            "set_private": False,
            "manual_delete_required": True,
        }

        if DRY_RUN:
            print(f"\n[DRY RUN] {title} ({pl_id}): {len(items)} item(s)")
            for it in items:
                print(f"  would remove: {it['video_id']}  {it['title'][:60]}")
            print("  would set privacyStatus=private")
            summary.append(entry)
            continue

        print(f"\n{title} ({pl_id}): removing {len(items)} item(s)")
        for it in items:
            try:
                _remove_playlist_item(youtube, it["item_id"])
                entry["items_removed"] += 1
                print(f"  removed {it['video_id']}")
                time.sleep(RATE_LIMIT)
            except HttpError as e:
                print(f"  ERROR removing item {it['item_id']}: {e}")
                errors = []
                if errors_path.exists():
                    with open(errors_path) as f:
                        errors = json.load(f)
                errors.append({
                    "playlist": title,
                    "playlist_id": pl_id,
                    "item_id": it["item_id"],
                    "video_id": it["video_id"],
                    "error": str(e),
                })
                with open(errors_path, "w") as f:
                    json.dump(errors, f, indent=2)

        try:
            _set_playlist_private(youtube, pl_id, title)
            entry["set_private"] = True
            print(f"  set {title} to private")
            time.sleep(RATE_LIMIT)
        except HttpError as e:
            print(f"  ERROR setting {title} private: {e}")

        summary.append(entry)

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    if DRY_RUN:
        print(f"\n[DRY RUN] Summary would be written to {summary_path}")
        print("Set DRY_RUN=false to apply.")
    else:
        print(f"\nWrote summary to {summary_path}")
        print("These playlists are now empty + private. Owner must delete them manually in Studio.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--approve", action="store_true",
                        help="Required to confirm review before unlinking items.")
    args = parser.parse_args()

    if not args.approve:
        print("Pass --approve to confirm you want to empty and privatize legacy playlists.")
        raise SystemExit(1)

    cleanup(args.client)
