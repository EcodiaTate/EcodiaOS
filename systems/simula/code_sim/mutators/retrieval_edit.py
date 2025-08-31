# systems/simula/code_sim/mutators/retrieval_edit.py
from __future__ import annotations

import difflib
import logging
import os
import re
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

REPO_ROOT = Path(os.environ.get("SIMULA_REPO_ROOT", "/workspace")).resolve()


def _unidiff(old: str, new: str, rel: str) -> str:
    """Generate a unified diff between old and new text."""
    a = old.splitlines(True)
    b = new.splitlines(True)
    return "".join(difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm=""))


def _read(path: Path) -> str:
    """Read file content as utf-8; return empty string on failure (caller decides create vs. modify)."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.debug("read failed for %s: %s", path, e)
        return ""


def _ensure_line(src: str, needle: str) -> tuple[str, bool]:
    """Ensure an exact line exists in src; returns (updated_text, changed?)."""
    # Exact match across lines to avoid partial substrings
    lines = src.splitlines()
    if any(line.strip() == needle.strip() for line in lines):
        return src, False
    if not src.endswith("\n"):
        src += "\n"
    return src + needle.rstrip("\n") + "\n", True


def _detect_registry_path() -> Path:
    """Return the most plausible registry module path; if none exist, choose canonical location to create."""
    candidates = [
        REPO_ROOT / "systems" / "synk" / "core" / "tools" / "registry.py",
        REPO_ROOT / "systems" / "feature" / "tool.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Prefer synk registry as canonical creation target
    return candidates[0]


# ---------- Public entry ----------


def retrieval_guided_edits(
    step,
    mode: Literal["registry", "config", "prior_art", "tests"],
) -> str | None:
    """
    Apply deterministic retrieval-guided edits:
      - "registry": ensure tools required by acceptance.contracts.must_register are registered.
      - "config": ensure pyproject.toml contains formatter/linter config blocks.
      - "prior_art": create a missing module/function with a concrete, safe body and logging.
      - "tests": create a smoke test that imports target module and asserts function presence.
    Returns a unified diff string or None if no change is needed.
    """

    if mode == "registry":
        # Extract tool names from acceptance contracts (strings or dicts).
        acc = (step.objective or {}).get("acceptance", {})
        regs = acc.get("contracts", {}).get("must_register", []) or []

        tool_names: list[str] = []
        for r in regs:
            s = str(r)
            # Accept patterns like "tool 'name'" or {"tool": "name"} or plain "name"
            m = re.search(r"tool\s*['\"]([^'\"]+)['\"]", s)
            if m:
                tool_names.append(m.group(1).strip())
                continue
            m2 = re.search(r"'tool'\s*:\s*['\"]([^'\"]+)['\"]", s)
            if m2:
                tool_names.append(m2.group(1).strip())
                continue
            # Last resort: a clean token without spaces
            token = s.strip()
            if token and " " not in token and ":" not in token:
                tool_names.append(token)

        tool_names = sorted({t for t in tool_names if t})

        if not tool_names:
            return None

        reg_path = _detect_registry_path()
        old = _read(reg_path)

        # Ensure module has a register_tool symbol or create a minimal registry.
        new = old or (
            "# Auto-created tool registry\n"
            "from __future__ import annotations\n"
            "from typing import Dict, Any\n\n"
            "_REGISTRY: Dict[str, Dict[str, Any]] = {}\n\n"
            "def register_tool(name: str, metadata: Dict[str, Any] | None = None) -> None:\n"
            "    _REGISTRY[name] = dict(metadata or {})\n\n"
            "def has_tool(name: str) -> bool:\n"
            "    return name in _REGISTRY\n"
        )

        changed = False
        for name in tool_names:
            # Avoid false positives by searching for exact call pattern
            if re.search(rf"register_tool\(\s*['\"]{re.escape(name)}['\"]", new):
                continue
            new, did = _ensure_line(new, f"register_tool('{name}', metadata={{}})")
            changed = changed or did

        if not changed:
            return None
        return _unidiff(old, new, str(reg_path.relative_to(REPO_ROOT)))

    if mode == "config":
        p = REPO_ROOT / "pyproject.toml"
        old = _read(p)
        if not old:
            return None

        new = old
        blocks: list[str] = []

        if "[tool.ruff]" not in new:
            blocks.append("\n[tool.ruff]\nline-length = 100\n")
        if "[tool.isort]" not in new:
            blocks.append('\n[tool.isort]\nprofile = "black"\n')
        if "[tool.black]" not in new:
            blocks.append("\n[tool.black]\nline-length = 100\n")
        if "[tool.mypy]" not in new:
            blocks.append("\n[tool.mypy]\nignore_missing_imports = true\nstrict_optional = true\n")

        if not blocks:
            return None

        # Ensure single trailing newline
        if not new.endswith("\n"):
            new += "\n"
        new += "".join(blocks)
        return _unidiff(old, new, str(p.relative_to(REPO_ROOT)))

    if mode == "prior_art":
        # Create a missing module/function with a concrete, side-effect-free body.
        rel, sig = step.primary_target()
        if not rel:
            return None
        p = REPO_ROOT / rel
        if p.exists():
            return None

        old = ""
        header = f'"""Autogenerated scaffold for {rel} (Simula retrieval-guided)."""\n'
        body = (
            "from __future__ import annotations\n"
            "import logging\n"
            "from typing import Any\n"
            "logger = logging.getLogger(__name__)\n\n"
        )
        if sig:
            name = sig.split("(", 1)[0].strip()
            body += f"def {sig}:\n"
            body += f"    logger.info('{name} invoked')\n"
            body += "    # Return a deterministic neutral value to keep the system runnable\n"
            body += "    return None\n"
        new = header + body
        return _unidiff(old, new, rel)

    if mode == "tests":
        tests = step.match_tests(REPO_ROOT)
        write_targets = [t for t in tests if not t.exists()]
        if not write_targets:
            return None

        rel = str(write_targets[0].relative_to(REPO_ROOT))
        old = ""
        tgt_file, sig = step.primary_target()
        mod_path = tgt_file.replace("/", ".").rstrip(".py")
        fn_name = sig.split("(", 1)[0].strip() if sig else None

        content = [
            "import importlib",
            "",
            "def test_import_target():",
            f"    m = importlib.import_module('{mod_path}')",
        ]
        if fn_name:
            content.append(f"    assert hasattr(m, '{fn_name}')")
        content.append("")  # trailing newline
        new = "\n".join(content)
        return _unidiff(old, new, rel)

    return None
