"""Airflow integration (targets the Airflow 2.x stable REST API v1).

Two pieces:
- `make_on_failure_callback(endpoint)`: attach to a DAG; on failure it sends
  the task's identifiers to the PipelineMedic service. It never raises, so it
  cannot break your DAG.
- `fetch_task_log(...)`: used by the service to pull the failed task's log
  through the Airflow REST API.

This module does not import Airflow, so it can be tested without it.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from urllib.parse import quote

log = logging.getLogger(__name__)


def fetch_task_log(
    base_url: str,
    dag_id: str,
    run_id: str,
    task_id: str,
    try_number: int,
    username: str | None = None,
    password: str | None = None,
    timeout: float = 15,
) -> str:
    """Fetch a task log. Tries `try_number`, then `try_number - 1`.

    Some Airflow 2 versions report the *next* try number inside failure
    callbacks, so the previous one is tried when the first returns 404.
    """
    last_error: Exception | None = None
    for attempt in dict.fromkeys([try_number, try_number - 1]):
        if attempt < 1:
            continue
        url = (
            f"{base_url.rstrip('/')}/api/v1/dags/{quote(dag_id, safe='')}"
            f"/dagRuns/{quote(run_id, safe='')}/taskInstances/{quote(task_id, safe='')}"
            f"/logs/{attempt}?full_content=true"
        )
        req = urllib.request.Request(url, headers={"Accept": "text/plain"})
        if username:
            token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
            req.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code != 404:
                raise
    raise last_error or RuntimeError("no valid try_number")


def build_payload(context: dict) -> dict:
    ti = context["task_instance"]
    return {
        "title": f"{ti.dag_id}.{ti.task_id}",
        "airflow": {
            "dag_id": ti.dag_id,
            "run_id": context.get("run_id") or getattr(context.get("dag_run"), "run_id", ""),
            "task_id": ti.task_id,
            "try_number": int(ti.try_number),
        },
    }


def make_on_failure_callback(endpoint: str, timeout: float = 10):
    """Return a callback for `on_failure_callback=` on a DAG or task."""

    def callback(context: dict) -> None:
        try:
            body = json.dumps(build_payload(context)).encode()
            req = urllib.request.Request(
                f"{endpoint.rstrip('/')}/diagnose",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=timeout).close()
        except Exception as e:  # never let monitoring break the pipeline
            log.warning("PipelineMedic callback failed: %s", e)

    return callback
