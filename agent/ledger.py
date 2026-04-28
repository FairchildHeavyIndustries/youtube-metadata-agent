"""Idempotency ledger — tracks which video IDs have been pushed."""

import json
from pathlib import Path


class Ledger:
    def __init__(self, client_name: str):
        self._path = Path(f"clients/{client_name}/output/pushed.json")
        self._pushed: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path) as f:
                self._pushed = set(json.load(f))

    def _save(self) -> None:
        with open(self._path, "w") as f:
            json.dump(sorted(self._pushed), f, indent=2)

    def is_pushed(self, video_id: str) -> bool:
        return video_id in self._pushed

    def mark_pushed(self, video_id: str) -> None:
        self._pushed.add(video_id)
        self._save()

    def all_pushed(self) -> set[str]:
        return set(self._pushed)
