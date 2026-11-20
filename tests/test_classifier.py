from pipelinemedic import classify

SCHEMA_DRIFT_LOG = """\
03:12:01 Running with dbt=1.8.2
03:12:04 1 of 12 START sql table model analytics.fct_orders
03:12:06 Database Error in model fct_orders (models/marts/fct_orders.sql)
03:12:06   column "customer_id" not found in stg_customers
03:12:06 1 of 12 ERROR creating sql table model analytics.fct_orders
"""

EXPIRED_CREDS_LOG = """\
[2026-11-20 03:00:00] INFO - Starting extract from postgres_source
[2026-11-20 03:00:02] ERROR - FATAL: password authentication failed for user "etl"
[2026-11-20 03:00:02] ERROR - Task failed with exception
"""

UNKNOWN_LOG = """\
[2026-11-20 03:00:00] INFO - Starting task
[2026-11-20 03:00:05] ERROR - Task exited with return code -9
"""

AMBIGUOUS_LOG = """\
ERROR column "id" not found
ERROR permission denied for table orders
"""


def test_schema_drift_is_cited_by_line():
    d = classify(SCHEMA_DRIFT_LOG)
    assert d.failure_type == "schema_drift"
    assert [c.line_no for c in d.citations] == [4]
    assert "upstream_commit" in d.required_evidence


def test_expired_credentials():
    d = classify(EXPIRED_CREDS_LOG)
    assert d.failure_type == "expired_credentials"
    assert d.citations[0].line_no == 2


def test_no_match_escalates_instead_of_guessing():
    d = classify(UNKNOWN_LOG)
    assert d.escalate
    assert "escalating" in d.summary()


def test_tie_between_types_escalates():
    d = classify(AMBIGUOUS_LOG)
    assert d.escalate
    assert d.candidates == {"schema_drift": 1, "expired_credentials": 1}


def test_summary_contains_evidence():
    out = classify(SCHEMA_DRIFT_LOG).summary()
    assert "log L4" in out
    assert "schema drift" in out
