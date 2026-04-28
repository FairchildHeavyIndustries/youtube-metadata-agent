"""Analyze current metadata and write audit_<date>.json with findings."""

import argparse
import json
from datetime import date
from pathlib import Path


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def audit(client_name: str) -> Path:
    output_dir = Path(f"clients/{client_name}/output")
    source = output_dir / "current_metadata.json"

    if not source.exists():
        raise FileNotFoundError(f"{source} not found. Run fetch.py first.")

    with open(source) as f:
        data = json.load(f)

    videos = data.get("videos", [])
    channel = data.get("channel", {})

    findings = {
        "video_count": len(videos),
        "videos_english_only_title": 0,
        "videos_short_description": 0,
        "videos_few_tags": 0,
        "videos_no_location_tag": 0,
        "videos_no_playlist": 0,
        "channel_findings": {},
        "per_video": [],
    }

    location_keywords = [
        "puerto rico", "pr", "san juan", "caribe", "caribbean",
        "isla", "antillas",
    ]

    for video in videos:
        snippet = video.get("snippet", {})
        video_id = video.get("id", "")
        title = snippet.get("title", "")
        description = snippet.get("description", "")
        tags = snippet.get("tags", [])
        default_lang = snippet.get("defaultLanguage", "")
        localizations = video.get("localizations", {})

        issues = []

        # English-only title (no Spanish localization)
        has_es = "es" in localizations and localizations["es"].get("title")
        if not has_es and default_lang in ("en", "en-US", ""):
            findings["videos_english_only_title"] += 1
            issues.append("english_only_title")

        # Short description
        if _word_count(description) < 100:
            findings["videos_short_description"] += 1
            issues.append("short_description")

        # Few tags
        if len(tags) < 5:
            findings["videos_few_tags"] += 1
            issues.append("few_tags")

        # No location tag
        all_text = " ".join([title, description] + tags).lower()
        if not any(kw in all_text for kw in location_keywords):
            findings["videos_no_location_tag"] += 1
            issues.append("no_location_tag")

        # No playlist (playlistId not in snippet; need separate check)
        # playlist membership is not in videos.list response — mark as unknown
        findings["per_video"].append({
            "id": video_id,
            "title": title,
            "tag_count": len(tags),
            "description_words": _word_count(description),
            "has_es_localization": has_es,
            "default_language": default_lang,
            "issues": issues,
        })

    # Channel-level findings
    channel_snippet = channel.get("snippet", {})
    branding = channel.get("brandingSettings", {}).get("channel", {})
    channel_localizations = channel.get("localizations", {})

    channel_desc = branding.get("description", "")
    channel_keywords = branding.get("keywords", "")
    channel_default_lang = channel_snippet.get("defaultLanguage", "")
    channel_country = channel_snippet.get("country", "")

    findings["channel_findings"] = {
        "default_language": channel_default_lang,
        "country": channel_country,
        "has_keywords": bool(channel_keywords),
        "keyword_count": len([k for k in channel_keywords.split('"') if k.strip()]),
        "about_word_count": _word_count(channel_desc),
        "has_es_localization": "es" in channel_localizations,
        "issues": [],
    }

    cf = findings["channel_findings"]
    if channel_default_lang not in ("es", "es-419"):
        cf["issues"].append("default_language_not_es")
    if not channel_keywords:
        cf["issues"].append("no_keywords")
    if _word_count(channel_desc) < 50:
        cf["issues"].append("short_about_section")
    if not cf["has_es_localization"]:
        cf["issues"].append("no_es_localization")

    today = date.today().isoformat()
    out_path = output_dir / f"audit_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(findings, f, ensure_ascii=False, indent=2)

    print(f"Audit complete: {out_path}")
    print(f"  {findings['video_count']} videos analyzed")
    print(f"  {findings['videos_english_only_title']} with English-only title")
    print(f"  {findings['videos_short_description']} with short description (<100 words)")
    print(f"  {findings['videos_few_tags']} with few tags (<5)")
    print(f"  {findings['videos_no_location_tag']} missing location tags")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    audit(args.client)
