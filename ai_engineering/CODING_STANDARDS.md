# CODING STANDARDS

## Language

Python 3.11+

## Style

- PEP8 compliant
- Type hints mandatory
- Use Pydantic or dataclasses for schemas
- No global state
- No magic numbers
- No circular imports

## Architecture

- Dependency Injection
- Interface-based design
- No hard-coded model references
- Configuration via environment variables

## Performance

- Use vectorization (NumPy, Pandas)
- Avoid Python loops where possible
- Batch processing preferred
- Minimize memory duplication

## Testing

- Unit tests required
- Edge case handling mandatory
- Schema validation enforced
- No untested modules

## Logging

- Structured logging required
- Execution time tracking
- Error categorization
