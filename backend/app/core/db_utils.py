"""Small database helpers shared by repositories."""

from __future__ import annotations

LIKE_ESCAPE = "\\"


def escape_like(value: str, escape: str = LIKE_ESCAPE) -> str:
    """Escape the LIKE/ILIKE metacharacters in a user-supplied fragment.

    ``%`` and ``_`` are wildcards and the escape character itself must be
    doubled, otherwise a query such as ``%`` matches every row and ``_``
    matches any single character — an easy way to enumerate or slow down a
    table. Use together with ``escape=LIKE_ESCAPE`` on the ``ilike`` call::

        Model.name.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE)
    """
    return (
        value.replace(escape, escape + escape)
        .replace("%", escape + "%")
        .replace("_", escape + "_")
    )


def contains(value: str) -> str:
    """``%<escaped value>%`` — the pattern for a substring search."""
    return f"%{escape_like(value)}%"
