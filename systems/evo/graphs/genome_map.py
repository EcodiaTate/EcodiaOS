from __future__ import annotations

import ast
from pathlib import Path

from core.utils.neo.cypher_query import cypher_query


class GenomeMapper:
    """
    Builds a 'genome map' of mutation-sensitive loci:
      - fan-in/out
      - exception density
      - test adjacency (naive heuristic via file names)
    """

    def scan_repo(self, root: str | Path) -> list[dict]:
        root = Path(root)
        out: list[dict] = []
        for py in root.rglob("*.py"):
            try:
                src = py.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(src)
            except Exception:
                continue
            metrics = self._file_metrics(tree, src)
            out.append({"path": str(py), **metrics})
        return out

    def _file_metrics(self, tree: ast.AST, src: str) -> dict:
        calls = sum(isinstance(n, ast.Call) for n in ast.walk(tree))
        defs = sum(
            isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            for n in ast.walk(tree)
        )
        raises = src.count("raise ")
        excepts = sum(isinstance(n, ast.ExceptHandler) for n in ast.walk(tree))
        try_blocks = sum(isinstance(n, ast.Try) for n in ast.walk(tree))
        test_adjacent = int("test" in src.lower())
        return {
            "fan": calls / max(1, defs),
            "exception_density": (raises + excepts) / max(1, defs),
            "def_count": defs,
            "try_blocks": try_blocks,
            "test_adjacent": test_adjacent,
        }

    async def write_to_graph(self, rows: list[dict]) -> int:
        """
        Stores per-file metrics as (:SourceFile) nodes for downstream focus.
        """
        n = 0
        for r in rows:
            q = """
            MERGE (f:SourceFile {path: $p})
            SET f.fan = $fan,
                f.exception_density = $exd,
                f.def_count = $defs,
                f.try_blocks = $trys,
                f.test_adjacent = $tadj,
                f.updated_at = datetime()
            """
            await cypher_query(
                q,
                {
                    "p": r["path"],
                    "fan": float(r["fan"]),
                    "exd": float(r["exception_density"]),
                    "defs": int(r["def_count"]),
                    "trys": int(r["try_blocks"]),
                    "tadj": int(r["test_adjacent"]),
                },
            )
            n += 1
        return n
