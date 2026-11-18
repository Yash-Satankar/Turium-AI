ELLIPSIS = "…"


def truncate(text: str, limit: int) -> str:
    """Returns text unchanged if it fits, else cuts it and appends "…"; the result is never longer than limit."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - len(ELLIPSIS)].rstrip() + ELLIPSIS
