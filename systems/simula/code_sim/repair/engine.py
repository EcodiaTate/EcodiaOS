# systems/simula/code_sim/repair/engine.py
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import libcst as cst

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

from .templates import TRANSFORMS, Patch


@dataclass
class RepairOutcome:
    status: str  # "healed" | "partial" | "unchanged" | "error"
    diff: str | None
    tried: int
    notes: str | None = None


def _generate_patches(paths: Iterable[str]) -> list[Patch]:
    """Generates candidate repair patches using a series of LibCST transformers."""
    patches: list[Patch] = []
    for path_str in paths:
        try:
            current_source = Path(path_str).read_text(encoding="utf-8")
            for name, transform_class in TRANSFORMS:
                context = cst.codemod.CodemodContext()
                transformer = transform_class(context)
                tree = cst.parse_module(current_source)
                updated_tree = transformer.transform_module(tree)
                new_source = updated_tree.code

                if new_source != current_source:
                    patches.append(
                        Patch(
                            path=path_str,
                            before=current_source,
                            after=new_source,
                            transform_id=name,
                        ),
                    )
                    current_source = new_source  # Apply transforms sequentially
        except Exception:
            continue  # Skip files that fail to parse or transform
    return patches


async def attempt_repair(paths: Iterable[str], *, timeout_sec: int = 900) -> RepairOutcome:
    """
    Tries a sequence of safe, AST-based transforms on given files, evaluates
    by running tests, and returns a cumulative diff if the tests pass.
    """
    patches = _generate_patches(paths)
    if not patches:
        return RepairOutcome(
            status="unchanged",
            diff=None,
            tried=0,
            notes="No applicable AST transforms found.",
        )

    cfg = seed_config()
    cumulative_diff = ""
    applied_patches = 0

    async with DockerSandbox(cfg).session() as sess:
        # Get baseline diff (in case workspace is dirty)
        initial_diff_result = await sess._run_tool(["git", "diff"])
        initial_diff = initial_diff_result.get("stdout", "")

        for patch in patches:
            # Apply the patch by completely overwriting the file with the new source
            write_ok_result = await sess._run_tool(
                [
                    "python",
                    "-c",
                    f"from pathlib import Path; Path('{patch.path}').write_text({repr(patch.after)}, encoding='utf-8')",
                ],
            )
            if write_ok_result.get("returncode", 1) != 0:
                continue  # Skip if we can't even write the file

            # Run tests to see if this patch fixed the issue
            ok, _ = await sess.run_pytest(list(paths), timeout=timeout_sec)

            if ok:
                # Test suite passed! This is a good patch.
                applied_patches += 1
                # We stop at the first successful repair to return a minimal fix.
                final_diff_result = await sess._run_tool(["git", "diff"])
                final_diff = final_diff_result.get("stdout", "")

                # We must subtract the initial diff to isolate only the changes from this engine
                # A proper diff library would be better, but this is a simple approximation.
                if final_diff.startswith(initial_diff):
                    cumulative_diff = final_diff[len(initial_diff) :]
                else:
                    cumulative_diff = final_diff

                return RepairOutcome(
                    status="healed",
                    diff=cumulative_diff,
                    tried=len(patches),
                    notes=f"Applied {applied_patches} AST patch(es).",
                )

            # Revert the changes if tests failed, to try the next patch from a clean slate
            await sess._run_tool(
                [
                    "python",
                    "-c",
                    f"from pathlib import Path; Path('{patch.path}').write_text({repr(patch.before)}, encoding='utf-8')",
                ],
            )

    return RepairOutcome(
        status="unchanged",
        diff=None,
        tried=len(patches),
        notes="No AST patch resulted in a passing test suite.",
    )
