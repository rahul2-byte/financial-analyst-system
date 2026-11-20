"""Design tokens shared by FIN-AI's Textual stylesheets and Rich renderers.

Spec: docs/design/tui-redesign.md. Hierarchy comes from colour and weight only.
"""

from __future__ import annotations

INK = "#131312"
GRAPHITE = "#23211F"
RULE = "#2E2C29"
PAPER = "#E7E4DC"
DIM = "#98948A"
LEDGER = "#D4A55A"
GAIN = "#86B98A"
LOSS = "#D9796B"
WARN = "#CFC66F"  # partial runs; deliberately not ledger amber
FAINT = "#837F75"  # domains/URLs, still >= 4.5:1 on ink

# Exposed to .tcss as $fin-<name>.
CSS_VARIABLES: dict[str, str] = {
    "fin-ink": INK,
    "fin-graphite": GRAPHITE,
    "fin-rule": RULE,
    "fin-paper": PAPER,
    "fin-dim": DIM,
    "fin-ledger": LEDGER,
    "fin-gain": GAIN,
    "fin-loss": LOSS,
    "fin-warn": WARN,
    "fin-faint": FAINT,
}

COLORS = {
    "ink": INK,
    "graphite": GRAPHITE,
    "rule": RULE,
    "paper": PAPER,
    "dim": DIM,
    "ledger": LEDGER,
    "gain": GAIN,
    "loss": LOSS,
    "warn": WARN,
    "faint": FAINT,
}
