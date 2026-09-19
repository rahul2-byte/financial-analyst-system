from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ShadowLedger:
    """Append-only hypothetical decisions; it has no broker or order API."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation_id: str, payload: dict[str, Any]) -> bool:
        seen = self.seen_ids()
        if observation_id in seen:
            return False
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"observation_id": observation_id, "hypothetical": True, **payload},
                    sort_keys=True,
                )
                + "\n"
            )
        return True

    def seen_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        result: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result.add(str(json.loads(line)["observation_id"]))
        return result
