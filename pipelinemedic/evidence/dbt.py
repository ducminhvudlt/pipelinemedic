"""Read dbt's target/run_results.json and pull out the nodes that failed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FAILED_STATUSES = {"error", "fail", "runtime error"}


@dataclass(frozen=True)
class FailedNode:
    unique_id: str
    status: str
    message: str
    relation_name: str | None = None

    def as_log_line(self) -> str:
        return f"{self.unique_id} [{self.status}]: {self.message}"


def load_run_results(path: str | Path) -> list[FailedNode]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    failed = []
    for result in data.get("results", []):
        status = str(result.get("status", "")).lower()
        if status not in FAILED_STATUSES:
            continue
        failed.append(
            FailedNode(
                unique_id=result.get("unique_id", "unknown"),
                status=status,
                message=(result.get("message") or "").strip(),
                relation_name=result.get("relation_name"),
            )
        )
    return failed


def as_log_text(nodes: list[FailedNode]) -> str:
    return "\n".join(n.as_log_line() for n in nodes)
