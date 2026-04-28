"""Display a side-by-side terminal diff of current vs proposed metadata."""

import argparse
import json
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

FIELDS = [
    ("title", "Title"),
    ("description", "Description"),
    ("tags", "Tags"),
    ("default_language", "Default Language"),
    ("localizations.es.title", "ES Title"),
    ("localizations.es.description", "ES Description"),
    ("localizations.en.title", "EN Title"),
    ("localizations.en.description", "EN Description"),
    ("playlist_category", "Playlist Category"),
]


def _get_nested(obj: dict, dotpath: str) -> str:
    parts = dotpath.split(".")
    val = obj
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part, "")
        else:
            return ""
    if isinstance(val, list):
        return ", ".join(val)
    return str(val) if val else ""


def _truncate(text: str, max_len: int = 300) -> str:
    return text[:max_len] + "…" if len(text) > max_len else text


def diff(client_name: str) -> Path:
    output_dir = Path(f"clients/{client_name}/output")

    current_path = output_dir / "current_metadata.json"
    proposed_path = output_dir / "proposed_metadata.json"

    if not current_path.exists():
        raise FileNotFoundError(f"{current_path} not found.")
    if not proposed_path.exists():
        raise FileNotFoundError(f"{proposed_path} not found. Run rewrite.py first.")

    with open(current_path) as f:
        current_data = json.load(f)
    with open(proposed_path) as f:
        proposed_data = json.load(f)

    current_videos = {v["id"]: v for v in current_data.get("videos", [])}

    md_lines = [f"# Metadata Diff — {client_name} — {date.today().isoformat()}\n"]

    for vid_id, proposed in proposed_data.items():
        current = current_videos.get(vid_id, {})
        current_snippet = current.get("snippet", {})
        current_locs = current.get("localizations", {})

        current_flat = {
            "title": current_snippet.get("title", ""),
            "description": current_snippet.get("description", ""),
            "tags": ", ".join(current_snippet.get("tags", [])),
            "default_language": current_snippet.get("defaultLanguage", ""),
            "localizations.es.title": current_locs.get("es", {}).get("title", ""),
            "localizations.es.description": current_locs.get("es", {}).get("description", ""),
            "localizations.en.title": current_locs.get("en", {}).get("title", ""),
            "localizations.en.description": current_locs.get("en", {}).get("description", ""),
            "playlist_category": "",
        }

        table = Table(
            title=f"[bold cyan]{vid_id}[/] — {current_snippet.get('title', 'Unknown')}",
            show_lines=True,
            expand=True,
        )
        table.add_column("Field", style="bold", width=20)
        table.add_column("Current", style="red", ratio=1)
        table.add_column("Proposed", style="green", ratio=1)

        md_section = [f"\n## {vid_id} — {current_snippet.get('title', 'Unknown')}\n"]
        md_section.append("| Field | Current | Proposed |\n|---|---|---|\n")

        for dotpath, label in FIELDS:
            curr_val = current_flat.get(dotpath, "")
            prop_val = _get_nested(proposed, dotpath)

            changed = curr_val != prop_val
            curr_display = _truncate(curr_val)
            prop_display = _truncate(prop_val)

            if changed:
                table.add_row(label, curr_display, Text(prop_display, style="bold green"))
            else:
                table.add_row(label, curr_display, "[dim](unchanged)[/dim]")

            md_section.append(
                f"| {label} | {curr_val[:200].replace('|', '/')} | {prop_val[:200].replace('|', '/')} |\n"
            )

        notes = proposed.get("rewrite_notes", "")
        if notes:
            table.add_row("Rewrite Notes", "", f"[italic]{_truncate(notes, 500)}[/italic]")
            md_section.append(f"\n**Notes:** {notes}\n")

        console.print(table)
        md_lines.extend(md_section)

    today = date.today().isoformat()
    md_path = output_dir / f"diff_{today}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.writelines(md_lines)

    console.print(f"\n[bold]Diff written to[/] {md_path}")
    return md_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    diff(args.client)
