"""Tests for agent/push.py — always runs in dry-run mode."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


PROPOSED_VIDEO = {
    "title": "Barredoras Tennant T7 | Sweep & Vac Unlimited Puerto Rico",
    "description": " ".join(["palabra"] * 210),
    "tags": [f"tag{i}" for i in range(15)],
    "default_language": "es",
    "localizations": {
        "es": {"title": "Barredoras Tennant", "description": "desc es"},
        "en": {"title": "Tennant Sweepers", "description": "desc en"},
    },
    "playlist_category": "barredoras",
    "rewrite_notes": "test",
    "_video_id": "vid001",
}


@pytest.fixture
def push_env(tmp_path, monkeypatch):
    """Set up a minimal client directory for push tests."""
    client_name = "testclient"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)

    # Create a backup so the safety check passes
    (output_dir / "original_backup_2026-04-28.json").write_text("{}")

    # Write proposed metadata
    proposed = {"vid001": PROPOSED_VIDEO}
    (output_dir / "proposed_metadata.json").write_text(json.dumps(proposed))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DRY_RUN", "true")
    return client_name, output_dir


def test_dry_run_does_not_call_youtube(push_env, monkeypatch, capsys):
    client_name, _ = push_env

    with patch("agent.push.get_youtube_client") as mock_yt:
        from agent.push import push
        push(client_name)

    mock_yt.assert_not_called()
    out = capsys.readouterr().out
    assert "DRY RUN" in out


def test_dry_run_prints_video_title(push_env, capsys):
    client_name, _ = push_env
    with patch("agent.push.get_youtube_client"):
        from agent.push import push
        push(client_name)
    out = capsys.readouterr().out
    assert "vid001" in out


def test_push_requires_backup(tmp_path, monkeypatch):
    """push() should refuse if no backup exists."""
    client_name = "nobkp"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "proposed_metadata.json").write_text(json.dumps({"vid1": PROPOSED_VIDEO}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DRY_RUN", "true")

    from agent.push import push
    with pytest.raises(RuntimeError, match="original_backup"):
        push(client_name)


def test_push_skips_already_pushed(push_env, monkeypatch, capsys):
    client_name, output_dir = push_env
    # Pre-populate ledger with vid001
    (output_dir / "pushed.json").write_text(json.dumps(["vid001"]))

    with patch("agent.push.get_youtube_client"):
        from agent.push import push
        push(client_name)

    out = capsys.readouterr().out
    # vid001 should be skipped — not appear in DRY RUN output
    assert "vid001" not in out or "skipped" in out.lower()


def test_push_video_body_structure(monkeypatch):
    """Validate that _push_video sends the correct payload structure."""
    from agent.push import _push_video

    mock_youtube = MagicMock()
    mock_youtube.videos().update().execute.return_value = {"id": "vid001"}

    _push_video(mock_youtube, "vid001", PROPOSED_VIDEO)

    call_kwargs = mock_youtube.videos().update.call_args
    body = call_kwargs.kwargs["body"]

    assert body["id"] == "vid001"
    assert body["snippet"]["title"] == PROPOSED_VIDEO["title"]
    assert body["snippet"]["defaultLanguage"] == "es"
    assert "es" in body["localizations"]
    assert "en" in body["localizations"]
    assert isinstance(body["snippet"]["tags"], list)


def test_push_errors_logged_on_failure(push_env, monkeypatch):
    client_name, output_dir = push_env
    monkeypatch.setenv("DRY_RUN", "false")

    mock_youtube = MagicMock()
    mock_youtube.videos().update().execute.side_effect = Exception("API error")

    with patch("agent.push.get_youtube_client", return_value=mock_youtube):
        from agent.push import push
        push(client_name)

    errors_path = output_dir / "push_errors.json"
    assert errors_path.exists()
    errors = json.loads(errors_path.read_text())
    assert any(e["video_id"] == "vid001" for e in errors)
