# 🩺 PipelineMedic

**An AI on-call assistant for data pipelines that refuses to guess.**

When an Airflow DAG, dbt model or Spark job fails at 3am, PipelineMedic collects the evidence, finds the root cause, proves it, and hands a human a ready-to-review fix, or says *"I don't know"* and escalates.

> **Status:** 🚧 Early development. Built in public with [Devin](https://devin.ai). Progress, results and failures are published in this repo.

---

## Why

Every data team knows the morning ritual: a pipeline failed overnight, and someone has to dig through thousands of log lines, recent commits and schema changes before the first coffee. Most failures fall into a small set of repeatable patterns: schema drift, null spikes, expired credentials, late upstream data, bad join fan-out.

PipelineMedic automates the diagnosis, not the judgment. A human always decides what gets merged.

---

## What it posts to Slack

```
🔴 dbt model fct_orders failed (03:12)
root cause: upstream schema drift
evidence:
  - log L482: column "customer_id" not found
  - commit a3f9c21 (02:47) renamed customer_id → cust_id in stg_customers
fix: update ref in fct_orders.sql line 14
     (PR #231, tested on clone ✅ row counts match)
confidence: high (2 citations)
```

Every claim is backed by a log line or a commit. No citation, no claim.

---

## How it works

```
failure webhook (Airflow / dbt / Spark / Dagster)
        │
        ▼
1. COLLECT   task logs · last N commits · schema diff · row-count deltas
        │
        ▼
2. CLASSIFY  match against a failure taxonomy (12 known types)
        │
        ▼
3. CITE      every hypothesis must point to an exact log line or commit
        │
        ▼
4. VERIFY    replay the proposed fix on a zero-copy clone
        │
        ▼
5. REPORT    Slack summary + pull request (never auto-merged)
             └─ no proof? → escalate to on-call with the evidence gathered
```

### The core rule

```python
def diagnose(failure):
    evidence = collect(failure)  # logs, diff, schema, row counts
    for hypothesis in rank_hypotheses(evidence):
        proof = find_citation(hypothesis, evidence)
        if proof and replay_on_clone(hypothesis.fix):
            return Diagnosis(hypothesis, proof)
    return escalate(failure, evidence, reason="no proven cause")
```

---

## Safety by design

| Guardrail | Detail |
|---|---|
| **Read-only in prod** | No write credentials to production warehouses |
| **No destructive SQL** | `DROP`, `DELETE`, `TRUNCATE` and destructive `ALTER` are blocked |
| **Never auto-merges** | Output is a PR; a human approves every change |
| **Quarantine, don't delete** | Bad rows go to a side table with a test, never dropped |
| **Clone-first** | Every fix is replayed on a zero-copy clone before a PR is opened |
| **Earned trust** | Starts in summary-only mode; PRs are enabled only after diagnosis accuracy is proven |

---

## Failure taxonomy (v1)

| # | Type | Typical signal |
|---|---|---|
| 1 | Schema drift | `column not found`, type mismatch after an upstream commit |
| 2 | Null spike | Not-null test fails, sudden % null jump in a key column |
| 3 | Expired credentials | Auth / permission errors from a source or warehouse |
| 4 | Late upstream data | Freshness check fails, empty partition |
| 5 | Join fan-out | Row count explodes after a join, uniqueness test fails |

Types 6–12 (OOM, timeouts, dependency version breaks, quota limits, etc.) follow after v1.

---

## Roadmap

- [ ] **Day 1:** Public repo, failure webhook + log collector for dbt
- [ ] **Day 2–3:** Classifier for the 5 v1 failure types
- [ ] **Day 4:** Evidence-citation step (no citation → escalate)
- [ ] **Day 5:** Zero-copy clone replay
- [ ] **Day 6–7:** Run on 30 historical failures, publish the hit rate
- [ ] **Later:** Airflow, Spark and Dagster adapters
- [ ] **Later:** Public leaderboard of diagnosis accuracy on real, anonymized failures

---

## How we measure it

Results are published here, wins **and** misses.

- **Root-cause accuracy:** does the diagnosis match the fix a human actually made?
- **False-confidence rate:** how often it claimed a cause and was wrong (target: < 5%)
- **Time to diagnosis:** vs. an on-call engineer starting from scratch
- **Escalation rate:** how often it honestly said "I don't know"

---

## Contributing

Early days. Issues with real (anonymized) pipeline failures are the most valuable contribution: they become test cases.

## License

MIT
