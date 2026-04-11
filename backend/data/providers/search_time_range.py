def normalize_ddgs_time_range(
    time_range: str | None, default: str | None = "m"
) -> str | None:
    """Normalize timelimit values for DDGS to the supported set: d, w, m, y."""
    if not time_range:
        return default

    normalized = str(time_range).strip().lower()
    if normalized in {"d", "w", "m", "y"}:
        return normalized

    aliases = {
        "day": "d",
        "daily": "d",
        "week": "w",
        "weekly": "w",
        "month": "m",
        "monthly": "m",
        "year": "y",
        "yearly": "y",
        "90d": "m",
        "d90": "m",
        "3m": "m",
        "last_90_days": "m",
    }
    return aliases.get(normalized, default)
