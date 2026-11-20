# Airflow adapter

Implemented in [`pipelinemedic/integrations/airflow.py`](../pipelinemedic/integrations/airflow.py). Setup instructions are in the [README](../README.md#run-it-as-a-service-for-airflow).

## Flow

1. **Trigger:** `make_on_failure_callback(endpoint)` posts `dag_id`, `run_id`, `task_id` and `try_number` to the PipelineMedic service. It never raises.
2. **Collect logs:** the service calls `fetch_task_log()`, which reads
   `GET /api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/{try_number}`.
   Some Airflow 2 versions report the next try number inside failure callbacks, so it falls back to the previous one on a 404.
3. **Classify and cite:** `diagnose()` runs the log against `taxonomy.yaml` and traces identifiers in git when `PIPELINEMEDIC_REPO` is set.
4. **Report:** posts to Slack when `SLACK_WEBHOOK_URL` is set, and returns JSON either way.

## Status

- [x] Callback + payload
- [x] Log fetch via REST API v1 (unit-tested with a mocked API)
- [ ] dbt `run_results.json` pickup from inside Airflow tasks
- [ ] End-to-end test against a live Airflow 2.x instance
- [ ] Airflow 3 (REST API v2) support
