"""End-to-end demo: a column rename breaks a dbt model, PipelineMedic finds the commit.

    python examples/demo.py

Creates a throwaway git repo, commits a model, renames a column in a second
commit, then diagnoses the resulting dbt error against that repo.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipelinemedic import diagnose  # noqa: E402
from pipelinemedic.report import to_slack_text  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


with tempfile.TemporaryDirectory() as repo:
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "alice@example.com")
    git(repo, "config", "user.name", "alice")
    model = Path(repo) / "stg_customers.sql"
    model.write_text("select id as customer_id, email from raw.customers\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "add stg_customers")
    model.write_text("select id as cust_id, email from raw.customers\n")
    git(repo, "commit", "-q", "-am", "rename customer_id to cust_id in stg_customers")

    log = (
        "03:12:04 1 of 12 START sql table model analytics.fct_orders\n"
        "03:12:06 Database Error in model fct_orders (models/marts/fct_orders.sql)\n"
        '03:12:06   column "customer_id" not found\n'
        "03:12:06 1 of 12 ERROR creating sql table model analytics.fct_orders\n"
    )
    print(to_slack_text(diagnose(log=log, repo_path=repo), "dbt model fct_orders"))
