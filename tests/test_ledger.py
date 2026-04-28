"""Tests for agent/ledger.py — idempotency tracking."""

import json
from pathlib import Path

import pytest

from agent.ledger import Ledger


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    client_name = "testclient"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return Ledger(client_name)


def test_new_ledger_empty(ledger):
    assert not ledger.is_pushed("vid001")
    assert ledger.all_pushed() == set()


def test_mark_pushed_persists(tmp_path, monkeypatch):
    client_name = "testclient"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    ledger1 = Ledger(client_name)
    ledger1.mark_pushed("vid001")
    ledger1.mark_pushed("vid002")

    # Create a new Ledger instance — should reload from disk
    ledger2 = Ledger(client_name)
    assert ledger2.is_pushed("vid001")
    assert ledger2.is_pushed("vid002")


def test_is_pushed_false_for_unknown(ledger):
    ledger.mark_pushed("vid001")
    assert not ledger.is_pushed("vid999")


def test_all_pushed_returns_set(ledger):
    ledger.mark_pushed("vid001")
    ledger.mark_pushed("vid002")
    result = ledger.all_pushed()
    assert isinstance(result, set)
    assert result == {"vid001", "vid002"}


def test_mark_pushed_idempotent(ledger):
    ledger.mark_pushed("vid001")
    ledger.mark_pushed("vid001")
    assert len(ledger.all_pushed()) == 1


def test_pushed_json_is_sorted_list(tmp_path, monkeypatch):
    client_name = "testclient"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    ledger = Ledger(client_name)
    ledger.mark_pushed("vid_c")
    ledger.mark_pushed("vid_a")
    ledger.mark_pushed("vid_b")

    pushed_path = output_dir / "pushed.json"
    data = json.loads(pushed_path.read_text())
    assert data == sorted(data)


def test_resume_skips_pushed_videos(tmp_path, monkeypatch):
    """Simulate a partial run by pre-populating pushed.json, then verify new ledger skips them."""
    client_name = "testclient"
    output_dir = tmp_path / "clients" / client_name / "output"
    output_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    pushed_path = output_dir / "pushed.json"
    pushed_path.write_text(json.dumps(["vid001", "vid002"]))

    ledger = Ledger(client_name)
    all_videos = ["vid001", "vid002", "vid003", "vid004"]
    to_push = [v for v in all_videos if not ledger.is_pushed(v)]

    assert to_push == ["vid003", "vid004"]
