"""Command line interface.

    pipelinemedic diagnose failure.log [--run-results target/run_results.json] [--repo .]
    pipelinemedic eval [--write EVAL.md]
    pipelinemedic serve [--port 8787]
    pipelinemedic check-sql fix.sql
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .diagnose import diagnose
from .evaluate import DEFAULT_FIXTURES, run_eval
from .guard import check_sql
from .report import post_to_slack, to_slack_text


def _cmd_diagnose(args) -> int:
    log = Path(args.log).read_text(encoding="utf-8") if args.log and args.log != "-" else ""
    if args.log == "-":
        log = sys.stdin.read()
    if not log and not args.run_results:
        print("error: give a log file, '-' for stdin, or --run-results", file=sys.stderr)
        return 2
    report = diagnose(log=log, run_results_path=args.run_results, repo_path=args.repo)
    text = to_slack_text(report, args.title)
    print(json.dumps(report.to_dict(), indent=2, default=str) if args.json else text)
    if args.slack:
        webhook = os.environ.get("SLACK_WEBHOOK_URL")
        if not webhook:
            print("error: --slack needs SLACK_WEBHOOK_URL", file=sys.stderr)
            return 2
        post_to_slack(webhook, text)
    return 0


def _cmd_eval(args) -> int:
    result = run_eval(args.fixtures)
    md = result.to_markdown()
    if args.write:
        Path(args.write).write_text(md, encoding="utf-8")
    print(
        f"cases={result.total} accuracy={result.accuracy:.0%} "
        f"false_confidence={result.false_confidence:.0%} escalation={result.escalation_rate:.0%}"
    )
    return 0


def _cmd_serve(args) -> int:
    from .server import serve

    serve(args.host, args.port)
    return 0


def _cmd_check_sql(args) -> int:
    problems = check_sql(Path(args.file).read_text(encoding="utf-8"))
    if problems:
        print("BLOCKED: " + ", ".join(problems))
        return 1
    print("safe")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipelinemedic", description="Cited root-cause analysis for failed data pipelines.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="diagnose a failure log")
    d.add_argument("log", nargs="?", help="log file, or '-' for stdin")
    d.add_argument("--run-results", help="path to dbt target/run_results.json")
    d.add_argument("--repo", help="git repo to search for the commit that caused it")
    d.add_argument("--title", default="pipeline")
    d.add_argument("--json", action="store_true")
    d.add_argument("--slack", action="store_true", help="also post to SLACK_WEBHOOK_URL")
    d.set_defaults(func=_cmd_diagnose)

    e = sub.add_parser("eval", help="score diagnoses on labeled failures")
    e.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    e.add_argument("--write", help="write a markdown report to this path")
    e.set_defaults(func=_cmd_eval)

    s = sub.add_parser("serve", help="run the HTTP service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(func=_cmd_serve)

    c = sub.add_parser("check-sql", help="block destructive SQL in a proposed fix")
    c.add_argument("file")
    c.set_defaults(func=_cmd_check_sql)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
