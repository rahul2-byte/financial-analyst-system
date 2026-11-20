"""Export the bridge protocol and research-event JSON schemas.

Usage::

    PYTHONPATH=backend uv run python -m finai.bridge.schema --out protocol/schema

The generated files are committed. A test regenerates them into a temporary
directory and compares byte-for-byte, so this output must stay deterministic.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.events.models import ResearchEvent
from finai.bridge.protocol import PROTOCOL_MODELS, PROTOCOL_VERSION
from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema

PROTOCOL_TITLE = f"FIN-AI bridge protocol v{PROTOCOL_VERSION}"
RESEARCH_EVENT_FILE = "research_event.schema.json"
PROTOCOL_FILE = "protocol.schema.json"


def _write_schema(path: Path, schema: dict[str, Any]) -> None:
    text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def build_protocol_schema() -> dict[str, Any]:
    """Return one JSON schema whose ``$defs`` hold every protocol model."""
    _, schema = models_json_schema(
        [(model, "serialization") for model in PROTOCOL_MODELS],
        title=PROTOCOL_TITLE,
    )
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["description"] = (
        "JSON-RPC envelopes, method params/results, notifications and "
        "display payloads for the FIN-AI TypeScript bridge."
    )
    return schema


def export_schemas(out_dir: Path) -> list[Path]:
    """Write both schema files into ``out_dir`` and return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    event_path = out_dir / RESEARCH_EVENT_FILE
    event_schema = TypeAdapter(ResearchEvent).json_schema(mode="serialization")
    _write_schema(event_path, event_schema)

    protocol_path = out_dir / PROTOCOL_FILE
    _write_schema(protocol_path, build_protocol_schema())

    return [event_path, protocol_path]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the FIN-AI bridge JSON schemas."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("protocol/schema"),
        help="output directory (default: protocol/schema)",
    )
    args = parser.parse_args(argv)
    for path in export_schemas(args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_protocol_schema", "export_schemas", "main"]
