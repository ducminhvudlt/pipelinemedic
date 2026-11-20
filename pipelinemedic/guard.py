"""Safety guard: refuse any proposed SQL fix that could destroy data.

PipelineMedic quarantines bad rows; it never drops or deletes them. Every
fix it proposes must pass `check_sql` before a pull request is opened.
"""

from __future__ import annotations

import re

_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_STRINGS = re.compile(r"'(?:[^']|'')*'")

_BLOCKED = [
    (re.compile(r"\bdrop\s+(table|view|schema|database|column)\b", re.I), "DROP"),
    (re.compile(r"\bdelete\s+from\b", re.I), "DELETE"),
    (re.compile(r"\btruncate\b", re.I), "TRUNCATE"),
    (re.compile(r"\balter\s+table\b[^;]*\bdrop\b", re.I), "ALTER TABLE ... DROP"),
]


def check_sql(sql: str) -> list[str]:
    """Return the destructive operations found; an empty list means safe."""
    cleaned = _STRINGS.sub("''", _COMMENTS.sub(" ", sql))
    found = []
    for pattern, name in _BLOCKED:
        if pattern.search(cleaned) and name not in found:
            found.append(name)
    return found


def is_safe(sql: str) -> bool:
    return not check_sql(sql)
