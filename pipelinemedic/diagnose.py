"""Combine every evidence source into one cited diagnosis.

Confidence levels:
- high:   a log line AND a commit both support the cause
- medium: only log lines support it
- none:   nothing citable -> escalate to a human
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .classifier import Citation, classify, load_taxonomy
from .evidence.dbt import FailedNode, as_log_text, load_run_results
from .evidence.git import CommitCitation, extract_identifiers, find_commits_touching

# Failure types where a code change is a plausible cause worth tracing in git.
CODE_CAUSED = {"schema_drift", "null_spike", "join_fanout"}


@dataclass
class Report:
    failure_type: str | None
    confidence: str
    log_citations: list[Citation] = field(default_factory=list)
    commit_citations: list[CommitCitation] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    failed_nodes: list[FailedNode] = field(default_factory=list)
    candidates: dict[str, int] = field(default_factory=dict)

    @property
    def escalate(self) -> bool:
        return self.failure_type is None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["escalate"] = self.escalate
        return d


def diagnose(
    log: str = "",
    run_results_path: str | Path | None = None,
    repo_path: str | Path | None = None,
    taxonomy: dict | None = None,
) -> Report:
    taxonomy = taxonomy or load_taxonomy()

    nodes: list[FailedNode] = []
    text = log
    if run_results_path:
        nodes = load_run_results(run_results_path)
        extra = as_log_text(nodes)
        text = f"{log}\n{extra}" if log else extra

    result = classify(text, taxonomy)
    if result.escalate:
        return Report(failure_type=None, confidence="none", failed_nodes=nodes,
                      candidates=result.candidates)

    commits: list[CommitCitation] = []
    if repo_path and result.failure_type in CODE_CAUSED:
        for token in extract_identifiers([c.text for c in result.citations]):
            # only the most recent change to the identifier is the suspect
            for commit in find_commits_touching(token, repo_path, limit=1):
                if commit.sha not in {c.sha for c in commits}:
                    commits.append(commit)
        commits = commits[:3]

    return Report(
        failure_type=result.failure_type,
        confidence="high" if commits else "medium",
        log_citations=result.citations,
        commit_citations=commits,
        required_evidence=result.required_evidence,
        failed_nodes=nodes,
        candidates=result.candidates,
    )
