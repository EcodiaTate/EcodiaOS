# collate.py
import argparse
import os
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = r"D:\EcodiaOS\systems"
DEFAULT_EXTS = [".py"]
DEFAULT_IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
}


def collate_dir(base_dir: Path, out, exts, ignore_dirs):
    if not base_dir.exists():
        out.write(f"\n# ===== MISSING DIRECTORY: {base_dir} =====\n")
        return

    out.write(f"\n# ===== DIRECTORY: {base_dir} =====\n")
    for root, dirs, files in os.walk(base_dir):
        # prune ignored directories (in-place)
        dirs[:] = sorted([d for d in dirs if d not in ignore_dirs])
        files = sorted(files)
        for file in files:
            if Path(file).suffix.lower() not in exts:
                continue
            file_path = Path(root) / file
            out.write(f"\n# ===== FILE: {file_path} =====\n")
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"\n# ERROR reading {file_path}: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Collate code files from one or more EOS systems into a single text file.",
    )
    parser.add_argument(
        "systems",
        nargs="+",
        help="System folder names under the base root (e.g., unity, simula, evo).",
    )
    parser.add_argument(
        "-r",
        "--root",
        default=DEFAULT_ROOT,
        help=f"Base systems root directory (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path. Default: D:\\EcodiaOS\\COLLATED_thread_<systems>.txt",
    )
    parser.add_argument(
        "--ext",
        nargs="*",
        default=DEFAULT_EXTS,
        help=f"File extensions to include (default: {' '.join(DEFAULT_EXTS)})",
    )
    parser.add_argument(
        "--ignore-dirs",
        nargs="*",
        default=sorted(DEFAULT_IGNORE_DIRS),
        help="Directory names to ignore (space-separated).",
    )

    args = parser.parse_args()

    root = Path(args.root)
    systems = [s.strip("\\/") for s in args.systems]
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext}
    ignore_dirs = set(args.ignore_dirs)

    # Default output path: D:\EcodiaOS\COLLATED_thread_<systems>.txt
    if args.output:
        output_path = Path(args.output)
    else:
        # Put in parent of root (i.e., D:\EcodiaOS)
        out_name = f"COLLATED_{'+'.join(systems)}.txt"
        output_path = root.parent / out_name

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out:
        out.write("# ===== EcodiaOS Collation =====\n")
        out.write(f"# Generated: {datetime.now().isoformat(timespec='seconds')}\n")
        out.write(f"# Root: {root}\n")
        out.write(f"# Systems: {', '.join(systems)}\n")
        out.write(f"# Extensions: {', '.join(sorted(exts))}\n")
        out.write(f"# Ignored dirs: {', '.join(sorted(ignore_dirs))}\n")

        for sys_name in systems:
            base_dir = root / sys_name
            collate_dir(base_dir, out, exts, ignore_dirs)

    print(f"Collation complete → {output_path}")


if __name__ == "__main__":
    main()
