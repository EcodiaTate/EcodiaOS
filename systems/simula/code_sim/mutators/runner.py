# systems/simula/code_sim/mutation/runner.py
from __future__ import annotations

from dataclasses import dataclass

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

from .mutants import generate_mutants


@dataclass
class MutationResult:
    total: int
    killed: int
    score: float


async def run_mutation_tests(
    changed_files: list[str],
    *,
    k_expr: str = "",
    timeout_sec: int = 900,
) -> dict[str, object]:
    muts = []
    for f in changed_files:
        muts.extend(generate_mutants(f))
    total = len(muts)
    if total == 0:
        return {"status": "noop", "score": 1.0, "total": 0, "killed": 0}
    killed = 0
    async with DockerSandbox(seed_config()).session() as sess:
        for m in muts:
            # apply mutant
            await sess._run_tool(
                [
                    "bash",
                    "-lc",
                    f"python - <<'PY'\nfrom pathlib import Path;Path({m.file!r}).write_text({m.after!r}, encoding='utf-8')\nPY",
                ],
            )
            ok, _ = await sess.run_pytest_select(["tests"], k_expr, timeout=timeout_sec)
            # If tests fail with mutant → killed
            if not ok:
                killed += 1
            # revert file back to original
            await sess._run_tool(
                [
                    "bash",
                    "-lc",
                    f"python - <<'PY'\nfrom pathlib import Path;Path({m.file!r}).write_text({m.before!r}, encoding='utf-8')\nPY",
                ],
            )
    score = killed / total
    return {"status": "done", "score": score, "total": total, "killed": killed}
