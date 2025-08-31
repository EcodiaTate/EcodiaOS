# py cite_clean.py "D:\EcodiaOS\systems\synapse" --write

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Match exactly the bracketed tokens, no surrounding whitespace:
#
#
#
#
CITE_TOKEN = re.compile(
    r"""\[(?:cite_start|cite\s*:\s*[\d,\s]+)\]""",
    re.IGNORECASE | re.VERBOSE,
)


def strip_cites_token_only(text: str) -> tuple[str, int]:
    new_text, n = CITE_TOKEN.subn("", text)
    return new_text, n


def process_file(path: Path, write: bool, make_backup: bool) -> int:
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0

    new_text, n = strip_cites_token_only(original)
    if n > 0 and write:
        if make_backup:
            try:
                path.with_suffix(path.suffix + ".bak").write_text(
                    original,
                    encoding="utf-8",
                    errors="ignore",
                )
            except Exception:
                pass
        try:
            path.write_text(new_text, encoding="utf-8", errors="ignore")
        except Exception:
            return 0
    return n


def main():
    p = argparse.ArgumentParser(
        description="Safely remove  and [cite: ...] tokens without touching surrounding whitespace.",
    )
    p.add_argument("root", help=r"Root dir, e.g. D:\EcodiaOS\systems\synapse")
    p.add_argument(
        "-e",
        "--ext",
        action="append",
        default=[".py"],
        help="File extension to include (repeatable). Default: .py",
    )
    p.add_argument("--write", action="store_true", help="Apply changes (default: dry-run).")
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create .bak files when writing.",
    )
    args = p.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"[!] Not a directory: {root}")
        return

    wanted_exts = {ext.lower() if ext.startswith(".") else "." + ext.lower() for ext in args.ext}
    total_files = 0
    total_hits = 0

    for pth in root.rglob("*"):
        if not pth.is_file():
            continue
        if pth.suffix.lower() in wanted_exts:
            hits = process_file(pth, write=args.write, make_backup=not args.no_backup)
            if hits > 0:
                print(f"{'CLEAN' if args.write else 'FOUND'} {hits:>3} : {pth}")
                total_files += 1
                total_hits += hits

    mode = "dry-run" if not args.write else "in-place"
    print(f"\nDone ({mode}). Files touched: {total_files}, tokens removed: {total_hits}")


if __name__ == "__main__":
    main()
