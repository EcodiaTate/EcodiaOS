#!/usr/bin/env python3
"""
Collect files with placeholder-like phrasing and collate their full contents
into a single Markdown "fix plan" file.

Default root: D:\\EcodiaOS\\systems
Default output: placeholder_fix_plan.md (written to the root directory)

Usage:
    python collect_placeholders.py
    python collect_placeholders.py --root "D:\\EcodiaOS\\systems" --out "D:\\EcodiaOS\\systems\\placeholder_fix_plan.md"
    python collect_placeholders.py --dry-run  # shows what would be included without writing the file
"""

import argparse
import datetime as dt
import os
import re
from collections.abc import Iterable
from pathlib import Path

# --- Default configuration ---
DEFAULT_ROOT = r"D:\EcodiaOS\systems"
DEFAULT_OUT = None  # if None, write "placeholder_fix_plan.md" inside root
# Directories to skip during walk:
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
}

# File extensions we consider "texty" by default (lowercased, include the dot)
TEXT_EXTS = {
    ".py",
    ".pyi",
    ".txt",
    ".md",
    ".rst",
    ".json",
    ".jsonl",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".bat",
    ".ps1",
    ".cmd",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".sql",
    ".cypher",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".hpp",
    ".cpp",
    ".cc",
    ".dockerfile",
    ".env",
    ".service",
}

# Phrases to detect (case-insensitive). Use careful regex with word boundaries where helpful.
PLACEHOLDER_PATTERNS = [
    r"\bplaceholder\b",
    r"\bfor\s+now\b",
    r"\bin\s+a\s+real\b",  # e.g. "In a real system..."
    r"\bnot\s+production\b",
    r"\btemporary\b",
    r"\btemp\s+hack\b|\bhack(y)?\b|\bquick\s+and\s+dirty\b",
    r"\bworkaround\b",
    r"\bTODO\b|\bTBD\b|\bFIXME\b|\bWIP\b",
    r"\bnot\s+ideal\b|\bnot\s+robust\b",
    r"\bstub\b|\bmock\b",
    r"\bhard-?coded\b|\bhardcoded\b",
    r"\brefactor\b",  # can be noisy, but useful for hunting tech debt
    r"\blater\b|\bwe'?ll\s+do\s+this\s+later\b",
    r"\bassume(d)?\s+.*for\s+now\b",
    r"\bedge\s+case(s)?\s+ignored\b",
    r"\bshould\s+be\s+fine\b",
    r"\bplaceholder\s+value\b|\bplaceholder\s+impl(ementation)?\b",
]

COMPILED_RE = re.compile("|".join(f"({p})" for p in PLACEHOLDER_PATTERNS), re.IGNORECASE)


def is_texty(path: Path) -> bool:
    # Treat files with known text extensions as text; ignore others to avoid binary junk.
    # If the file has no extension, we’ll still try to read small ones as text below.
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return True
    # Heuristic fallback: treat extensionless scripts and small files as text candidates
    if ext == "" and path.stat().st_size <= 2 * 1024 * 1024:
        return True
    return False


def iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip noisy/irrelevant dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            yield p


def read_text_safely(p: Path) -> str:
    # Try utf-8, then latin-1; ignore errors to avoid crashes on mixed-encoding repos.
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        try:
            return p.read_text(encoding="latin-1", errors="ignore")
        except Exception:
            return ""


def find_matches(text: str) -> list[str]:
    # Return the unique phrases that matched (best-effort labeling by pattern)
    matches = []
    for m in COMPILED_RE.finditer(text):
        span = m.group(0).strip()
        if span and span.lower() not in {s.lower() for s in matches}:
            matches.append(span)
    return matches


def scan(root: Path) -> list[tuple[Path, list[str]]]:
    results = []
    for p in iter_files(root):
        if not p.is_file():
            continue
        if not is_texty(p):
            continue
        text = read_text_safely(p)
        if not text:
            continue
        hits = find_matches(text)
        if hits:
            results.append((p, hits))

    # Sort for stability: first by extension weight (code > docs), then by path
    def weight(path: Path) -> int:
        # Lower weight means earlier
        ext = path.suffix.lower()
        if ext in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c", ".h"}:
            return 0
        if ext in {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".env"}:
            return 1
        return 2

    results.sort(key=lambda t: (weight(t[0]), str(t[0]).lower()))
    return results


def write_report(root: Path, out_path: Path, hits: list[tuple[Path, list[str]]]) -> None:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append(f"# Placeholder Fix Plan")
    lines.append("")
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Root:** `{root}`")
    lines.append(f"- **Files flagged:** {len(hits)}")
    lines.append("")
    lines.append("## Detection patterns")
    lines.append("")
    lines.append("The following case-insensitive regex patterns were used:")
    for p in PLACEHOLDER_PATTERNS:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for idx, (path, phrases) in enumerate(hits, 1):
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        text = read_text_safely(path)
        # Sanity clamp to avoid exploding the file size in extreme cases
        # (You can raise this if you want the *entire* file no matter what.)
        if len(text) > 2_000_000:
            text_body = text[:2_000_000] + "\n\n# [Truncated due to size]\n"
        else:
            text_body = text

        lines.append(f"## {idx}. `{rel}`")
        lines.append("")
        lines.append(f"- **Absolute path:** `{path}`")
        lines.append(f"- **Match count (unique spans):** {len(phrases)}")
        # Show unique matched snippets (not all occurrences) to guide what to fix
        for ph in phrases:
            lines.append(f"  - `{ph}`")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary><strong>Full file contents</strong></summary>\n")
        # Use fenced code block without specifying language to preserve raw text
        lines.append("```")
        lines.append(text_body)
        lines.append("```")
        lines.append("\n</details>\n")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Collate files with placeholder-ish content into a fix plan.",
    )
    ap.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help="Root directory to scan (default: D:\\EcodiaOS\\systems)",
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output Markdown path. Default: <root>/placeholder_fix_plan.md",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be included without writing the file",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Root does not exist or is not a directory: {root}")

    out_path = Path(args.out).resolve() if args.out else (root / "placeholder_fix_plan.md")

    hits = scan(root)

    if args.dry_run:
        print(f"[DRY RUN] Would include {len(hits)} files:")
        for p, phrases in hits:
            rel = p.relative_to(root) if p.is_relative_to(root) else p
            print(f" - {rel}  ({len(phrases)} unique match spans)")
        return

    write_report(root, out_path, hits)
    print(f"Wrote placeholder fix plan to: {out_path}")


if __name__ == "__main__":
    main()
