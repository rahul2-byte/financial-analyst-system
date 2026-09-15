# FIN-AI Textual styles

Textual CSS is not Tailwind and does not support `@apply`. This directory uses
the same useful mental model: tokens first, layout second, semantic components
last. `FinAIApp.CSS_PATH` loads the files in that order.

## Where to edit

- `theme.py`: colors shared by Textual and Rich. Add a token here instead of
  placing a new hex value in a stylesheet.
- `tokens.tcss`: global defaults and small composable utilities such as
  `.text-muted`, `.surface-elevated`, and `.border-subtle`.
- `layout.tcss`: dimensions, grid/rows, responsive breakpoints, and scroll
  regions. Keep widget appearance out of this file.
- `components.tcss`: semantic widget classes (`.user-message`,
  `.run-activity`, `.sources-message`, `.error`) and their state variants.

## Safe change recipe

1. Reuse an existing token or add one to `theme.py`.
2. Choose a semantic class; do not style a one-off widget by its generated
   markup.
3. Put geometry in `layout.tcss` and color/typography in `components.tcss`.
4. Add a focused Textual test when changing a breakpoint or interaction state.

The utility classes are intentionally small. Avoid building a full utility
framework: semantic classes keep the terminal readable at 3am.

The context rail is approximately 17% on wide terminals and is hidden below
120 columns. Responsive classes are `layout-wide`, `layout-medium`,
`layout-compact`, and `layout-narrow`.
