"""Find the commits that touched an identifier named in a failure.

Uses `git log -S`, which lists commits where the number of occurrences of a
string changed: exactly the commits that added, removed or renamed it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_QUOTED = re.compile(r"\"([A-Za-z_][\w.]*)\"|'([A-Za-z_][\w.]*)'|`([A-Za-z_][\w.]*)`")
_STOPWORDS = {"etl", "error", "null", "true", "false", "none", "public", "main", "default"}


@dataclass(frozen=True)
class CommitCitation:
    sha: str
    author: str
    date: str
    subject: str
    token: str

    def short(self) -> str:
        return self.sha[:7]


def extract_identifiers(lines: list[str]) -> list[str]:
    """Pull quoted identifiers (column, table, model names) out of log lines."""
    seen: list[str] = []
    for line in lines:
        for match in _QUOTED.finditer(line):
            token = next(g for g in match.groups() if g)
            # "schema.table.column" -> also try the last part on its own
            for candidate in (token, token.split(".")[-1]):
                if len(candidate) >= 3 and candidate.lower() not in _STOPWORDS and candidate not in seen:
                    seen.append(candidate)
    return seen


def find_commits_touching(token: str, repo_path: str | Path, limit: int = 3) -> list[CommitCitation]:
    cmd = [
        "git", "-C", str(repo_path), "log", f"--max-count={limit}",
        "-S", token, "--format=%H%x1f%an%x1f%aI%x1f%s",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    commits = []
    for row in out.stdout.splitlines():
        parts = row.split("\x1f")
        if len(parts) == 4:
            commits.append(CommitCitation(*parts, token=token))
    return commits
