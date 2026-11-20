# 🩺 PipelineMedic

[![CI](https://github.com/ducminhvudlt/pipelinemedic/actions/workflows/ci.yml/badge.svg)](https://github.com/ducminhvudlt/pipelinemedic/actions/workflows/ci.yml)

**An AI on-call assistant for data pipelines that refuses to guess.**

When an Airflow DAG, dbt model or Spark job fails at 3am, PipelineMedic collects the evidence, finds the root cause, cites it, and hands a human a clear diagnosis, or says *"I don't know"* and escalates.

> **Status:** MVP (v0.2). Diagnosis, git commit tracing, Slack reports, an HTTP service, an Airflow callback and a SQL safety guard work today and are covered by tests. Automatic fix PRs and clone replay are next. Built in public with [Devin](https://devin.ai).

---

## Why

Every data team knows the morning ritual: a pipeline failed overnight, and someone has to dig through thousands of log lines, recent commits and schema changes before the first coffee. Most failures fall into a small set of repeatable patterns: schema drift, null spikes, expired credentials, late upstream data, bad join fan-out.

PipelineMedic automates the diagnosis, not the judgment. A human always decides what gets merged.

---

## Quickstart

```bash
git clone https://github.com/ducminhvudlt/pipelinemedic && cd pipelinemedic
pip install -e ".[dev]"

python examples/demo.py          # a column rename breaks a model; it finds the commit
pytest -q                        # run the test suite
pipelinemedic eval               # score it on the labeled failure set
```

Output of `examples/demo.py` (the commit hash and time differ on each run):

```
🔴 dbt model fct_orders failed
root cause: schema drift (confidence: high)
evidence:
  - log L3: 03:12:06   column "customer_id" not found
  - commit 4ee6d09 by alice (2026-11-20T03:58): rename customer_id to cust_id in stg_customers [touches "customer_id"]
next: collect upstream_commit, schema_diff to confirm before proposing a fix
```

Every claim is backed by a log line or a commit. No citation, no claim.

### Use it on your own failures

```bash
# a log file, plus your dbt run results and the repo of your dbt project
pipelinemedic diagnose failure.log --run-results target/run_results.json --repo ~/code/dbt-project

# post the report to Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/... pipelinemedic diagnose failure.log --slack

# check that a proposed SQL fix is not destructive
pipelinemedic check-sql fix.sql
```

### Run it as a service for Airflow

```bash
export PIPELINEMEDIC_REPO=~/code/dbt-project
export AIRFLOW_API_URL=http://airflow:8080 AIRFLOW_USERNAME=... AIRFLOW_PASSWORD=...
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
pipelinemedic serve --host 0.0.0.0 --port 8787
```

```python
# in your DAG file
from pipelinemedic.integrations.airflow import make_on_failure_callback

with DAG("orders", default_args={"on_failure_callback": make_on_failure_callback("http://pipelinemedic:8787")}):
    ...
```

When a task fails, the callback sends its IDs to the service, the service pulls the task log through the Airflow REST API (v1, Airflow 2.x), diagnoses it and posts to Slack. The callback never raises, so monitoring can't break your DAG.

---

## How it works

```
failure (log text · dbt run_results.json · Airflow callback)
        │
        ▼
1. COLLECT   task log · failed dbt nodes · git history          ✅ built
        │
        ▼
2. CLASSIFY  match each line against taxonomy.yaml              ✅ built
        │
        ▼
3. CITE      log line numbers + the commit that last touched    ✅ built
             the identifier named in the error (git log -S)
        │
        ▼
4. GUARD     block DROP / DELETE / TRUNCATE in any fix          ✅ built
        │
        ▼
5. REPORT    Slack message · JSON · HTTP response               ✅ built
             └─ no match, or two causes tied → escalate
        │
        ▼
6. FIX       propose a fix PR, replay it on a zero-copy clone   🔜 next
```

### Confidence

| Level | Meaning |
|---|---|
| **high** | A log line **and** a commit both support the cause |
| **medium** | Only log lines support it |
| **none** | Nothing citable, or two causes equally supported: escalate to a human |

---

## Project layout

```
pipelinemedic/
  classifier.py          line-by-line match against taxonomy.yaml, with citations
  diagnose.py            combines all evidence into one Report
  evidence/dbt.py        reads target/run_results.json
  evidence/git.py        finds the commit that changed an identifier
  report.py              Slack text + webhook
  guard.py               blocks destructive SQL
  server.py              HTTP service (standard library only)
  integrations/airflow.py  on_failure_callback + REST log fetcher
  evaluate.py            accuracy / false-confidence / escalation metrics
  cli.py                 `pipelinemedic` command
taxonomy.yaml            failure types, regex signals, required evidence
fixtures/failures.json   labeled failure cases for evaluation
EVAL.md                  latest evaluation report
```

---

## Safety by design

| Guardrail | Detail | Status |
|---|---|---|
| **No destructive SQL** | `DROP`, `DELETE`, `TRUNCATE` and `ALTER ... DROP` are blocked (`guard.py`) | ✅ |
| **Never guesses** | No citation, or a tie between causes, means escalation | ✅ |
| **Can't break your DAG** | The Airflow callback swallows its own errors | ✅ |
| **Read-only in prod** | Only reads logs and git history; holds no warehouse write credentials | ✅ |
| **Never auto-merges** | Fixes will be PRs a human approves | 🔜 with fix stage |
| **Clone-first** | Fixes will be replayed on a zero-copy clone before a PR opens | 🔜 with fix stage |
| **Earned trust** | Runs in diagnosis-only mode until accuracy on real failures is proven | ✅ (current mode) |

---

## Failure taxonomy (v1)

| # | Type | Example signals |
|---|---|---|
| 1 | Schema drift | `column ... not found`, `invalid identifier`, Spark `cannot resolve ... given input columns` |
| 2 | Null spike | dbt `Failure in test not_null_...`, Postgres not-null violation |
| 3 | Expired credentials | `authentication failed`, `invalid_grant`, AWS `ExpiredToken` |
| 4 | Late upstream data | dbt `ERROR STALE`, `AirflowSensorTimeout`, empty partition |
| 5 | Join fan-out | dbt `Failure in test unique_...`, duplicate key violation |

Out-of-memory, network and timeout failures are not in v1 on purpose: PipelineMedic escalates them instead of guessing. Edit `taxonomy.yaml` to add your own signals.

---

## How we measure it

See [EVAL.md](EVAL.md). Results are published wins **and** misses.

- **Accuracy:** does the outcome match the label?
- **False-confidence rate:** how often it named a cause and was wrong (target: < 5%)
- **Escalation rate:** how often it honestly said "I don't know"

> The current evaluation set is synthetic and was written alongside the taxonomy, so it proves the pipeline works end to end, not real-world accuracy. Real, anonymized failures are the next milestone.

---

## Roadmap

- [x] Public repo, failure taxonomy
- [x] Classifier with line citations and tie-escalation
- [x] dbt `run_results.json` evidence
- [x] Git commit tracing for the identifier in the error
- [x] Slack report, CLI, HTTP service
- [x] Airflow callback + REST log fetch
- [x] SQL safety guard
- [x] Evaluation harness + CI
- [ ] Evaluate on 30 real, anonymized failures and publish the results
- [ ] Fix proposals as PRs, verified on a zero-copy clone
- [ ] Spark and Dagster adapters

---

## Contributing

Issues with real (anonymized) pipeline failures are the most valuable contribution: each one becomes an evaluation case.

## License

MIT
