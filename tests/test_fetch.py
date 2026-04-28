"""Tests for agent/fetch.py — mocks YouTube API responses."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.fetch import fetch_all_video_ids, fetch_channel_metadata, fetch_video_metadata


@pytest.fixture
def mock_youtube():
    return MagicMock()


def test_fetch_all_video_ids_single_page(mock_youtube):
    mock_youtube.channels().list().execute.return_value = {
        "items": [{
            "contentDetails": {
                "relatedPlaylists": {"uploads": "UU_test_playlist"}
            }
        }]
    }
    mock_youtube.playlistItems().list().execute.return_value = {
        "items": [
            {"contentDetails": {"videoId": "vid1"}},
            {"contentDetails": {"videoId": "vid2"}},
        ]
    }

    ids = fetch_all_video_ids(mock_youtube, "UC_test_channel")
    assert ids == ["vid1", "vid2"]


def test_fetch_all_video_ids_paginated(mock_youtube):
    mock_youtube.channels().list().execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_test"}}}]
    }
    call_count = 0

    def paginated_execute():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "items": [{"contentDetails": {"videoId": "vid1"}}],
                "nextPageToken": "page2",
            }
        return {"items": [{"contentDetails": {"videoId": "vid2"}}]}

    mock_youtube.playlistItems().list().execute.side_effect = paginated_execute

    ids = fetch_all_video_ids(mock_youtube, "UC_test")
    assert "vid1" in ids
    assert "vid2" in ids


def test_fetch_all_video_ids_channel_not_found(mock_youtube):
    mock_youtube.channels().list().execute.return_value = {"items": []}
    with pytest.raises(ValueError, match="not found"):
        fetch_all_video_ids(mock_youtube, "UC_nonexistent")


def test_fetch_video_metadata_batches(mock_youtube):
    mock_youtube.videos().list().execute.return_value = {
        "items": [{"id": f"vid{i}"} for i in range(3)]
    }

    video_ids = [f"vid{i}" for i in range(55)]
    videos = fetch_video_metadata(mock_youtube, video_ids)

    # Should have made 2 calls (50 + 5)
    assert mock_youtube.videos().list().execute.call_count == 2
    assert len(videos) == 6  # 3 per call * 2 calls


def test_fetch_video_metadata_output_schema(mock_youtube):
    mock_youtube.videos().list().execute.return_value = {
        "items": [{
            "id": "dQw4w9WgXcQ",
            "snippet": {"title": "Test", "description": "Desc", "tags": []},
            "statistics": {"viewCount": "100"},
            "status": {"privacyStatus": "public"},
            "localizations": {},
        }]
    }

    videos = fetch_video_metadata(mock_youtube, ["dQw4w9WgXcQ"])
    assert len(videos) == 1
    v = videos[0]
    assert "id" in v
    assert "snippet" in v


def test_fetch_channel_metadata(mock_youtube):
    mock_youtube.channels().list().execute.return_value = {
        "items": [{
            "id": "UC_test",
            "snippet": {"title": "Test Channel"},
            "brandingSettings": {"channel": {"keywords": "test"}},
            "localizations": {},
        }]
    }

    channel = fetch_channel_metadata(mock_youtube, "UC_test")
    assert channel["id"] == "UC_test"
    assert "brandingSettings" in channel


def test_fetch_channel_metadata_not_found(mock_youtube):
    mock_youtube.channels().list().execute.return_value = {"items": []}
    with pytest.raises(ValueError, match="Could not fetch"):
        fetch_channel_metadata(mock_youtube, "UC_bad")


def test_fetch_writes_output(tmp_path, mock_youtube, monkeypatch):
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "UC_test")

    mock_youtube.channels().list().execute.side_effect = [
        # First call: fetch_all_video_ids
        {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_test"}}}]},
        # Second call: fetch_channel_metadata
        {"items": [{"id": "UC_test", "snippet": {}, "brandingSettings": {}, "localizations": {}}]},
    ]
    mock_youtube.playlistItems().list().execute.return_value = {
        "items": [{"contentDetails": {"videoId": "vid1"}}]
    }
    mock_youtube.videos().list().execute.return_value = {
        "items": [{"id": "vid1", "snippet": {}, "statistics": {}, "status": {}, "localizations": {}}]
    }

    with patch("agent.fetch.get_youtube_client", return_value=mock_youtube):
        client_dir = tmp_path / "clients" / "testclient" / "output"
        client_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        from agent.fetch import fetch
        fetch("testclient")

        out = client_dir / "current_metadata.json"
        assert out.exists()
        data = json.loads(out.read_text())
        assert "videos" in data
        assert "channel" in data
        assert data["video_count"] == 1
