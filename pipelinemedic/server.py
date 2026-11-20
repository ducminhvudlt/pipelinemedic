"""A small HTTP service that receives failures and returns cited diagnoses.

POST /diagnose  JSON body, any of:
    {"log": "...raw log text...", "title": "my_dag.my_task"}
    {"airflow": {"dag_id": ..., "run_id": ..., "task_id": ..., "try_number": 1}}
GET  /health

Configuration (environment variables, all optional):
    PIPELINEMEDIC_REPO   path to the git repo of your dbt/pipeline code
    SLACK_WEBHOOK_URL    post every report to this Slack incoming webhook
    AIRFLOW_API_URL      base URL of the Airflow webserver, for log fetching
    AIRFLOW_USERNAME / AIRFLOW_PASSWORD   basic auth for the Airflow API

Standard library only, so it runs anywhere Python does.
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .diagnose import diagnose
from .integrations.airflow import fetch_task_log
from .report import post_to_slack, to_slack_text

log = logging.getLogger(__name__)
MAX_BODY = 5 * 1024 * 1024


def handle_failure(payload: dict) -> dict:
    text = payload.get("log") or ""
    af = payload.get("airflow")
    if not text and af:
        base = os.environ.get("AIRFLOW_API_URL")
        if not base:
            raise ValueError("airflow payload received but AIRFLOW_API_URL is not set")
        text = fetch_task_log(
            base, af["dag_id"], af["run_id"], af["task_id"], int(af.get("try_number", 1)),
            os.environ.get("AIRFLOW_USERNAME"), os.environ.get("AIRFLOW_PASSWORD"),
        )
    if not text:
        raise ValueError("provide 'log' or 'airflow' in the request body")

    report = diagnose(log=text, repo_path=os.environ.get("PIPELINEMEDIC_REPO"))
    title = payload.get("title") or "pipeline"
    slack_text = to_slack_text(report, title)

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if webhook:
        try:
            post_to_slack(webhook, slack_text)
        except Exception as e:
            log.warning("Slack post failed: %s", e)

    return {"report": report.to_dict(), "slack_text": slack_text}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/diagnose":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": "missing or oversized body"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            self._send(200, handle_failure(payload))
        except (ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            log.exception("diagnosis failed")
            self._send(500, {"error": str(e)})

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)


def make_server(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = make_server(host, port)
    print(f"PipelineMedic listening on http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
