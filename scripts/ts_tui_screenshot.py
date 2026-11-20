#!/usr/bin/env python3
"""Render an ANSI terminal capture from the TypeScript UI to a PNG.

Pipeline: ANSI -> Rich text -> SVG -> rsvg-convert PNG. Used by
frontend/scripts/snapshot.tsx for the images in docs/design/screenshots.

Usage: ts_tui_screenshot.py IN.ans OUT.png [--cols N] [--title TITLE]
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.text import Text

FONT_FAMILY = "Adwaita Mono"


def ansi_to_svg(ansi: str, cols: int, title: str) -> str:
    """Render ANSI escape output to an SVG string at the given column width."""
    console = Console(
        record=True,
        width=cols,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )
    console.print(Text.from_ansi(ansi), overflow="ignore", crop=False, no_wrap=True)
    svg = console.export_svg(title=title)
    # rsvg drops leading whitespace in a <text> element, so spaces at the start of a coloured
    # run vanished ("Upstox· api" for "Upstox · api"). xml:space="preserve" keeps them.
    svg = svg.replace("<text ", '<text xml:space="preserve" ')
    return svg.replace("Fira Code", FONT_FAMILY)


def svg_to_png(svg: str, png_path: Path) -> None:
    """Convert an SVG string to PNG with rsvg-convert."""
    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        raise SystemExit("rsvg-convert is required (install librsvg)")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        svg_path = Path(tmp) / "frame.svg"
        svg_path.write_text(svg, encoding="utf-8")
        subprocess.run(
            [rsvg, "--format=png", "-o", str(png_path), str(svg_path)],
            check=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="ANSI capture from the snapshot harness")
    parser.add_argument("output", type=Path, help="PNG path to write")
    parser.add_argument("--cols", type=int, default=100, help="Terminal width in columns")
    parser.add_argument("--title", default="FIN-AI", help="Window title in the frame")
    args = parser.parse_args(argv)
    ansi = args.input.read_text(encoding="utf-8")
    svg = ansi_to_svg(ansi, args.cols, args.title)
    svg_to_png(svg, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
