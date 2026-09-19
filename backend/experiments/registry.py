from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class RegistryError(ValueError):
    pass


class ExperimentRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root / "experiments"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, spec: dict[str, Any]) -> str:
        run_id = uuid4().hex
        payload = {
            "run_id": run_id,
            "status": "running",
            "created_at": datetime.now(UTC).isoformat(),
            "spec": spec,
        }
        self._write(run_id, payload)
        return run_id

    def complete(self, run_id: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        record = self.load(run_id)
        if record["status"] != "running":
            raise RegistryError("only running experiments can complete")
        record.update(
            {
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
                "artifacts": artifacts,
            }
        )
        self._write(run_id, record)
        return record

    def fail(self, run_id: str, reason: str) -> None:
        record = self.load(run_id)
        if record["status"] != "running":
            raise RegistryError("only running experiments can fail")
        record.update(
            {
                "status": "failed",
                "failure": reason,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._write(run_id, record)

    def load(self, run_id: str) -> dict[str, Any]:
        path = self.root / run_id / "manifest.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"experiment unavailable: {run_id}") from exc

    def list(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*/manifest.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
        return records

    def _write(self, run_id: str, payload: dict[str, Any]) -> None:
        target = self.root / run_id / "manifest.json"
        if (
            target.exists()
            and json.loads(target.read_text(encoding="utf-8")).get("status")
            == "completed"
        ):
            raise RegistryError("completed experiments are immutable")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(data, encoding="utf-8")
        temporary.replace(target)


def reproducibility_fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
