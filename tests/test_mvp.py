import json
import subprocess
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from pipelinemedic import check_sql, diagnose, is_safe
from pipelinemedic.cli import main
from pipelinemedic.evaluate import run_eval
from pipelinemedic.evidence.dbt import load_run_results
from pipelinemedic.evidence.git import extract_identifiers, find_commits_touching
from pipelinemedic.integrations import airflow
from pipelinemedic.report import to_slack_text
from pipelinemedic.server import make_server

SCHEMA_LOG = '03:12:06 Database Error in model fct_orders\n03:12:06   column "customer_id" not found\n'


# --- git evidence -----------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "dev@example.com")
    git("config", "user.name", "Dev")
    model = tmp_path / "stg_customers.sql"
    model.write_text("select id as customer_id from raw.customers\n")
    git("add", ".")
    git("commit", "-q", "-m", "add stg_customers")
    model.write_text("select id as cust_id from raw.customers\n")
    git("commit", "-q", "-am", "rename customer_id to cust_id")
    return tmp_path


def test_extract_identifiers():
    assert extract_identifiers(['column "analytics.customer_id" not found', "user 'etl'"]) == [
        "analytics.customer_id", "customer_id",
    ]


def test_find_commits_touching(repo):
    commits = find_commits_touching("customer_id", repo)
    assert commits[0].subject == "rename customer_id to cust_id"


def test_diagnose_cites_the_breaking_commit(repo):
    report = diagnose(log=SCHEMA_LOG, repo_path=repo)
    assert report.failure_type == "schema_drift"
    assert report.confidence == "high"
    assert report.commit_citations[0].subject == "rename customer_id to cust_id"
    text = to_slack_text(report, "fct_orders")
    assert "log L2" in text and "rename customer_id to cust_id" in text


def test_diagnose_without_repo_is_medium_confidence():
    report = diagnose(log=SCHEMA_LOG)
    assert report.confidence == "medium"


def test_diagnose_escalates_unknown():
    report = diagnose(log="Task exited with return code -9")
    assert report.escalate and report.confidence == "none"
    assert "no proven cause" in to_slack_text(report)


# --- dbt evidence -----------------------------------------------------------

def test_dbt_run_results(tmp_path):
    rr = tmp_path / "run_results.json"
    rr.write_text(json.dumps({"results": [
        {"unique_id": "model.shop.fct_orders", "status": "error",
         "message": 'Database Error: column "customer_id" not found'},
        {"unique_id": "model.shop.dim_users", "status": "success", "message": "OK"},
    ]}))
    nodes = load_run_results(rr)
    assert [n.unique_id for n in nodes] == ["model.shop.fct_orders"]
    report = diagnose(run_results_path=rr)
    assert report.failure_type == "schema_drift"
    assert report.failed_nodes[0].unique_id == "model.shop.fct_orders"


# --- safety guard -----------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DROP TABLE analytics.orders",
    "delete from orders where customer_id is null",
    "TRUNCATE orders",
    "alter table orders drop column region",
])
def test_guard_blocks_destructive_sql(sql):
    assert not is_safe(sql)


def test_guard_allows_quarantine_and_ignores_comments_and_strings():
    sql = """
    -- never DROP TABLE here
    insert into quarantine.orders select * from orders where customer_id is null;
    select 'delete from x' as note;
    """
    assert check_sql(sql) == []


# --- eval -------------------------------------------------------------------

def test_eval_runs_on_fixtures():
    result = run_eval()
    assert result.total >= 15
    assert 0 <= result.false_confidence <= 1
    assert "Accuracy" in result.to_markdown()


# --- airflow ----------------------------------------------------------------

def _fake_response(body: bytes):
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    return resp


def test_fetch_task_log_falls_back_to_previous_try():
    import urllib.error

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if req.full_url.split("/logs/")[1].startswith("2"):
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        return _fake_response(b"the log")

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        text = airflow.fetch_task_log("http://af", "d", "manual__2026-11-20T03:00", "t", 2, "u", "p")
    assert text == "the log"
    assert "/logs/2" in calls[0] and "/logs/1" in calls[1]
    assert "manual__2026-11-20T03%3A00" in calls[0]


def test_failure_callback_never_raises():
    ti = SimpleNamespace(dag_id="d", task_id="t", try_number=1)
    cb = airflow.make_on_failure_callback("http://127.0.0.1:1")
    cb({"task_instance": ti, "run_id": "r"})  # nothing listening: must not raise
    assert airflow.build_payload({"task_instance": ti, "run_id": "r"})["title"] == "d.t"


# --- server -----------------------------------------------------------------

@pytest.fixture
def server(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PIPELINEMEDIC_REPO", raising=False)
    srv = make_server(port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_server_health_and_diagnose(server):
    with urllib.request.urlopen(f"{server}/health", timeout=5) as r:
        assert json.loads(r.read()) == {"status": "ok"}
    out = _post(f"{server}/diagnose", {"log": SCHEMA_LOG, "title": "fct_orders"})
    assert out["report"]["failure_type"] == "schema_drift"
    assert out["slack_text"].startswith("🔴 fct_orders failed")


def test_server_rejects_empty_payload(server):
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as e:
        _post(f"{server}/diagnose", {"title": "x"})
    assert e.value.code == 400


# --- cli --------------------------------------------------------------------

def test_cli_diagnose_and_check_sql(tmp_path, capsys):
    log = tmp_path / "f.log"
    log.write_text(SCHEMA_LOG)
    assert main(["diagnose", str(log), "--title", "fct_orders"]) == 0
    assert "schema drift" in capsys.readouterr().out
    fix = tmp_path / "fix.sql"
    fix.write_text("drop table orders")
    assert main(["check-sql", str(fix)]) == 1
