from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

mutants_router = APIRouter()

# Use Simula's wrappers (SoC)
try:
    from systems.simula.nscs import agent_tools as _nscs_tools  # type: ignore
except Exception:  # pragma: no cover
    _nscs_tools = None


class Mutant(BaseModel):
    id: str
    diff: str


class EvalRequest(BaseModel):
    mutants: list[Mutant]
    k_expr: str | None = Field(default=None, description="Optional focused pytest -k expression")
    timeout_sec: int = Field(600, ge=60, le=3600)


class EvalResult(BaseModel):
    id: str
    status: str  # "killed" | "survived" | "error"
    details: dict[str, Any] = Field(default_factory=dict)


class EvalResponse(BaseModel):
    ok: bool
    killed: int
    survived: int
    results: list[EvalResult]


@mutants_router.post("/eval", response_model=EvalResponse)
async def mutants_eval(req: EvalRequest) -> EvalResponse:
    if _nscs_tools is None:
        raise HTTPException(status_code=501, detail="Simula NSCS tools not available")

    killed = survived = 0
    results: list[EvalResult] = []

    for m in req.mutants:
        try:
            # Apply mutant diff, run focused or full tests, revert via git checkout --
            # Our apply_refactor wrapper can apply and (optionally) verify paths.
            ap = await _nscs_tools.apply_refactor(diff=m.diff, verify_paths=["tests"])
            if (ap or {}).get("status") not in ("success", "ok"):
                results.append(EvalResult(id=m.id, status="error", details=ap or {}))
                continue

            if req.k_expr:
                t = await _nscs_tools.run_tests_k(
                    paths=["tests"],
                    k_expr=req.k_expr,
                    timeout_sec=req.timeout_sec,
                )
            else:
                t = await _nscs_tools.run_tests_xdist(paths=["tests"], timeout_sec=req.timeout_sec)

            # If tests FAIL with the mutant, the mutant is KILLED (good).
            ok = (t or {}).get("status") == "success"
            if ok:
                survived += 1
                results.append(EvalResult(id=m.id, status="survived", details=t or {}))
            else:
                killed += 1
                results.append(EvalResult(id=m.id, status="killed", details=t or {}))

        except Exception as e:
            results.append(EvalResult(id=m.id, status="error", details={"error": repr(e)}))
        finally:
            # FIXED: Best-effort cleanup is now in a finally block.
            # This ensures the repo state is reset for the next mutant, even if an exception occurs.
            try:
                await _nscs_tools.git_checkout("--", ".")
            except Exception:
                # This is a best-effort cleanup; log if it fails in a real scenario
                pass

    return EvalResponse(ok=True, killed=killed, survived=survived, results=results)


import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# --- basic operators to flip ---
_OP_MUTS: list[tuple[str, str]] = [
    (r"\b==\b", "!="),
    (r"\b!=\b", "=="),
    (r"\bis\b", "is not"),
    (r"\bis\s+not\b", "is"),
    (r">=", "<"),
    (r"<=", ">"),
    (r">", "<="),
    (r"<", ">="),
    (r"\band\b", "or"),
    (r"\bor\b", "and"),
    (r"\bTrue\b", "False"),
    (r"\bFalse\b", "True"),
    (r"\+", "-"),
    (r"-", "+"),
]

_FILE_HDR = re.compile(r"^\+\+\+ b/(.+)$", re.M)


class Mutant(BaseModel):
    id: str
    path: str
    line: int
    op: str
    before: str
    after: str
    diff: str


class GenerateRequest(BaseModel):
    diff: str = Field(..., description="Unified diff")
    max_mutants: int = Field(50, ge=1, le=500)


class GenerateResponse(BaseModel):
    ok: bool
    mutants: list[Mutant] = Field(default_factory=list)


def _changed_blocks(diff: str) -> list[tuple[str, list[tuple[int, str]]]]:
    """
    Return list of (path, [(lineno, line), ... for '+' lines]) based on unified diff.
    """
    files: list[tuple[str, list[tuple[int, str]]]] = []
    cur_path = None
    cur_lines: list[tuple[int, str]] = []
    line_no = 0
    for ln in diff.splitlines():
        if ln.startswith("+++ b/"):
            if cur_path is not None:
                files.append((cur_path, cur_lines))
                cur_lines = []
            cur_path = ln[6:]
            line_no = 0
        elif ln.startswith("@@"):
            # Parse new-file hunk header like @@ -a,b +c,d @@
            m = re.search(r"\+(\d+)", ln)
            line_no = int(m.group(1)) if m else 0
        elif ln.startswith("+") and not ln.startswith("+++ "):
            cur_lines.append((line_no, ln[1:]))
            line_no += 1
        elif ln.startswith("-") and not ln.startswith("--- "):
            # removed line; new-file counter doesn't advance
            pass
        else:
            # context line
            line_no += 1 if ln and not ln.startswith("\\") else 0
    if cur_path is not None:
        files.append((cur_path, cur_lines))
    return files


def _mutate_line(s: str) -> list[tuple[str, str]]:
    muts: list[tuple[str, str]] = []
    for pat, repl in _OP_MUTS:
        if re.search(pat, s):
            after = re.sub(pat, repl, s, count=1)
            muts.append((pat, after))
    return muts


def _diff_for_line(path: str, line: int, before: str, after: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -{line},1 +{line},1 @@\n"
        f"-{before}\n"
        f"+{after}\n"
    )


@mutants_router.post("/generate", response_model=GenerateResponse)
async def mutants_generate(req: GenerateRequest) -> GenerateResponse:
    try:
        blocks = _changed_blocks(req.diff or "")
        out: list[Mutant] = []
        uid = 0
        for path, added in blocks:
            for ln, s in added:
                for pat, after in _mutate_line(s):
                    before = s
                    out.append(
                        Mutant(
                            id=f"m{uid}",
                            path=path,
                            line=ln,
                            op=pat,
                            before=before,
                            after=after,
                            diff=_diff_for_line(path, ln, before, after),
                        ),
                    )
                    uid += 1
                    if len(out) >= req.max_mutants:
                        return GenerateResponse(ok=True, mutants=out)
        return GenerateResponse(ok=True, mutants=out)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"mutants_generate failed: {e!r}")
