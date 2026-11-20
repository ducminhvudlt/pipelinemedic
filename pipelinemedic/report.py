"""Turn a Report into a Slack message, and optionally send it."""

from __future__ import annotations

import json
import urllib.request

from .diagnose import Report


def to_slack_text(report: Report, title: str = "pipeline") -> str:
    if report.escalate:
        lines = [
            f"🟡 {title} failed: no proven cause",
            "PipelineMedic found no evidence it could cite, so it is escalating instead of guessing.",
        ]
        if report.candidates:
            considered = ", ".join(f"{k} ({v} line)" for k, v in report.candidates.items())
            lines.append(f"considered but tied: {considered}")
        if report.failed_nodes:
            lines.append("failing dbt nodes: " + ", ".join(n.unique_id for n in report.failed_nodes))
        return "\n".join(lines)

    lines = [
        f"🔴 {title} failed",
        f"root cause: {report.failure_type.replace('_', ' ')} (confidence: {report.confidence})",
        "evidence:",
    ]
    for c in report.log_citations:
        lines.append(f"  - log L{c.line_no}: {c.text.strip()}")
    for c in report.commit_citations:
        lines.append(f"  - commit {c.short()} by {c.author} ({c.date[:16]}): {c.subject} [touches \"{c.token}\"]")
    if report.failed_nodes:
        lines.append("failing dbt nodes: " + ", ".join(n.unique_id for n in report.failed_nodes))
    lines.append("next: collect " + ", ".join(report.required_evidence) + " to confirm before proposing a fix")
    return "\n".join(lines)


def post_to_slack(webhook_url: str, text: str, timeout: float = 10) -> int:
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status
