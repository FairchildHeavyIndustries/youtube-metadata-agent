"""Tests for agent/rewrite.py — mocks Anthropic API."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.rewrite import (
    REQUIRED_KEYS,
    _parse_response,
    _validate,
    _video_prompt,
)

SAMPLE_CATEGORIES = [
    "barredoras", "aspiradoras", "cortadoras", "tractores",
    "podadoras", "limpiadoras_presion", "repuestos", "accesorios",
    "servicio_tecnico", "arrendamiento", "proyectos", "otros",
]

VALID_RESPONSE = {
    "title": "Barredoras Industriales Tennant T7 | Sweep & Vac Unlimited Puerto Rico",
    "description": " ".join(["palabra"] * 210),
    "tags": [f"tag{i}" for i in range(15)],
    "default_language": "es",
    "localizations": {
        "es": {
            "title": "Barredoras Industriales Tennant T7 | Sweep & Vac Unlimited Puerto Rico",
            "description": " ".join(["palabra"] * 210),
        },
        "en": {
            "title": "Tennant T7 Industrial Sweeper | Sweep & Vac Unlimited Puerto Rico",
            "description": " ".join(["word"] * 210),
        },
    },
    "playlist_category": "barredoras",
    "rewrite_notes": "Rewrote title to include brand and location.",
}


def test_parse_response_plain_json():
    text = json.dumps(VALID_RESPONSE)
    parsed = _parse_response(text)
    assert parsed["title"] == VALID_RESPONSE["title"]


def test_parse_response_strips_markdown_fences():
    text = "```json\n" + json.dumps(VALID_RESPONSE) + "\n```"
    parsed = _parse_response(text)
    assert parsed["title"] == VALID_RESPONSE["title"]


def test_parse_response_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        _parse_response("not json at all")


def test_validate_valid_response():
    errors = _validate(VALID_RESPONSE, SAMPLE_CATEGORIES)
    assert errors == []


def test_validate_title_too_long():
    bad = {**VALID_RESPONSE, "title": "A" * 101}
    errors = _validate(bad, SAMPLE_CATEGORIES)
    assert any("title too long" in e for e in errors)


def test_validate_localization_title_too_long():
    bad = {
        **VALID_RESPONSE,
        "localizations": {
            **VALID_RESPONSE["localizations"],
            "en": {"title": "A" * 101, "description": " ".join(["word"] * 210)},
        },
    }
    errors = _validate(bad, SAMPLE_CATEGORIES)
    assert any("localization 'en' title too long" in e for e in errors)


def test_validate_description_too_short():
    bad = {**VALID_RESPONSE, "description": "short description"}
    errors = _validate(bad, SAMPLE_CATEGORIES)
    assert any("description too short" in e for e in errors)


def test_validate_too_few_tags():
    bad = {**VALID_RESPONSE, "tags": ["only", "three", "tags"]}
    errors = _validate(bad, SAMPLE_CATEGORIES)
    assert any("few tags" in e for e in errors)


def test_validate_unknown_category():
    bad = {**VALID_RESPONSE, "playlist_category": "unknown_category"}
    errors = _validate(bad, SAMPLE_CATEGORIES)
    assert any("playlist_category" in e for e in errors)


def test_validate_missing_keys():
    bad = {"title": "Test"}
    errors = _validate(bad, SAMPLE_CATEGORIES)
    assert any("missing keys" in e for e in errors)


def test_required_keys_complete():
    assert REQUIRED_KEYS == {
        "title", "description", "tags", "default_language",
        "localizations", "playlist_category", "rewrite_notes",
    }


def test_video_prompt_includes_video_id():
    video = {"id": "test123", "snippet": {"title": "Test"}}
    prompt = _video_prompt(video, SAMPLE_CATEGORIES)
    assert "test123" in prompt
    assert "barredoras" in prompt


def test_rewrite_realtime_mocked(tmp_path, monkeypatch):
    """Validate that real-time mode calls Anthropic and writes proposed_metadata.json."""
    client_name = "testclient"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)
    brief_dir = tmp_path / "clients" / client_name
    brief_dir.mkdir(parents=True, exist_ok=True)
    (brief_dir / "brief.md").write_text("You are an SEO expert.")
    (brief_dir / "categories.json").write_text(
        json.dumps({cat: {"title": cat} for cat in SAMPLE_CATEGORIES})
    )

    current = {
        "channel_id": "UC_test",
        "client": client_name,
        "channel": {},
        "video_count": 1,
        "videos": [{
            "id": "vid001",
            "snippet": {"title": "Old title", "description": "short", "tags": []},
            "statistics": {},
            "status": {},
            "localizations": {},
        }],
    }
    (output_dir / "current_metadata.json").write_text(json.dumps(current))

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({**VALID_RESPONSE, "playlist_category": "barredoras"}))]

    async def mock_create(**kwargs):
        return mock_response

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_USE_BATCH", "false")

    with patch("agent.rewrite._ASYNC_CLIENT") as mock_async_client:
        mock_async_client.messages.create = mock_create
        from agent.rewrite import rewrite
        out_path = rewrite(client_name)

    assert out_path.exists()
    proposed = json.loads(out_path.read_text())
    assert "vid001" in proposed
    assert proposed["vid001"]["title"] == VALID_RESPONSE["title"]
    assert len(proposed["vid001"]["tags"]) >= 15
    assert len(proposed["vid001"]["description"].split()) >= 200
