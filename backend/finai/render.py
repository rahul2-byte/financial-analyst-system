"""Small Rich renderables used by the interactive terminal."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from markdown_it.token import Token
from rich import box
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import Heading, Markdown, TableElement
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .plain import dedupe_sources, source_label
from .safety import sanitize_terminal_text
from .state import PresentationState
from .theme import COLORS

FINAI_RICH_THEME = Theme(
    {
        "finai.body": COLORS["paper"],
        "markdown.h1": f"bold {COLORS['paper']}",
        "markdown.h2": f"bold {COLORS['paper']}",
        "markdown.h3": f"bold {COLORS['paper']}",
        "markdown.h4": f"bold {COLORS['dim']}",
        "markdown.item": COLORS["paper"],
        "markdown.item.bullet": COLORS["dim"],
        "markdown.item.number": COLORS["dim"],
        "markdown.code": COLORS["ledger"],
        "markdown.code_block": f"{COLORS['paper']} on {COLORS['graphite']}",
        "markdown.block_quote": COLORS["dim"],
        "markdown.hr": COLORS["rule"],
        "markdown.table.border": COLORS["rule"],
        "markdown.table.header": f"bold {COLORS['paper']}",
        "markdown.link": f"underline {COLORS['ledger']}",
        "markdown.link_url": COLORS["dim"],
        "markdown.strong": f"bold {COLORS['paper']}",
    },
    inherit=False,
)

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_DONE_PHASES = {"complete", "failed", "cancelled"}
_PARTIAL_STATUSES = {
    "partial",
    "insufficient_data",
    "completed_with_limited_evidence",
}


class _LeftHeading(Heading):
    """Left-aligned, unboxed headings: hierarchy from weight only."""

    new_line = False  # no blank line between a heading and its content

    @classmethod
    def create(cls, markdown: Markdown, token: Token) -> Heading:
        # Consecutive headings still get a blank line between them.
        tokens = markdown.parsed
        for index, item in enumerate(tokens):
            if item is token:
                following = tokens[index + 3 : index + 4]
                is_heading = bool(following) and following[0].type == "heading_open"
                if is_heading:
                    return _SpacedHeading(token.tag)
                break
        return cls(token.tag)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        self.text.justify = "left"
        yield self.text


class _SpacedHeading(_LeftHeading):
    """Heading directly followed by another heading: keep a blank line."""

    new_line = True


class _FlatTable(TableElement):
    """Table without outer edge rows or side padding, aligned with the text."""

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        table = Table(
            box=box.SIMPLE_HEAD,
            pad_edge=False,
            show_edge=False,
            style="markdown.table.border",
            collapse_padding=True,
        )
        if self.header is not None and self.header.row is not None:
            for column in self.header.row.cells:
                heading = column.content.copy()
                heading.stylize("markdown.table.header")
                table.add_column(heading)
        if self.body is not None:
            for row in self.body.rows:
                table.add_row(*[cell.content for cell in row.cells])
        yield table


class FinMarkdown(Markdown):
    """Markdown with calm headings and tables (one blank line between blocks)."""

    elements = {
        **Markdown.elements,
        "heading_open": _LeftHeading,
        "table_open": _FlatTable,
    }


def render_welcome() -> Text:
    """Empty-state: brand, one line of purpose, a few example prompts."""
    output = Text()
    output.append("FIN-AI", style=f"bold {COLORS['ledger']}")
    output.append(" — financial research, grounded in evidence\n", style=COLORS["dim"])
    output.append(
        "\nAsk about a company, sector, filing, price action or the news. "
        "FIN-AI gathers provider data, computes the numbers in code, and cites "
        "every source.\n",
        style=COLORS["paper"],
    )
    output.append("\nTry\n", style=COLORS["dim"])
    for example in (
        "Analyse HDFC Bank for the last 1 year",
        "Summarize TCS's latest quarterly results",
        "Compare Reliance vs Infosys fundamentals",
        "Latest news affecting IT stocks",
    ):
        output.append("› ", style=COLORS["ledger"])
        output.append(f"{example}\n", style=COLORS["paper"])
    return output


def render_user_message(query: str) -> Text:
    output = Text("› ", style=COLORS["dim"])
    output.append(sanitize_terminal_text(query), style=COLORS["paper"])
    return output


def render_command(name: str, args: list[str]) -> Text:
    command = "/" + name
    if args:
        command += " " + " ".join(args)
    return Text("› " + sanitize_terminal_text(command), style=COLORS["dim"])


_VERBS = {
    "fetch": "Fetched",
    "get": "Fetched",
    "run": "Ran",
    "analyze": "Analyzed",
    "analyse": "Analyzed",
    "compute": "Computed",
    "search": "Searched",
    "resolve": "Resolved",
    "load": "Loaded",
    "read": "Read",
}
# Short noun used for failures and the collapsed summary ("news unavailable").
_NOUNS = {
    "fetch_fundamentals": "fundamentals",
    "get_technical_overview": "technical overview",
    "fetch_news": "news",
    "run_fundamental_scan": "fundamental scan",
    "fetch_price_history": "price history",
}
_KV = re.compile(r"(\w+)=([^,\s]+)")
_RAW_ID = re.compile(r"\b[a-z_]+:[a-z_]+\b")


def _tool_name(label: str) -> str:
    return label.split(":", 1)[-1].strip()


def _noun(label: str) -> str:
    name = _tool_name(label)
    if name in _NOUNS:
        return _NOUNS[name]
    words = name.replace("_", " ").split()
    if len(words) > 1 and words[0] in _VERBS:
        words = words[1:]
    return " ".join(words) or label


def _tool_label(label: str) -> str:
    """`data:fetch_stock_data` -> `Fetched stock data` (never a raw id)."""
    words = _tool_name(label).replace("_", " ").split()
    if not words:
        return label
    verb = _VERBS.get(words[0])
    text = " ".join([verb, *words[1:]] if verb else words)
    return text[:1].upper() + text[1:]


def _tool_detail(label: str, detail: str | None) -> str:
    """Short human detail; never raw key=value dumps or JSON."""
    detail = (detail or "").strip()
    if not detail or detail.startswith(("{", "[")):
        return ""
    if detail.startswith("key values:"):
        pairs = dict(_KV.findall(detail))
        if label.endswith("get_technical_overview") and "close" in pairs:
            return f"close ₹{pairs['close']}"
        return ""
    if "=" in detail:
        return ""
    return _short(sanitize_terminal_text(detail), 40)


def _failure_detail(label: str, detail: str | None) -> str:
    text = (detail or "").strip().lower()
    if not text or "no usable" in text or "unavailable" in text:
        return (
            "no usable articles"
            if _tool_name(label) == "fetch_news"
            else "no usable data"
        )
    return _short(_RAW_ID.sub("", sanitize_terminal_text(text)).strip(" :·"), 40)


def _short(text: str, limit: int = 72) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _failed_nouns(state: PresentationState) -> list[str]:
    nouns: list[str] = []
    for key, activity in state.activities.items():
        if key.startswith("tool:") and activity.status == "failed":
            noun = _noun(activity.label)
            if noun not in nouns:
                nouns.append(noun)
    return nouns


_QUOTE_SYMBOL = re.compile(r"/quote/([A-Z0-9&_-]+\.(?:NS|BO))", re.IGNORECASE)


def instrument_from_sources(sources: list[dict[str, str]]) -> str | None:
    """Best-effort resolved instrument (e.g. HDFCBANK.NS) from provider quote URLs."""
    for source in sources:
        match = _QUOTE_SYMBOL.search(source.get("url", ""))
        if match:
            return match.group(1).upper()
    return None


def has_tool_trail(state: PresentationState) -> bool:
    return any(key.startswith("tool:") for key in state.activities)


def render_activity(
    state: PresentationState,
    *,
    spinner: str | None = None,
    elapsed_s: float | None = None,
    expanded: bool = False,
) -> Text:
    """Live trail while running; one collapsed summary line once done."""
    done = state.phase.value in _DONE_PHASES
    steps = [
        (key, activity)
        for key, activity in state.activities.items()
        # Model/provider chatter is noise unless something went wrong.
        if key != "model" and (key != "provider" or activity.status != "completed")
    ]
    if any(key.startswith("tool:") for key, _ in steps):
        steps = [
            (k, a) for k, a in steps if k.startswith("tool:") or a.status != "completed"
        ]
    output = Text(no_wrap=True, overflow="ellipsis")
    if done:
        count = len([1 for key, _ in steps if key.startswith("tool:")])
        if not count:
            return output  # chat-only reply: no trail at all
        summary = f"Gathered evidence · {count} tool{'s' if count != 1 else ''}"
        failed = _failed_nouns(state)
        if failed:
            summary += " · " + ", ".join(f"{noun} unavailable" for noun in failed)
        output.append("● ", style=COLORS["dim"])
        output.append(summary, style=COLORS["dim"])
        if not expanded:
            return output
    else:
        operation = state.current_operation or state.phase.value.replace("_", " ")
        output.append(f"{spinner or '●'} ", style=COLORS["ledger"])
        output.append(
            _short(_tool_label(operation).capitalize(), 60), style=COLORS["paper"]
        )
        if elapsed_s is not None:
            output.append(f" · {elapsed_s:.0f}s", style=COLORS["dim"])
    for key, activity in steps:
        is_tool = key.startswith("tool:")
        failed_step = activity.status == "failed"
        output.append("\n  ⎿ ", style=COLORS["dim"])
        if failed_step:
            output.append("✗ ", style=COLORS["loss"])
            label = _noun(activity.label).capitalize() if is_tool else activity.label
            output.append(_short(label, 48), style=COLORS["dim"])
            detail = (
                _failure_detail(activity.label, activity.detail)
                if is_tool
                else _short(
                    _RAW_ID.sub("", sanitize_terminal_text(activity.detail or "")), 40
                )
            )
        else:
            label = _tool_label(activity.label) if is_tool else activity.label
            output.append(_short(label, 48), style=COLORS["dim"])
            if activity.status == "running" and not done:
                output.append(" …", style=COLORS["dim"])
            detail = _tool_detail(activity.label if is_tool else "", activity.detail)
        if detail:
            output.append(f" · {detail}", style=COLORS["dim"])
    if state.error:
        output.append("\n  ⎿ ", style=COLORS["dim"])
        output.append(
            f"✗ {_short(sanitize_terminal_text(state.error), 100)}",
            style=COLORS["loss"],
        )
    return output


def render_header(
    state: PresentationState,
    *,
    instrument: str | None = None,
    width: int | None = None,
) -> Text:
    """One line: brand and rule; the resolved instrument on the right when known."""
    width = width or 120
    right = instrument or ""
    output = Text(no_wrap=True, overflow="ellipsis")
    output.append("FIN-AI", style=f"bold {COLORS['ledger']}")
    room = width - len("FIN-AI") - (len(right) + 1 if right else 0) - 2
    if room >= 3:
        output.append(" " + "─" * room, style=COLORS["rule"])
        if right:
            output.append(" " + right, style=COLORS["dim"])
    return output


def render_hints(*, mode: str, model: str, session_id: str | None, width: int) -> Text:
    """Dim status line under the composer."""
    left = f"{mode} · {model} · session {(session_id or 'local')[:8]}"
    right = "/ commands · F1 help"
    if len(left) + len(right) + 2 > width:
        left = f"{mode} · {(session_id or 'local')[:8]}"
    if len(left) + len(right) + 2 > width:
        right = "F1 help"
    output = Text(no_wrap=True, overflow="ellipsis", style=COLORS["dim"])
    output.append(left)
    output.append(" " * max(2, width - len(left) - len(right)))
    output.append(right)
    return output


def render_context(
    state: PresentationState, *, mode: str, session_id: str | None
) -> Text:
    """Render only context already present in the presentation state."""
    output = Text("Context\n", style=f"bold {COLORS['paper']}")
    if state.query:
        output.append("\nRequest\n", style=COLORS["dim"])
        output.append(f"{sanitize_terminal_text(state.query)}\n", style=COLORS["paper"])
    else:
        output.append("\nNo active research\n", style=COLORS["dim"])
    output.append("\nSession\n", style=COLORS["dim"])
    output.append(f"{(session_id or 'local')[:8]} · {mode}\n", style=COLORS["paper"])
    output.append("\nEvidence\n", style=COLORS["dim"])
    count = len(dedupe_sources(state.sources))
    output.append(
        f"{count} verified source{'s' if count != 1 else ''}\n",
        style=COLORS["gain"] if count else COLORS["dim"],
    )
    if state.activities and state.phase.value not in _DONE_PHASES:
        output.append("\nActive\n", style=COLORS["dim"])
        for activity in state.activities.values():
            marker = (
                "✓"
                if activity.status == "completed"
                else "✗"
                if activity.status == "failed"
                else "…"
            )
            output.append(f"{marker} {activity.label}\n", style=COLORS["dim"])
    return output


def render_sources(sources: list[dict[str, str]]) -> Text:
    """One dim, deduped, numbered block; the domain is dimmer than the title."""
    output = Text("Sources", style=COLORS["dim"])
    for index, source in enumerate(dedupe_sources(sources), 1):
        title = sanitize_terminal_text(source_label(source))
        host = ""
        url = source.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            host = parsed.netloc
        output.append(f"\n[{index}] {title}", style=COLORS["dim"])
        if host and host.removeprefix("www.") != title.removeprefix("www."):
            output.append(" · ", style=COLORS["faint"])
            output.append(host, style=Style(color=COLORS["faint"], link=url))
    return output


def render_response(state: PresentationState) -> Markdown:
    text = sanitize_terminal_text(state.response_text)
    return FinMarkdown(text.strip(), code_theme="ansi_dark", style="finai.body")


_CANDIDATE = re.compile(
    r"^\s*[-*•]\s*(?:(?P<sym>[A-Z0-9&.\-]+)\s*\((?P<ex1>[A-Z]+)\)\s*(?P<name1>.*)"
    r"|(?P<name2>.+?)\s*\((?P<sym2>[A-Z0-9&.\-]+)(?:,\s*(?P<ex2>[A-Z]+))?\))\s*$"
)
_ACRONYMS = {"HDFC", "ICICI", "SBI", "LIC", "TCS", "ITC", "NTPC", "ONGC", "IDBI", "UPL"}


def _title_name(name: str) -> str:
    """`HDFC BANK LTD` -> `HDFC Bank Ltd`; already-mixed-case names are kept."""
    if not name.isupper():
        return name
    words = []
    for word in name.split():
        if word in _ACRONYMS:
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def render_clarification(prompt: str) -> Text:
    """A clarification is a normal answer; candidates align as `SYMBOL  Name · EX`."""
    rows: list[tuple[str, str, str]] = []
    lines = sanitize_terminal_text(prompt).splitlines()
    parsed: list[tuple[str, str, str] | None] = []
    for line in lines:
        match = _CANDIDATE.match(line)
        if match:
            symbol = match["sym"] or match["sym2"]
            name = (match["name1"] or match["name2"] or "").strip()
            exchange = match["ex1"] or match["ex2"] or ""
            row = (symbol, _title_name(name), exchange)
            rows.append(row)
            parsed.append(row)
        else:
            parsed.append(None)
    width = max((len(r[0]) for r in rows), default=0)
    name_width = min(max((len(r[1]) for r in rows), default=0), 40)
    output = Text(style=COLORS["paper"])
    for index, (line, cand) in enumerate(zip(lines, parsed, strict=True)):
        if index:
            output.append("\n")
        if cand is None:
            output.append(line)
            continue
        symbol, name, exchange = cand
        output.append("  ")
        output.append(symbol.ljust(width), style=f"bold {COLORS['paper']}")
        name = _short(name, 40)
        output.append("  " + name.ljust(name_width))
        if exchange:
            output.append(" · " + exchange, style=COLORS["dim"])
    return output


def render_saved_report(report: dict[str, object]) -> Markdown:
    status = str(report.get("status", "unknown"))
    prefix = "**Saved report**\n\n"
    if status in {"partial", "completed_with_limited_evidence"}:
        prefix += "> Partial evidence: this saved report is limited to verified data returned by the available tools.\n\n"
    metadata = (
        f"**Status:** {sanitize_terminal_text(status)}  \n"
        f"**Request:** {sanitize_terminal_text(str(report.get('query', '')))}  \n"
        f"**Created:** {sanitize_terminal_text(str(report.get('created_at', '')))}  \n"
        f"**Artifact:** `{sanitize_terminal_text(str(report.get('artifact_path', '')))}`\n\n"
    )
    return FinMarkdown(
        prefix + metadata + sanitize_terminal_text(str(report.get("report_text", ""))),
        code_theme="ansi_dark",
        style="finai.body",
    )


def render_footer(state: PresentationState, *, elapsed_s: float | None = None) -> Text:
    """One dim line closing a run: outcome, why if partial, duration, sources."""
    phase = state.phase.value
    failed = phase == "failed"
    cancelled = phase == "cancelled"
    unavailable = [f"{noun} unavailable" for noun in _failed_nouns(state)]
    status = state.terminal_status or "complete"
    partial = (
        not failed
        and not cancelled
        and (status in _PARTIAL_STATUSES or bool(unavailable))
    )
    if failed:
        label, mark, color = "failed", "✗", COLORS["loss"]
    elif cancelled:
        label, mark, color = "cancelled", "✗", COLORS["loss"]
    elif partial:
        label, mark, color = "partial", "◐", COLORS["warn"]
    else:
        label = {"success": "complete", "completed": "complete"}.get(
            status, status.replace("_", " ")
        )
        mark, color = "✓", COLORS["gain"]
    parts = [label]
    if partial:
        parts.extend(unavailable)
    if elapsed_s is not None:
        parts.append(f"{elapsed_s:.1f}s")
    count = len(dedupe_sources(state.sources))
    if count:
        parts.append(f"{count} source{'s' if count != 1 else ''}")
    output = Text(f"{mark} ", style=color)
    output.append(label, style=color if partial or failed else COLORS["dim"])
    output.append("".join(f" · {part}" for part in parts[1:]), style=COLORS["dim"])
    return output


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
