"""Push approved video metadata rewrites to YouTube."""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from agent.fetch import get_youtube_client
from agent.ledger import Ledger

load_dotenv()

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
RATE_LIMIT = float(os.environ.get("WRITE_RATE_LIMIT_SECONDS", "1"))
MAX_BACKOFF_RETRIES = 3


def _has_backup(client_name: str) -> bool:
    output_dir = Path(f"clients/{client_name}/output")
    return any(output_dir.glob("original_backup_*.json"))


def _push_video(youtube, video_id: str, proposed: dict) -> None:
    """Build and execute a videos.update call."""
    localizations = proposed.get("localizations", {})

    body = {
        "id": video_id,
        "snippet": {
            "title": proposed["title"],
            "description": proposed["description"],
            "tags": proposed.get("tags", []),
            "defaultLanguage": proposed.get("default_language", "es"),
            "defaultAudioLanguage": proposed.get("default_language", "es"),
            "categoryId": "28",  # Science & Technology — YouTube requires a categoryId on update
        },
        "localizations": {
            lang: {"title": loc["title"], "description": loc["description"]}
            for lang, loc in localizations.items()
        },
    }

    for attempt in range(MAX_BACKOFF_RETRIES):
        try:
            youtube.videos().update(part="snippet,localizations", body=body).execute()
            return
        except HttpError as e:
            if e.resp.status == 429:
                sleep_time = (2 ** attempt) * 5
                print(f"  Rate limited. Sleeping {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                raise
    raise RuntimeError(f"Failed after {MAX_BACKOFF_RETRIES} retries for {video_id}")


def push(client_name: str, resume: bool = False) -> None:
    if not _has_backup(client_name):
        raise RuntimeError(
            f"No original_backup_*.json found for client '{client_name}'. "
            "Run backup.py before pushing."
        )

    output_dir = Path(f"clients/{client_name}/output")
    proposed_path = output_dir / "proposed_metadata.json"
    errors_path = output_dir / "push_errors.json"

    if not proposed_path.exists():
        raise FileNotFoundError(f"{proposed_path} not found. Run rewrite.py first.")

    with open(proposed_path) as f:
        proposed_data: dict = json.load(f)

    ledger = Ledger(client_name)
    youtube = None if DRY_RUN else get_youtube_client()

    video_ids = sorted(proposed_data.keys())
    pushed_count = 0
    skipped_count = 0
    error_count = 0

    for video_id in video_ids:
        if ledger.is_pushed(video_id):
            skipped_count += 1
            continue

        proposed = proposed_data[video_id]

        if DRY_RUN:
            print(f"[DRY RUN] Would push {video_id}: {proposed.get('title', '')[:60]}")
            continue

        try:
            _push_video(youtube, video_id, proposed)
            ledger.mark_pushed(video_id)
            pushed_count += 1
            print(f"  Pushed {video_id}: {proposed.get('title', '')[:60]}")
            time.sleep(RATE_LIMIT)
        except Exception as e:
            error_count += 1
            print(f"  ERROR on {video_id}: {e}")
            errors = []
            if errors_path.exists():
                with open(errors_path) as f:
                    errors = json.load(f)
            errors.append({"video_id": video_id, "error": str(e)})
            with open(errors_path, "w") as f:
                json.dump(errors, f, indent=2)

    if DRY_RUN:
        print(f"\n[DRY RUN] Would push {len(video_ids) - skipped_count} videos. "
              f"Set DRY_RUN=false to push live.")
    else:
        print(f"\nPush complete: {pushed_count} pushed, {skipped_count} skipped, {error_count} errors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--approve", action="store_true",
                        help="Required flag to confirm you have reviewed the diff.")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if not args.approve:
        print("Pass --approve to confirm you have reviewed the diff before pushing.")
        raise SystemExit(1)

    push(args.client, resume=args.resume)
