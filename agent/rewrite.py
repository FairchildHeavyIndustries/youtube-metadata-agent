"""Rewrite video metadata using Claude — Batch API (default) or real-time asyncio."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

_CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
_ASYNC_CLIENT = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

PRIMARY_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ESCALATION_MODEL = os.environ.get("ANTHROPIC_ESCALATION_MODEL", "claude-opus-4-7")
VALIDATION_MODEL = os.environ.get("ANTHROPIC_VALIDATION_MODEL", "claude-haiku-4-5-20251001")
USE_BATCH = os.environ.get("ANTHROPIC_USE_BATCH", "true").lower() == "true"

REQUIRED_KEYS = {
    "title", "description", "tags", "default_language",
    "localizations", "playlist_category", "rewrite_notes",
}


def _load_brief(client_name: str) -> str:
    brief_path = Path(f"clients/{client_name}/brief.md")
    if not brief_path.exists():
        raise FileNotFoundError(f"Brief not found: {brief_path}")
    return brief_path.read_text(encoding="utf-8")


def _load_categories(client_name: str) -> list[str]:
    cat_path = Path(f"clients/{client_name}/categories.json")
    with open(cat_path) as f:
        data = json.load(f)
    cats = data.get("categories", data)
    if isinstance(cats, list):
        return [c["key"] for c in cats]
    return list(cats.keys())


def _video_prompt(video: dict, categories: list[str]) -> str:
    return (
        f"Rewrite the metadata for this YouTube video.\n\n"
        f"Current metadata:\n```json\n{json.dumps(video, ensure_ascii=False, indent=2)}\n```\n\n"
        f"Valid playlist_category values: {json.dumps(categories)}\n\n"
        f"Respond with ONLY valid JSON matching the required schema. No markdown fences."
    )


def _parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(text)


def _validate(parsed: dict, categories: list[str]) -> list[str]:
    errors = []
    missing = REQUIRED_KEYS - set(parsed.keys())
    if missing:
        errors.append(f"missing keys: {missing}")
    title = parsed.get("title", "")
    if len(title) > 100:
        errors.append(f"title too long: {len(title)} chars")
    desc = parsed.get("description", "")
    if len(desc.split()) < 200:
        errors.append(f"description too short: {len(desc.split())} words")
    tags = parsed.get("tags", [])
    if len(tags) < 15:
        errors.append(f"too few tags: {len(tags)}")
    category = parsed.get("playlist_category", "")
    if category not in categories:
        errors.append(f"unknown playlist_category: {category!r}")
    return errors


def _call_claude_sync(model: str, system: str, user: str, cached_system: bool = False) -> str:
    system_content = [
        {
            "type": "text",
            "text": system,
            **({"cache_control": {"type": "ephemeral"}} if cached_system else {}),
        }
    ]
    resp = _CLIENT.messages.create(
        model=model,
        max_tokens=6000,
        system=system_content,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _rewrite_one_sync(
    video: dict, brief: str, categories: list[str], errors_path: Path, escalations_path: Path
) -> dict | None:
    video_id = video.get("id", "unknown")
    prompt = _video_prompt(video, categories)

    for attempt in range(2):
        model = PRIMARY_MODEL if attempt == 0 else ESCALATION_MODEL
        try:
            text = _call_claude_sync(model, brief, prompt, cached_system=(attempt == 0))
            parsed = _parse_response(text)
            validation_errors = _validate(parsed, categories)
            if not validation_errors:
                parsed["_video_id"] = video_id
                return parsed
        except (json.JSONDecodeError, Exception):
            pass

    # Escalate to Opus
    try:
        text = _call_claude_sync(ESCALATION_MODEL, brief, prompt)
        parsed = _parse_response(text)
        validation_errors = _validate(parsed, categories)
        if not validation_errors:
            parsed["_video_id"] = video_id
            _append_json(escalations_path, {"video_id": video_id, "reason": "parse_failure"})
            return parsed
        raw_text = text
    except Exception as e:
        raw_text = str(e)

    _append_json(errors_path, {"video_id": video_id, "raw_response": raw_text})
    return None


async def _rewrite_one_async(
    video: dict, brief: str, categories: list[str], semaphore: asyncio.Semaphore,
    errors_path: Path, escalations_path: Path
) -> dict | None:
    video_id = video.get("id", "unknown")
    prompt = _video_prompt(video, categories)

    async with semaphore:
        for attempt in range(2):
            model = PRIMARY_MODEL if attempt == 0 else ESCALATION_MODEL
            try:
                system_content = [
                    {
                        "type": "text",
                        "text": brief,
                        **({"cache_control": {"type": "ephemeral"}} if attempt == 0 else {}),
                    }
                ]
                resp = await _ASYNC_CLIENT.messages.create(
                    model=model,
                    max_tokens=6000,
                    system=system_content,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = resp.content[0].text
                parsed = _parse_response(text)
                validation_errors = _validate(parsed, categories)
                if not validation_errors:
                    parsed["_video_id"] = video_id
                    return parsed
            except (json.JSONDecodeError, Exception):
                pass

        # Escalate to Opus
        try:
            resp = await _ASYNC_CLIENT.messages.create(
                model=ESCALATION_MODEL,
                max_tokens=6000,
                system=brief,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            parsed = _parse_response(text)
            if not _validate(parsed, categories):
                parsed["_video_id"] = video_id
                _append_json(escalations_path, {"video_id": video_id, "reason": "parse_failure"})
                return parsed
            raw_text = text
        except Exception as e:
            raw_text = str(e)

        _append_json(errors_path, {"video_id": video_id, "raw_response": raw_text})
        return None


def _append_json(path: Path, entry: dict) -> None:
    existing = []
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
    existing.append(entry)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)


def _rewrite_batch(
    videos: list[dict], brief: str, categories: list[str], output_dir: Path
) -> list[dict]:
    """Submit all videos to Batch API, poll until complete, return results."""
    errors_path = output_dir / "parse_errors.json"
    escalations_path = output_dir / "escalations.json"
    batch_errors_path = output_dir / "batch_errors.json"

    system_content = [
        {"type": "text", "text": brief, "cache_control": {"type": "ephemeral"}}
    ]

    requests = [
        {
            "custom_id": video.get("id", f"video_{i}"),
            "params": {
                "model": PRIMARY_MODEL,
                "max_tokens": 6000,
                "system": system_content,
                "messages": [{"role": "user", "content": _video_prompt(video, categories)}],
            },
        }
        for i, video in enumerate(videos)
    ]

    print(f"Submitting batch of {len(requests)} requests...")
    batch = _CLIENT.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"Batch ID: {batch_id}")

    # Poll every 5 minutes; timeout after 26 hours
    max_polls = 312
    for poll in range(max_polls):
        time.sleep(300)
        batch = _CLIENT.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        counts = batch.request_counts
        print(
            f"Poll {poll + 1}: {status} — "
            f"succeeded={counts.succeeded} errored={counts.errored} "
            f"processing={counts.processing}"
        )
        if status == "ended":
            break
    else:
        _append_json(batch_errors_path, {"batch_id": batch_id, "reason": "timeout"})
        raise RuntimeError(f"Batch {batch_id} did not complete within 26 hours.")

    results = []
    failed_video_ids = []

    for result in _CLIENT.messages.batches.results(batch_id):
        vid_id = result.custom_id
        if result.result.type == "succeeded":
            text = result.result.message.content[0].text
            try:
                parsed = _parse_response(text)
                errors = _validate(parsed, categories)
                if not errors:
                    parsed["_video_id"] = vid_id
                    results.append(parsed)
                    continue
            except (json.JSONDecodeError, Exception):
                pass
            failed_video_ids.append(vid_id)
        else:
            failed_video_ids.append(vid_id)

    # Re-submit failures as real-time Opus calls
    if failed_video_ids:
        print(f"Re-submitting {len(failed_video_ids)} failed videos via Opus...")
        video_map = {v.get("id"): v for v in videos}
        for vid_id in failed_video_ids:
            video = video_map.get(vid_id, {})
            result = _rewrite_one_sync(video, brief, categories, errors_path, escalations_path)
            if result:
                _append_json(escalations_path, {"video_id": vid_id, "reason": "batch_parse_failure"})
                results.append(result)

    return results


def _rewrite_realtime(
    videos: list[dict], brief: str, categories: list[str], output_dir: Path
) -> list[dict]:
    """Process videos with asyncio.gather in groups of 10."""
    errors_path = output_dir / "parse_errors.json"
    escalations_path = output_dir / "escalations.json"

    async def run_all():
        semaphore = asyncio.Semaphore(10)
        tasks = [
            _rewrite_one_async(v, brief, categories, semaphore, errors_path, escalations_path)
            for v in videos
        ]
        return await asyncio.gather(*tasks)

    raw = asyncio.run(run_all())
    return [r for r in raw if r is not None]


def rewrite(client_name: str) -> Path:
    output_dir = Path(f"clients/{client_name}/output")
    source = output_dir / "current_metadata.json"

    if not source.exists():
        raise FileNotFoundError(f"{source} not found. Run fetch.py first.")

    with open(source) as f:
        data = json.load(f)

    videos = data.get("videos", [])
    brief = _load_brief(client_name)
    categories = _load_categories(client_name)

    print(f"Rewriting metadata for {len(videos)} videos (batch={USE_BATCH})...")

    if USE_BATCH:
        results = _rewrite_batch(videos, brief, categories, output_dir)
    else:
        results = _rewrite_realtime(videos, brief, categories, output_dir)

    # Build proposed metadata keyed by video ID
    proposed = {r["_video_id"]: r for r in results}

    out_path = output_dir / "proposed_metadata.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(proposed, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(proposed)} rewrites to {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    rewrite(args.client)
