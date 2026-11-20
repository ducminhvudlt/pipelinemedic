# Airflow adapter (planned, week 2)

dbt usually runs inside Airflow, so the Airflow adapter lets PipelineMedic explain a failure across both layers:
*"Airflow task failed because dbt model X broke because commit Y renamed a column."*

## How it plugs in

1. **Trigger:** an `on_failure_callback` on the DAG sends `dag_id`, `run_id`, `task_id` and `try_number` to PipelineMedic.
2. **Collect logs:** pull the task log through the Airflow REST API:
   `GET /api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/{try_number}`
3. **dbt context:** if the failed task ran dbt, read `target/run_results.json` to get the failing model and its compiled SQL.
4. **Classify:** run the log through `pipelinemedic.classify()` against `taxonomy.yaml`.
5. **Report:** post the cited diagnosis to Slack. No citation means escalation.

## Callback sketch

```python
def pipelinemedic_on_failure(context):
    ti = context["task_instance"]
    payload = {
        "dag_id": ti.dag_id,
        "run_id": context["run_id"],
        "task_id": ti.task_id,
        "try_number": ti.try_number,
    }
    # POST payload to the PipelineMedic service (to be built)
```

## Status

- [ ] Callback + payload
- [ ] Log fetch via REST API
- [ ] `run_results.json` parsing for dbt tasks
- [ ] End-to-end test on a local Airflow
