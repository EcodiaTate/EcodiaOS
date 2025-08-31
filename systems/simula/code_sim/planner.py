# systems/simula/code_sim/planner.py
"""
Simula Planner (objective → executable plan)

Turns a high-level objective YAML (already loaded as a dict) into a concrete,
validated, and *iterable* plan that the orchestrator can execute.

Scope
-----
- Validate and normalize a raw objective dictionary.
- Decompose it into ordered, typed Step objects based on the canonical schema.
- Provide utilities for resolving tests and pretty-printing the final plan.

Design
------
- Pure stdlib. Deterministic.
- Uses the canonical, typed dataclasses from `specs.schema` as the source of truth.
- Raises ValueError with precise messages for malformed objective dictionaries.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# UNIFIED SCHEMAS: Import the canonical dataclasses.
from .specs.schema import (
    Constraints,
    Objective,
    Plan,
    Step,
    StepTarget,
)

# =========================
# Validation & Normalization Helpers
# =========================

_REQUIRED_TOP_LEVEL = ("id", "title", "steps", "acceptance", "iterations")


def _as_list(x: Any) -> list[Any]:
    """Coerces a value to a list if it isn't one already."""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _require_keys(d: dict[str, Any], keys: list[str], ctx: str) -> None:
    """Ensures a dictionary contains a set of required keys."""
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"Objective missing required {ctx} keys: {missing}")


