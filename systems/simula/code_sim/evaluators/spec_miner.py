# systems/simula/code_sim/evaluators/spec_miner.py
from __future__ import annotations

from dataclasses import dataclass

from systems.simula.code_sim.diagnostics.error_parser import parse_pytest_output


@dataclass
class AcceptanceHint:
    file: str
    line: int
    test: str | None
    errtype: str | None
    message: str | None
    suggestion: str


def _suggestion(errtype: str | None, msg: str | None) -> str:
    t = (errtype or "").lower()
    (msg or "").lower()
    if "typeerror" in t:
        return "Add input-type guard or coerce types; update acceptance spec for type contracts."
    if "assertionerror" in t:
        return "Document invariant as explicit acceptance; adjust function behavior or tests accordingly."
    if "keyerror" in t or "indexerror" in t:
        return "Guard missing keys/indices or return safe default."
    return "Add acceptance clause for this edge case and implement guard."


def derive_acceptance(proposal_tests_stdout: str) -> dict[str, list[dict[str, str | int]]]:
    fails = parse_pytest_output(proposal_tests_stdout)
    hints: list[AcceptanceHint] = []
    for f in fails:
        hints.append(
            AcceptanceHint(
                file=f.file,
                line=f.line,
                test=f.test,
                errtype=f.errtype,
                message=f.message,
                suggestion=_suggestion(f.errtype, f.message),
            ),
        )
    return {
        "acceptance_hints": [
            {
                "file": h.file,
                "line": h.line,
                "test": h.test or "",
                "errtype": h.errtype or "",
                "message": h.message or "",
                "suggestion": h.suggestion,
            }
            for h in hints
        ],
    }
