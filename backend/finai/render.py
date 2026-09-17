"""Small Rich renderables used by the interactive terminal."""

from __future__ import annotations

from urllib.parse import urlparse

from rich.markdown import Markdown
from rich.style import Style
from rich.text import Text
from rich.theme import Theme

from .safety import sanitize_terminal_text
from .state import PresentationState
from .theme import COLORS

FINAI_RICH_THEME = Theme(
    {
        "finai.body": COLORS["text"],
        "markdown.h1": f"bold {COLORS['text']}",
        "markdown.h2": f"bold {COLORS['text']}",
        "markdown.h3": COLORS["text"],
        "markdown.item": COLORS["text"],
        "markdown.item.bullet": COLORS["info"],
        "markdown.item.number": COLORS["info"],
        "markdown.code": COLORS["secondary"],
        "markdown.code_block": f"{COLORS['text']} on #181818",
        "markdown.block_quote": COLORS["muted"],
        "markdown.hr": "#343434",
        "markdown.table.border": "#343434",
        "markdown.table.header": f"bold {COLORS['info']}",
        "markdown.link": f"underline {COLORS['info']}",
        "markdown.link_url": COLORS["muted"],
    },
    inherit=False,
)


def render_user_message(query: str) -> Text:
    output = Text("You\n", style=f"bold {COLORS['info']}")
    output.append(sanitize_terminal_text(query), style="default")
    return output


def render_command(name: str, args: list[str]) -> Text:
    command = "/" + name
    if args:
        command += " " + " ".join(args)
    output = Text("Command\n", style=f"bold {COLORS['muted']}")
    output.append(sanitize_terminal_text(command), style="default")
    return output


def render_activity(state: PresentationState) -> Text:
    if not state.activities:
        heading = {
            "starting": "Request · processing",
            "generating": "Response · streaming",
            "complete": "Response · complete",
        }.get(state.phase.value, "Request · processing")
    elif state.phase.value == "generating":
        heading = "Response · streaming"
    elif state.phase.value == "starting":
        heading = "Request · processing"
    elif state.phase.value in {"complete", "failed", "cancelled"}:
        outcome = state.terminal_status or state.phase.value
        heading = f"Research · {outcome}"
    else:
        heading = "Research · processing"
    heading_color = (
        COLORS["process"]
        if heading.startswith(("Research", "Request"))
        else COLORS["info"]
    )
    output = Text(f"{heading}\n", style=f"bold {heading_color}")
    for activity in state.activities.values():
        marker = (
            "✓"
            if activity.status == "completed"
            else "✗"
            if activity.status == "failed"
            else "◉"
        )
        style = (
            COLORS["success"]
            if activity.status == "completed"
            else COLORS["error"]
            if activity.status == "failed"
            else COLORS["process"]
        )
        output.append(f"  {marker} {activity.label}", style=style)
        if activity.detail:
            output.append(f" · {sanitize_terminal_text(activity.detail)}", style="dim")
        output.append("\n")
    if state.error:
        output.append(
            f"  Error · {sanitize_terminal_text(state.error)}\n", style=COLORS["error"]
        )
    return output


def render_header(
    state: PresentationState, *, mode: str, session_id: str | None
) -> Text:
    """Render compact, persistent chrome without inventing research metadata."""
    status = state.phase.value.replace("_", " ")
    session = (session_id or "local")[:8]
    output = Text("FIN-AI", style=f"bold {COLORS['text']}")
    output.append(
        "  Financial intelligence, grounded in evidence.", style=COLORS["secondary"]
    )
    output.append(
        "\n  Research companies · Analyze filings · Trace sources",
        style=COLORS["muted"],
    )
    output.append(
        f"                                      ● Online · {status} · session {session} · v0.1.0",
        style=COLORS["muted"],
    )
    return output