def _get(obj: Any, key: str, default=None):
    """Dict-or-attr getter."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_path(obj: Any, path: Sequence[str], default=None):
    """Nested getter by path: ['acceptance','unit_tests','patterns']"""
    cur = obj
    for i, k in enumerate(path):
        if cur is None:
            return default
        cur = _get(cur, k, None if i < len(path) - 1 else default)
    return cur if cur is not None else default


# Accept targets specified as strings, dicts, or lists of either.
def _normalize_targets(raw: Any) -> list[dict[str, Any]]:
    """
    Normalize `targets` into a list of dicts for StepTarget.from_dict.
    Accepts:
      - "." or "src"                      -> [{"file": "."}] / [{"file": "src"}]
      - {"file": "src"} / {"path":"src"}  -> [{"file":"src"}]
      - ["src", {"file":"tests"}]         -> [{"file":"src"},{"file":"tests"}]
    """

    def _to_file_dict(v: Any) -> dict[str, Any]:
        # Accept mapping; prefer "file" key, tolerate "path"
        if isinstance(v, dict):
            if "file" in v and isinstance(v["file"], str | bytes | bytearray):
                s = (
                    v["file"].decode()
                    if isinstance(v["file"], bytes | bytearray)
                    else str(v["file"])
                )
                return {"file": (s.strip() or ".")}
            if "path" in v and isinstance(v["path"], str | bytes | bytearray):
                s = (
                    v["path"].decode()
                    if isinstance(v["path"], bytes | bytearray)
                    else str(v["path"])
                )
                out = dict(v)
                out.pop("path", None)
                out["file"] = s.strip() or "."
                return out
            # Pass through unknown mappings but ensure a file key exists if possible
            if "file" not in v:
                return {"file": ".", **v}
            return v

        # Accept string/bytes → {"file": "..."}
        if isinstance(v, str | bytes | bytearray):
            s = v.decode() if isinstance(v, bytes | bytearray) else str(v)
            return {"file": (s.strip() or ".")}

        raise ValueError("targets items must be string or mapping")

    if raw is None:
        return [{"file": "."}]

    if isinstance(raw, str | bytes | bytearray) or isinstance(raw, dict):
        return [_to_file_dict(raw)]

    if isinstance(raw, list | tuple | set):
        norm: list[dict[str, Any]] = []
        for i, item in enumerate(raw):
            try:
                norm.append(_to_file_dict(item))
            except ValueError as e:
                raise ValueError(f"Invalid target at index {i}: expected string or mapping.") from e
        return norm

    raise ValueError("targets must be string | mapping | list")


def _normalize_tests(step_dict: dict[str, Any], objective_obj: Objective) -> list[str]:
    """
    Resolves which tests to run for a step.
    """
    # Step-local override
    if "tests" in step_dict and step_dict["tests"]:
        return [str(t) for t in _as_list(step_dict["tests"])]

    # Objective-level acceptance
    acc = getattr(objective_obj, "acceptance", None)
    tests: Any = None
    if acc is not None:
        # Accept either field name
        tests = getattr(acc, "tests", None)
        if not tests:
            ut = getattr(acc, "unit_tests", None)
            if ut:
                tests = getattr(ut, "patterns", None) or getattr(ut, "paths", None) or []

    if isinstance(tests, str | Path):
        tests = [str(tests)]
    elif not isinstance(tests, list):
        tests = list(tests) if tests else []

    # Default to a broad pattern if nothing provided
    return [str(t) for t in tests] or ["tests/**/*.py"]


def _validate_iterations(obj_dict: dict[str, Any]) -> tuple[int, float]:
    """Validates the top-level 'iterations' block.
    Allows defaults if missing."""
    it = obj_dict.get("iterations", {})
    if not isinstance(it, dict):
        raise ValueError("iterations must be a mapping with optional keys {max, target_score}")

    # Defaults tolerate upstream omission; orchestrator may still override.
    max_iters = int(it.get("max", 3))
    target_score = float(it.get("target_score", 0.8))

    if max_iters <= 0:
        raise ValueError("iterations.max must be > 0")
    if not (0.0 <= target_score <= 1.0):
        raise ValueError("iterations.target_score must be in [0,1]")

    return max_iters, target_score


def _validate_acceptance(obj_dict: dict[str, Any]) -> None:
    """Performs basic validation on the 'acceptance' block."""
    acc = obj_dict.get("acceptance", {})
    if not isinstance(acc, dict):
        raise ValueError("acceptance must be a mapping")

    unit = acc.get("unit_tests", {})
    if unit and not isinstance(unit, dict):
        raise ValueError("acceptance.unit_tests must be a mapping if present")

    # No hard requirement for tests at planning time; scaffolding steps may omit them.


def _normalize_steps_list(objective_dict: dict) -> list[dict]:
    """
    Normalize 'steps' from an objective into a list of step dicts with fields:
      - name (str)
      - targets (list[str|dict]) -> defaults to ['.'] if missing/empty; finalized later
      - kind (str)               -> optional
      - payload (dict)           -> optional

    Accepts:
      steps: ["do x",
              {"name":"do y", "targets":"src"},
              {"name":"do z","targets":["src","tests"]}]
    """
    raw = objective_dict.get("steps")
    if raw is None:
        return []

    # always work with a list
    if isinstance(raw, str | bytes | bytearray):
        steps_in = [{"name": str(raw)}]
    elif isinstance(raw, dict):
        steps_in = [raw]
    elif isinstance(raw, list | tuple):
        steps_in = list(raw)
    else:
        raise ValueError("objective.steps must be a list|dict|string")

    def _listify(x):
        if x is None:
            return []
        if isinstance(x, list | tuple | set):
            return list(x)
        return [x]

    out: list[dict] = []
    for i, s in enumerate(steps_in, start=1):
        if isinstance(s, str | bytes | bytearray):
            step = {"name": str(s)}
        elif isinstance(s, dict):
            step = dict(s)
        else:
            raise ValueError(f"step {i} must be str|dict")

        # name required
        name = step.get("name") or step.get("title")
        if not name or not str(name).strip():
            raise ValueError(f"step {i} missing 'name'")

        step["name"] = str(name).strip()

        # targets: tolerate missing/empty; default to repo root
        targets = _listify(step.get("targets"))
        if not targets:
            targets = ["."]
        step["targets"] = targets

        # normalize optional fields
        if "payload" in step and step["payload"] is None:
            step["payload"] = {}
        if "kind" in step and step["kind"] is None:
            step.pop("kind")

        out.append(step)

    return out


# =========================
# Planning
# =========================


def _build_step(
    step_dict: dict[str, Any],
    objective_dict: dict[str, Any],
    objective_obj: Objective,
) -> Step:
    """Constructs a single, typed Step object from its dictionary representation."""
    name = str(step_dict["name"]).strip()

    iterations = step_dict.get("iterations")
    if iterations is not None:
        try:
            iterations = int(iterations)
            if iterations <= 0:
                raise ValueError
        except Exception as e:
            raise ValueError(f"Step '{name}': iterations must be a positive integer") from e

    # Normalize targets into canonical dicts; StepTarget.from_dict will handle extras.
    targets_dicts = _normalize_targets(step_dict.get("targets"))
    tests = _normalize_tests(step_dict, objective_obj)

    # Merge constraints: step-level constraints override objective-level ones.
    step_constraints = objective_obj.constraints
    if "constraints" in step_dict and isinstance(step_dict["constraints"], dict):
        step_constraints = Constraints.from_dict(step_dict["constraints"])

    # Convert dict targets into StepTarget objects if schema expects that
    targets: list[StepTarget] = []
    for t in targets_dicts:
        try:
            # Prefer "file" key; keep backward-compat with "path"
            if "file" not in t and "path" in t:
                t = {**t, "file": t["path"]}
                t.pop("path", None)
            targets.append(StepTarget.from_dict(t))
        except Exception as e:
            raise ValueError(f"Step '{name}': invalid target spec {t!r}") from e

    return Step(
        name=name,
        iterations=iterations,
        targets=targets,
        tests=tests,
        constraints=step_constraints,
        objective=objective_dict,  # raw dict for legacy compatibility
    )


def plan_from_objective(objective_dict: dict[str, Any]) -> Plan:
    """
    Validates and transforms the raw objective dictionary into a typed, executable Plan.
    This is the primary entry point for the planner.
    """
    _require_keys(objective_dict, list(_REQUIRED_TOP_LEVEL), "top-level")

    # Perform validation on the raw dictionary structure
    _validate_acceptance(objective_dict)
    _validate_iterations(objective_dict)

    # Create the canonical Objective object from the dictionary
    objective_obj = Objective.from_dict(objective_dict)

    # Normalize and build the list of Step objects
    steps_raw = _normalize_steps_list(objective_dict)
    steps: list[Step] = [_build_step(s, objective_dict, objective_obj) for s in steps_raw]

    # Sanity check: ensure all step names are unique
    seen_names = set()
    for s in steps:
        if s.name in seen_names:
            raise ValueError(f"Duplicate step name found: '{s.name}'")
        seen_names.add(s.name)

    return Plan(steps=steps)


# =========================
# Utilities
# =========================


def match_tests_in_repo(tests: list[str], repo_root: Path) -> list[Path]:
    """Resolves glob patterns for test files under the repo root, returning unique Paths."""
    matched_paths: list[Path] = []
    if not tests:
        return matched_paths

    for pattern in tests:
        # Normalize to forward slashes for fnmatch, which is more consistent
        normalized_pattern = pattern.replace("\\", "/")
        for p in repo_root.rglob("*"):
            if not p.is_file():
                continue

            # Compare using relative, posix-style paths
            relative_path = str(p.relative_to(repo_root)).replace("\\", "/")
            if fnmatch.fnmatch(relative_path, normalized_pattern):
                matched_paths.append(p)

    # Deduplicate the resolved paths while preserving order
    seen = set()
    unique_paths: list[Path] = []
    for p in matched_paths:
        resolved_path = p.resolve()
        if resolved_path not in seen:
            seen.add(resolved_path)
            unique_paths.append(p)

    return unique_paths


def pretty_plan(plan: Plan) -> str:
    """Generates a human-friendly string representation of the plan for logs."""
    lines: list[str] = []
    for i, s in enumerate(plan.steps, 1):
        lines.append(f"{i}. {s.name} (iters: {s.iterations or 'default'})")

        if s.targets:
            for t in s.targets:
                # StepTarget is expected to expose .file and optionally .export
                export_info = f" :: {t.export}" if getattr(t, "export", None) else ""
                lines.append(f"   - target: {t.file}{export_info}")

        if s.tests:
            if len(s.tests) <= 3:
                for t_path in s.tests:
                    lines.append(f"   - test: {t_path}")
            else:
                shown_tests = ", ".join(s.tests[:3])
                more_count = len(s.tests) - 3
                lines.append(f"   - tests: {shown_tests} (+{more_count} more)")

        if s.constraints and getattr(s.constraints, "python", None):
            lines.append(f"   - python: {s.constraints.python}")

        if s.constraints and getattr(s.constraints, "allowed_new_packages", None):
            packages = ", ".join(s.constraints.allowed_new_packages)
            lines.append(f"   - allowed_new_packages: {packages}")

    return "\n".join(lines)
