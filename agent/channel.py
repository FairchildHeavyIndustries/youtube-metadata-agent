"""Update channel-level metadata from clients/{client}/channel.md."""

import argparse
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from agent.fetch import get_youtube_client

load_dotenv()

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


def _has_backup(client_name: str) -> bool:
    output_dir = Path(f"clients/{client_name}/output")
    return any(output_dir.glob("original_backup_*.json"))


def _load_channel_md(client_name: str) -> dict:
    channel_path = Path(f"clients/{client_name}/channel.md")
    if not channel_path.exists():
        raise FileNotFoundError(f"{channel_path} not found.")

    text = channel_path.read_text(encoding="utf-8")

    # Prefer a ```yaml fenced block, then --- front matter, then the whole file.
    fenced = re.search(r"```ya?ml\s*\n(.*?)\n```", text, re.DOTALL)
    if fenced:
        return yaml.safe_load(fenced.group(1))
    front_matter = re.search(r"(?:^|\n)---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if front_matter:
        return yaml.safe_load(front_matter.group(1))
    return yaml.safe_load(text)


def _check_placeholders(data: dict) -> list[str]:
    """Detect any [REPLACE_WITH_*] strings in the config."""
    text = str(data)
    return re.findall(r"\[REPLACE_WITH_[^\]]+\]", text)


def channel(client_name: str) -> None:
    if not _has_backup(client_name):
        raise RuntimeError(
            f"No original_backup_*.json found for client '{client_name}'. "
            "Run backup.py before pushing channel metadata."
        )

    config = _load_channel_md(client_name)

    placeholders = _check_placeholders(config)
    if placeholders:
        raise ValueError(
            f"Unresolved placeholders in channel.md: {placeholders}. "
            "Fill these in before pushing."
        )

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("YOUTUBE_CHANNEL_ID env var is required for channels.update.")

    branding = config.get("branding_settings", {}).get("channel", {})
    description = branding.get("description", "")
    keywords = branding.get("keywords", "")
    default_language = branding.get("default_language", "es")

    # channels.update is PUT-like: omitting an existing field deletes or rejects it.
    # Read current brandingSettings and merge our changes onto it.
    youtube = get_youtube_client()
    resp = youtube.channels().list(part="brandingSettings", id=channel_id).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError(f"Channel {channel_id} not found.")
    current_branding = items[0].get("brandingSettings", {})
    current_channel = current_branding.get("channel", {})

    merged_channel = {
        **current_channel,
        "description": description,
        "keywords": keywords,
        "defaultLanguage": default_language,
    }

    body = {
        "id": channel_id,
        "brandingSettings": {"channel": merged_channel},
    }

    if DRY_RUN:
        print("[DRY RUN] Would update channel with:")
        print(f"  defaultLanguage: {default_language}")
        print(f"  keywords: {keywords[:100]}...")
        print(f"  description: {description[:100]}...")
        print(f"  preserved fields: {sorted(set(current_channel) - {'description', 'keywords', 'defaultLanguage'})}")
        print("\nSet DRY_RUN=false to push live.")
        return

    try:
        youtube.channels().update(part="brandingSettings", body=body).execute()
        print("Channel metadata updated successfully.")
    except HttpError as e:
        raise RuntimeError(f"YouTube API error updating channel: {e}") from e


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--approve", action="store_true",
                        help="Required to confirm review before pushing.")
    args = parser.parse_args()

    if not args.approve:
        print("Pass --approve to confirm you have reviewed channel.md before pushing.")
        raise SystemExit(1)

    channel(args.client)
