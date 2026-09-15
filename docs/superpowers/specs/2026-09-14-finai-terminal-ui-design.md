# FIN-AI Terminal UI redesign

## Scope

Refresh the existing Textual presentation layer while preserving the typed
research event stream, approval flow, session store, and business logic.

## Design

The app keeps a persistent shell: compact top status bar, navigation rail,
independently scrolling conversation workspace, context rail, anchored
composer, and shortcut footer. Existing render functions remain the source of
runtime text; static welcome/context copy is expanded for useful onboarding.

Theme tokens move to the requested navy/cyan/green palette. Responsive classes
show all regions at 140+ columns, hide navigation context at medium widths,
and keep a usable main/composer layout on narrow terminals. Navigation and
keyboard bindings expose new research, sessions, trace, clear, export/save
labels, sidebar toggle, and help without changing orchestration semantics.

## Verification

Existing terminal tests remain the regression gate. Add focused assertions for
the shell labels, token values, and responsive visibility, then run the
terminal unit tests, full backend tests, and Ruff on changed files.

## Explicit non-goals

No new UI dependency, no quantitative logic, no API changes, no fabricated
financial values, and no full trace/analysis dashboard without corresponding
runtime data.
