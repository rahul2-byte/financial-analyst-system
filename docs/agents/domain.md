# Domain Docs

Before exploring the codebase, read:

- `CONTEXT.md` at the repo root, if present
- `docs/adr/` for architecture decisions relevant to the task

If these files do not exist, proceed without creating them upfront. The domain-modeling skill creates them when domain terms or decisions actually need to be recorded.

## Layout

This is a single-context repository:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

Use terminology from `CONTEXT.md` when it exists. If an output conflicts with an ADR, call out the conflict explicitly.
