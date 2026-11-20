"""Classify a pipeline failure log against the failure taxonomy.

The rule PipelineMedic never breaks: every diagnosis cites the exact log
lines that support it. If nothing in the log matches a known failure type,
the result is an escalation, not a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_TAXONOMY = Path(__file__).resolve().parent.parent / "taxonomy.yaml"


@dataclass(frozen=True)
class Citation:
    line_no: int  # 1-based line number in the log
    text: str
    signal: str  # the taxonomy signal that matched


@dataclass
class Diagnosis:
    failure_type: str | None  # None means "I don't know"
    citations: list[Citation] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    candidates: dict[str, int] = field(default_factory=dict)

    @property
    def escalate(self) -> bool:
        return self.failure_type is None

    def summary(self) -> str:
        if self.escalate:
            return "🟡 no proven cause: escalating to on-call with the raw log"
        cites = "\n".join(f"  - log L{c.line_no}: {c.text.strip()}" for c in self.citations)
        needs = ", ".join(self.required_evidence)
        return (
            f"🔴 root cause: {self.failure_type.replace('_', ' ')}\n"
            f"evidence:\n{cites}\n"
            f"next: collect {needs} to confirm before proposing a fix"
        )


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY) -> dict:
    with open(path, encoding="utf-8") as f:
        taxonomy = yaml.safe_load(f)
    for name, spec in taxonomy.items():
        spec["_patterns"] = [re.compile(s, re.IGNORECASE) for s in spec["signals"]]
    return taxonomy


def classify(log: str, taxonomy: dict | None = None) -> Diagnosis:
    """Return the failure type with the most cited log lines, or an escalation.

    A tie between two types is treated as ambiguous and escalated too:
    PipelineMedic does not pick between equally supported causes.
    """
    taxonomy = taxonomy or load_taxonomy()
    hits: dict[str, list[Citation]] = {}

    for line_no, line in enumerate(log.splitlines(), start=1):
        for name, spec in taxonomy.items():
            for signal, pattern in zip(spec["signals"], spec["_patterns"]):
                if pattern.search(line):
                    hits.setdefault(name, []).append(Citation(line_no, line, signal))
                    break  # one citation per line per type

    if not hits:
        return Diagnosis(failure_type=None)

    candidates = {name: len(c) for name, c in hits.items()}
    ranked = sorted(candidates.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return Diagnosis(failure_type=None, candidates=candidates)

    best = ranked[0][0]
    return Diagnosis(
        failure_type=best,
        citations=hits[best],
        required_evidence=list(taxonomy[best]["evidence"]),
        candidates=candidates,
    )


if __name__ == "__main__":
    import sys

    text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
    print(classify(text).summary())
