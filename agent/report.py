"""Generate a client-facing before/after report using Jinja2."""

import argparse
import json
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _latest_file(pattern: str, output_dir: Path) -> Path | None:
    files = sorted(output_dir.glob(pattern))
    return files[-1] if files else None


def report(client_name: str) -> Path:
    output_dir = Path(f"clients/{client_name}/output")

    current_path = output_dir / "current_metadata.json"
    proposed_path = output_dir / "proposed_metadata.json"
    audit_path = _latest_file("audit_*.json", output_dir)
    diff_path = _latest_file("diff_*.md", output_dir)
    legacy_playlists_path = _latest_file("legacy_playlists_*.json", output_dir)
    pushed_path = output_dir / "pushed.json"
    escalations_path = output_dir / "escalations.json"

    if not current_path.exists():
        raise FileNotFoundError(f"{current_path} not found.")
    if not proposed_path.exists():
        raise FileNotFoundError(f"{proposed_path} not found.")
    if not audit_path:
        raise FileNotFoundError("No audit_*.json found. Run audit.py first.")

    with open(current_path) as f:
        current_data = json.load(f)
    with open(proposed_path) as f:
        proposed_data = json.load(f)
    with open(audit_path) as f:
        audit_data = json.load(f)

    pushed_ids: set[str] = set()
    if pushed_path.exists():
        with open(pushed_path) as f:
            pushed_ids = set(json.load(f))

    escalation_count = 0
    if escalations_path.exists():
        with open(escalations_path) as f:
            escalation_count = len(json.load(f))

    legacy_playlists: list[dict] = []
    if legacy_playlists_path:
        with open(legacy_playlists_path) as f:
            legacy_playlists = json.load(f)

    # Pick 5 representative sample videos for the report
    current_videos = {v["id"]: v for v in current_data.get("videos", [])}
    sample_ids = list(proposed_data.keys())[:5]
    samples = []
    for vid_id in sample_ids:
        curr = current_videos.get(vid_id, {})
        prop = proposed_data[vid_id]
        samples.append({
            "video_id": vid_id,
            "before_title": curr.get("snippet", {}).get("title", ""),
            "after_title": prop.get("title", ""),
            "before_description_words": len(
                curr.get("snippet", {}).get("description", "").split()
            ),
            "after_description_words": len(prop.get("description", "").split()),
            "before_tag_count": len(curr.get("snippet", {}).get("tags", [])),
            "after_tag_count": len(prop.get("tags", [])),
            "playlist_category": prop.get("playlist_category", ""),
            "rewrite_notes": prop.get("rewrite_notes", ""),
        })

    template_dir = Path("reports")
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    template = env.get_template("report_template.md")

    context = {
        "client_name": client_name,
        "report_date": date.today().isoformat(),
        "video_count": current_data.get("video_count", 0),
        "pushed_count": len(pushed_ids),
        "escalation_count": escalation_count,
        "audit": audit_data,
        "channel_findings": audit_data.get("channel_findings", {}),
        "samples": samples,
        "diff_path": str(diff_path) if diff_path else "N/A",
        "legacy_playlists": legacy_playlists,
    }

    rendered = template.render(**context)

    today = date.today().isoformat()
    out_path = output_dir / f"report_{today}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"Report written to {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    report(args.client)
