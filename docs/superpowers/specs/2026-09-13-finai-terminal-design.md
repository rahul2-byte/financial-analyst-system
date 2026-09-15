# FIN-AI Event-Driven Terminal Design

## Goal

Replace the primitive `input()`/`print()` REPL with a professional, responsive terminal client without coupling terminal presentation to financial analysis, providers, or LangGraph nodes.

## Decisions

- Textual owns the interactive terminal, input editing, layout, key bindings, and redraw lifecycle.
- A plain renderer remains available for redirected output, CI, `NO_COLOR`, and future one-shot commands.
- The CLI consumes an in-process typed async event stream. It does not call the local FastAPI service.
- FastAPI SSE remains a separate transport adapter for the web frontend.
- Pydantic discriminated models define application events; arbitrary dictionaries are not the presentation contract.
- Only explicitly public final-answer text may produce response deltas. Internal model streams remain private.
- Every run receives its identity before execution and uses it for events, artifacts, logging, and telemetry.
- Presentation state is derived through a deterministic reducer.

## Event contract

Every event carries `event_id`, `run_id`, `conversation_id`, `sequence`, and `occurred_at`. The initial event union contains run lifecycle, stage lifecycle, tool lifecycle, response deltas, source updates, approval or clarification requests, warnings, retries, usage, and terminal outcomes.

The first migration maps existing LangGraph lifecycle events into stable public stage labels. Provider- and tool-level instrumentation is added only where the runtime can report real attempts, durations, result counts, and failures.

## State model

The top-level phase is one of `idle`, `starting`, `planning`, `waiting_for_approval`, `waiting_for_clarification`, `researching`, `analysing`, `validating`, `generating`, `cancelling`, `complete`, `failed`, or `cancelled`. Concurrent tools are child activity records and never competing top-level booleans.

## Interactive layout

The terminal has a compact header, a scrollable conversation, one active activity group, a persistent multiline composer, and a restrained status line. Approval and clarification use keyboard-operated modal screens. Completed output is append-only; only active activity and streaming response widgets update.

## Rendering and safety

- Stream deltas are coalesced before UI updates.
- Markdown, source lists, and financial tables wrap to terminal width.
- Semantic theme tokens provide primary, success, warning, error, muted, and text styles.
- Symbols plus text communicate state; color is never the only signal.
- `NO_COLOR`, non-TTY output, and limited terminal capability produce plain output.
- Untrusted model, provider, tool, and source text has terminal control characters removed.
- Raw JSON, prompts, credentials, authorization headers, and private reasoning are never rendered by default.

## Input and commands

Interactive input supports normal cursor editing, history, completion, multiline text, Enter to submit, Shift+Enter for a newline, Ctrl+L to redraw, and Ctrl+C to cancel the active run without exiting. Commands are defined in one registry used by parsing, completion, and `/help`.

Initial commands are `/help`, `/clear`, `/new`, `/history`, `/sessions`, `/resume`, `/sources`, `/status`, `/verbose`, `/debug`, `/retry`, `/export`, and `/exit`. Commands remain absent until their behavior exists.

## Cancellation and errors

The UI runs research in a cancellable async worker. Cancellation closes the event iterator, persists a cancelled terminal event, stops indicators, and restores composer focus. A second idle Ctrl+C may exit. User-facing errors are categorized and actionable; detailed exceptions are written to structured logs.

## Persistence

Conversation and run artifacts remain local under `.finai/`. Assistant responses are persisted with user messages. Approval continuation stays under the same run identity rather than recursively creating a new run.

## Compatibility

The existing FastAPI frontend continues receiving its legacy stream shape through an adapter while the typed event stream becomes canonical. Deterministic financial calculations and specialist-agent behavior remain unchanged.

## Verification

Unit tests cover event validation, sequencing, state transitions, command parsing, sanitization, rendering, terminal widths, cancellation, and plain output. Event-sequence tests cover success, approval, clarification, retry, failure, and cancellation. Textual headless tests cover keyboard operation and resize behavior. Live provider checks remain separate.