def render_context(
    state: PresentationState, *, mode: str, session_id: str | None
) -> Text:
    """Render only context already present in the presentation state."""
    output = Text("RESEARCH CONTEXT\n", style=f"bold {COLORS['text']}")
    if state.query:
        output.append("Request\n", style=f"bold {COLORS['muted']}")
        output.append(
            f"{sanitize_terminal_text(state.query)}\n\n", style=COLORS["text"]
        )
    else:
        output.append("No active research\n\n", style=COLORS["muted"])
    output.append("Session\n", style=f"bold {COLORS['muted']}")
    output.append(f"{(session_id or 'local')[:8]} · {mode}\n\n", style=COLORS["text"])
    output.append("EVIDENCE & SOURCES\n", style=f"bold {COLORS['text']}")
    count = len(state.sources)
    output.append(
        f"{count} verified source{'s' if count != 1 else ''}\n",
        style=COLORS["success"] if count else COLORS["muted"],
    )
    if state.activities and state.phase.value not in {
        "complete",
        "failed",
        "cancelled",
    }:
        output.append("\nACTIVE TOOLS\n", style=f"bold {COLORS['text']}")
        for activity in state.activities.values():
            marker = (
                "✓"
                if activity.status == "completed"
                else "✗"
                if activity.status == "failed"
                else "◉"
            )
            output.append(f"{marker} {activity.label}", style=COLORS["secondary"])
            if activity.detail:
                output.append(
                    f" · {sanitize_terminal_text(activity.detail)}",
                    style=COLORS["muted"],
                )
            output.append("\n")
    return output


def render_sources(sources: list[dict[str, str]]) -> Text:
    output = Text("Sources\n", style="bold")
    for index, source in enumerate(sources, 1):
        title = sanitize_terminal_text(
            source.get("title") or source.get("source") or "Untitled source"
        )
        source_type = sanitize_terminal_text(source.get("source_type", "source"))
        url = source.get("url", "")
        marker = (
            "[file]"
            if source_type in {"filing", "transcript", "presentation"}
            or url.lower().endswith(".pdf")
            else "[web]"
        )
        output.append(f"\n[{index}] {marker} {title}")
        output.append(f"\n    {source_type}", style="dim")
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            output.append(f" · {parsed.netloc}", style=Style(link=url))
    return output


def render_response(state: PresentationState, *, streaming: bool = False) -> Markdown:
    text = sanitize_terminal_text(state.response_text)
    prefix = "**FIN-AI**\n\n"
    if streaming:
        prefix = "**FIN-AI** · streaming\n\n"
    elif state.terminal_status in {"partial", "insufficient_data"}:
        label = (
            "Partial evidence"
            if state.terminal_status == "partial"
            else "Insufficient evidence"
        )
        prefix = f"**FIN-AI** · {label}\n\n> This report is limited to verified data returned by the available tools.\n\n"
    return Markdown(prefix + text, code_theme="ansi_dark", style="finai.body")


def render_status(
    state: PresentationState,
    *,
    spinner: str | None = None,
    elapsed_s: float | None = None,
) -> Text:
    label = state.phase.value.replace("_", " ")
    if spinner and state.phase.value not in {"complete", "failed", "cancelled"}:
        label = f"{spinner} {label}"
    if state.current_operation and state.phase.value not in {
        "complete",
        "failed",
        "cancelled",
    }:
        label += f" · {state.current_operation}"
    if elapsed_s is not None and state.phase.value != "idle":
        label += f" · {elapsed_s:.1f}s"
    if state.phase.value == "complete" and state.sources:
        label += f" · {len(state.sources)} sources"
    if state.terminal_status in {"partial", "insufficient_data"}:
        label += " · evidence limited"
    return Text(f"FIN-AI · {label}", style="dim")


def render_debug(state: PresentationState, event_log: list[str]) -> str:
    """Render diagnostic state without coupling formatting to Textual."""
    return (
        "\nDebug\n"
        f"run_id       {state.run_id or 'not started'}\n"
        f"last event   {state.last_event_type or 'none'}\n"
        f"sequence     {state.latest_sequence}\n"
        f"phase        {state.phase.value}\n"
        f"text deltas  {state.response_delta_count}\n"
        f"operation    {state.current_operation or 'none'}\n"
        f"active tools {', '.join(state.active_tools) or 'none'}\n"
        f"error        {state.error or 'none'}\n\nRecent events\n"
        + "\n".join(event_log[-12:])
    )
