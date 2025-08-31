# systems/qora/core/code_graph/ingestor.py
# --- INCREMENTAL INDEXER (FINAL) ---
from __future__ import annotations

import ast
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Optional ADR front matter support (pip package: python-frontmatter)
try:
    import frontmatter  # import name: frontmatter, package: python-frontmatter
except Exception:
    frontmatter = None  # fallback mode enabled below

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================
VECTOR_DIM = 3072
STD_LIBS = {
    "os", "sys", "json", "re", "asyncio", "collections", "pathlib", "typing",
    "ast", "hashlib", "logging", "codecs", "uuid", "time", "functools", "itertools", "subprocess"
}
ADR_GLOB = "docs/adr/**/*.md"

# Embedding strategy metadata (bump EMBEDDING_VERSION to force a global refresh)
EMBEDDING_VERSION = 1
EMBEDDING_MODEL = "gemini-embedding-001"

# Labels
LABEL_CODE = "Code"
LABEL_CODEFILE = "CodeFile"

# Builtins set for quick external resolution
try:
    import builtins as _builtins_mod  # type: ignore
    BUILTINS = set(dir(_builtins_mod))
except Exception:
    BUILTINS = set()


# =============================================================================
# Helpers
# =============================================================================
def _fqn(path: Path, node: ast.AST | None = None, relative_to: Path = Path(".")) -> str:
    """
    Build a stable FQN: "<rel_path>::<symbol>" or "<rel_path>" for files.
    rel_path uses forward slashes.
    """
    path_str = str(path.relative_to(relative_to)).replace("\\", "/")
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return f"{path_str}::{node.name}"
    return path_str


def _hash_text(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _hash_bytes(b: bytes) -> str:
    return hashlib.blake2b(b, digest_size=16).hexdigest()


def _path_to_module(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root)).replace("\\", "/").replace(".py", "").replace("/", ".")


def _node_source_and_doc(node: ast.AST, source: str) -> tuple[str, str]:
    """
    Extract the exact source slice for a class/function plus its docstring.
    We hash (source + doc) to detect meaningful changes.
    """
    lines = source.splitlines()
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", start + 1)
    snippet = "\n".join(lines[start:end])
    doc = ast.get_docstring(node) or ""
    return snippet, doc


# =============================================================================
# Git integration (optional; fall back to full scan)
# =============================================================================
async def _get_last_commit_from_graph() -> str | None:
    rows = await cypher_query(
        "MATCH (s:IngestState {id:'default'}) RETURN s.last_commit AS last LIMIT 1"
    )
    return rows[0]["last"] if rows and rows[0].get("last") else None


async def _set_last_commit_in_graph(commit: str) -> None:
    await cypher_query(
        "MERGE (s:IngestState {id:'default'}) "
        "SET s.last_commit = $c, s.updated_at = timestamp()",
        {"c": commit},
    )


def _git_head(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root)
        ).decode().strip()
    except Exception:
        return None


def _git_changed_py(repo_root: Path, since_commit: str) -> list[Path]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{since_commit}..HEAD", "--", "*.py"],
            cwd=str(repo_root),
        ).decode()
        return [repo_root / p for p in out.splitlines() if p.strip()]
    except Exception:
        return []


def _all_py_files(repo_root: Path) -> list[Path]:
    return [
        p
        for p in repo_root.rglob("*.py")
        if not any(d in p.parts for d in (".git", ".venv", "__pycache__", "node_modules"))
    ]


# =============================================================================
# ADR loader (frontmatter optional with safe fallback)
# =============================================================================
class _Post:
    def __init__(self, metadata: Dict[str, Any], content: str):
        self.metadata = metadata or {}
        self.content = content or ""


def _load_adr_file(adr_path: Path) -> _Post:
    """Load ADR file using python-frontmatter if available, else a minimal YAML-front matter fallback."""
    if frontmatter is not None:
        try:
            fm = frontmatter.load(adr_path)
            return _Post(fm.metadata or {}, fm.content or "")
        except Exception as e:
            logger.warning("frontmatter failed on %s; falling back. err=%s", adr_path, e)

    # Fallback: parse naive YAML block between leading '---' ... '---'
    text = adr_path.read_text(encoding="utf-8", errors="replace")
    meta: Dict[str, Any] = {}
    content = text

    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
            fm_text = "\n".join(lines[1:end])
            content = "\n".join(lines[end + 1 :])
            try:
                import yaml  # optional
                meta = yaml.safe_load(fm_text) or {}
            except Exception:
                meta = {}
        except StopIteration:
            # no closing '---' -> treat whole file as content
            pass

    if frontmatter is None:
        logger.warning(
            "ADR parsing running in fallback mode (install python-frontmatter for full support): %s",
            adr_path,
        )
    return _Post(meta, content)


# =============================================================================
# Symbol Resolver
# =============================================================================
class SymbolResolver:
    """
    Resolve an identifier to either:
      - internal symbol FQN ('internal_symbol')
      - internal module file path ('internal_module')  (maps to CodeFile.path)
      - external ('external')
      - unknown ('unknown')
    """

    def __init__(self, current_file_info: Dict, all_files_cache: Dict[str, Dict[str, Any]], module_to_file_path: Dict[str, str]):
        self.current_file_info = current_file_info
        self.all_files_cache = all_files_cache
        self.module_to_file_path = module_to_file_path
        self.local_symbols = {name: fqn for name, fqn in current_file_info.get("defines", {}).items()}

    def resolve(self, name: str) -> Tuple[str | None, str]:
        # Local define in this file
        if name in self.local_symbols:
            return self.local_symbols[name], "internal_symbol"

        # Imported alias
        if name in self.current_file_info["imports"]:
            full_import = self.current_file_info["imports"][name]

            # (a) Direct module mapping
            if full_import in self.module_to_file_path:
                return self.module_to_file_path[full_import], "internal_module"

            # (b) module.symbol where module part is internal file, symbol in its defines
            parts = full_import.split(".")
            if len(parts) > 1:
                module_part = ".".join(parts[:-1])
                symbol_part = parts[-1]
                file_path = self.module_to_file_path.get(module_part)
                if file_path:
                    target_file_info = self.all_files_cache.get(file_path)
                    if target_file_info and symbol_part in target_file_info.get("defines", {}):
                        return target_file_info["defines"][symbol_part], "internal_symbol"

            # (c) External library (first segment as package name)
            return full_import.split(".")[0], "external"

        # Builtins count as external (we won't create edges for them)
        if name in BUILTINS:
            return name, "external"

        return None, "unknown"


# =============================================================================
# Pass 1: Upsert CodeFile + Code symbols (with embedding hash-gate)
# =============================================================================
async def _pass_one_create_nodes(
    file_path: Path,
    repo_root: Path,
    file_cache: Dict[str, Dict[str, Any]],
    *,
    force: bool = False,
) -> int:
    """
    Upserts CodeFile + its Code symbols.
    Re-embeds a symbol only if its content hash changed or embedding version changed (unless force=True).
    """
    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code)
    except Exception:
        return 0

    rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
    file_module = _path_to_module(file_path, repo_root)
    file_hash = _hash_text(source_code)

    # Upsert CodeFile by path (keep fqn for backward compatibility)
    await cypher_query(
        f"MERGE (f:{LABEL_CODEFILE} {{path:$path}}) "
        "SET f.module=$module, f.hash=$hash, f.fqn=coalesce(f.fqn,$path), f.updated_at=timestamp()",
        {"path": rel_path, "module": file_module, "hash": file_hash},
    )

    # Preload existing symbols for this file: content_hash + embedding_version
    existing = await cypher_query(
        """
        MATCH (:CodeFile {path:$path})-[:DEFINES]->(c:Code)
        RETURN c.fqn AS fqn, c.content_hash AS content_hash, coalesce(c.embedding_version,0) AS v
        """,
        {"path": rel_path},
    )
    existing_map = {row["fqn"]: (row["content_hash"], int(row["v"])) for row in existing}

    # Prepare cache structure for pass-2
    file_info: Dict[str, Any] = {
        "path": rel_path,
        "module": file_module,
        "imports": {},
        "defines": {},
        "class_bases": {},
        "function_calls": {},
        "type_hints": {},
    }
    file_cache[rel_path] = file_info

    nodes_upserted = 0

    # Collect imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                file_info["imports"][alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                file_info["imports"][alias.asname or alias.name] = f"{node.module}.{alias.name}"

    # Ensure child->parent links for call collection
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)  # type: ignore

    async def _upsert_symbol(node: ast.AST, kind: str) -> None:
        nonlocal nodes_upserted
        node_fqn = _fqn(file_path, node, relative_to=repo_root)
        src, doc = _node_source_and_doc(node, source_code)
        content_hash = _hash_bytes((src + "\n\n" + doc).encode("utf-8"))

        have = existing_map.get(node_fqn)
        needs_embed = force or (not have) or (have[0] != content_hash) or (have[1] != EMBEDDING_VERSION)

        params = {
            "fqn": node_fqn,
            "name": getattr(node, "name", node_fqn.split("::")[-1]),
            "path": rel_path,
            "doc": doc,
            "src": src,
            "content_hash": content_hash,
            "embed_version": EMBEDDING_VERSION,
            "embed_model": EMBEDDING_MODEL,
        }

        if needs_embed:
            emb = None
            try:
                emb = await get_embedding(src + ("\n\n" + doc if doc else ""), dimensions=VECTOR_DIM)
            except Exception:
                emb = None
            params["embedding"] = emb

        set_embedding_clause = ", c.embedding=$embedding" if needs_embed else ""
        query = (
            f"MERGE (c:{LABEL_CODE} {{fqn:$fqn}}) "
            "SET c.name=$name, c.path=$path, c.docstring=$doc, c.source_code=$src, "
            "    c.content_hash=$content_hash, c.embedding_version=$embed_version, c.embedding_model=$embed_model, "
            "    c.updated_at=timestamp()"
            f"{set_embedding_clause} "
            "WITH c "
            f"MATCH (f:{LABEL_CODEFILE} {{path:$path}}) "
            "MERGE (f)-[:DEFINES]->(c)"
        )
        _ = await cypher_query(query, params)
        nodes_upserted += 1

    # Walk top-level defs to capture bases, calls, types
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            file_info["defines"][n.name] = _fqn(file_path, n, relative_to=repo_root)
            await _upsert_symbol(n, "ClassDef")
            # Bases
            bases = []
            for b in n.bases:
                try:
                    bases.append(ast.unparse(b))
                except Exception:
                    pass
            file_info["class_bases"][file_info["defines"][n.name]] = bases

        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            file_info["defines"][n.name] = _fqn(file_path, n, relative_to=repo_root)
            await _upsert_symbol(n, "FunctionDef")

            # Calls (best-effort)
            calls: set[str] = set()
            for sub in ast.walk(n):
                if isinstance(sub, ast.Call):
                    try:
                        calls.add(ast.unparse(sub.func))
                    except Exception:
                        pass
            file_info["function_calls"][file_info["defines"][n.name]] = calls

            # Type hints
            hints: set[str] = set()
            try:
                for arg in getattr(n.args, "args", []):
                    if getattr(arg, "annotation", None) is not None:
                        hints.add(ast.unparse(arg.annotation))
                if getattr(n.args, "posonlyargs", None):
                    for arg in n.args.posonlyargs:
                        if getattr(arg, "annotation", None) is not None:
                            hints.add(ast.unparse(arg.annotation))
                if getattr(n.args, "kwonlyargs", None):
                    for arg in n.args.kwonlyargs:
                        if getattr(arg, "annotation", None) is not None:
                            hints.add(ast.unparse(arg.annotation))
                if getattr(n, "returns", None) is not None:
                    hints.add(ast.unparse(n.returns))
            except Exception:
                pass
            file_info["type_hints"][file_info["defines"][n.name]] = hints

    return nodes_upserted


# =============================================================================
# Pass 2: Relationships (clear & rebuild for touched files)
# =============================================================================
async def _clear_outgoing_rels_for_file(rel_path: str) -> None:
    # Remove file-level IMPORTS and symbol-level rels for this file
    await cypher_query(
        f"""
        MATCH (f:{LABEL_CODEFILE} {{path:$path}})
        OPTIONAL MATCH (f)-[r1:IMPORTS]->() DELETE r1
        WITH f
        MATCH (f)-[:DEFINES]->(c:{LABEL_CODE})
        OPTIONAL MATCH (c)-[r:CALLS|INHERITS_FROM|USES_TYPE]->() DELETE r
        """,
        {"path": rel_path},
    )


async def _pass_two_create_relationships(
    file_key: str,  # rel_path string used as key in file_cache
    file_cache: Dict[str, Dict[str, Any]],
    module_to_file_path: Dict[str, str],
) -> int:
    file_info = file_cache[file_key]
    resolver = SymbolResolver(file_info, file_cache, module_to_file_path)
    rels_created = 0

    # IMPORTS (file -> file or file -> Library)
    for alias, full_import in file_info["imports"].items():
        target, kind = resolver.resolve(alias)
        if kind == "internal_module" and target:
            # CodeFile -> CodeFile
            await cypher_query(
                f"""
                MATCH (src:{LABEL_CODEFILE} {{path:$src}}), (dst:{LABEL_CODEFILE} {{path:$dst}})
                MERGE (src)-[:IMPORTS]->(dst)
                """,
                {"src": file_info["path"], "dst": target},
            )
            rels_created += 1
        elif kind == "external" and target and target not in STD_LIBS:
            await cypher_query("MERGE (l:Library {name:$name})", {"name": target})
            await cypher_query(
                f"""
                MATCH (src:{LABEL_CODEFILE} {{path:$src}}), (l:Library {{name:$name}})
                MERGE (src)-[:IMPORTS]->(l)
                """,
                {"src": file_info["path"], "name": target},
            )
            rels_created += 1

    # INHERITS_FROM (class -> base class)
    for class_fqn, base_names in file_info.get("class_bases", {}).items():
        for base in base_names:
            target, kind = resolver.resolve(base)
            if target and kind == "internal_symbol":
                await cypher_query(
                    f"""
                    MATCH (src:{LABEL_CODE} {{fqn:$src}}), (dst:{LABEL_CODE} {{fqn:$dst}})
                    MERGE (src)-[:INHERITS_FROM]->(dst)
                    """,
                    {"src": class_fqn, "dst": target},
                )
                rels_created += 1

    # CALLS (func -> func)
    for func_fqn, call_names in file_info.get("function_calls", {}).items():
        for call_name in call_names:
            target, kind = resolver.resolve(call_name)
            if target and kind == "internal_symbol":
                await cypher_query(
                    f"""
                    MATCH (src:{LABEL_CODE} {{fqn:$src}}), (dst:{LABEL_CODE} {{fqn:$dst}})
                    MERGE (src)-[:CALLS]->(dst)
                    """,
                    {"src": func_fqn, "dst": target},
                )
                rels_created += 1

    # USES_TYPE (func -> type symbol)
    for func_fqn, hint_names in file_info.get("type_hints", {}).items():
        for hint in hint_names:
            target, kind = resolver.resolve(hint)
            if target and kind == "internal_symbol":
                await cypher_query(
                    f"""
                    MATCH (src:{LABEL_CODE} {{fqn:$src}}), (dst:{LABEL_CODE} {{fqn:$dst}})
                    MERGE (src)-[:USES_TYPE]->(dst)
                    """,
                    {"src": func_fqn, "dst": target},
                )
                rels_created += 1

    return rels_created


# =============================================================================
# Pass 3: ADR ingest (incremental)
# =============================================================================
async def _pass_three_ingest_adrs_incremental(repo_root: Path, *, force: bool = False) -> int:
    nodes_upserted = 0
    for adr_path in repo_root.glob(ADR_GLOB):
        try:
            post = _load_adr_file(adr_path)

            title = (post.metadata.get("title") or adr_path.stem)
            status = post.metadata.get("status", "unknown")
            related_paths = post.metadata.get("related_code", []) or []

            rel_path = str(adr_path.relative_to(repo_root)).replace("\\", "/")
            content = post.content
            content_hash = _hash_text(f"{content}\n\n{title}\n{status}")

            # Check existing hash/version
            have = await cypher_query(
                """
                MATCH (a:ArchitecturalDecision {path:$path})
                RETURN a.content_hash AS h, coalesce(a.embedding_version,0) AS v
                """,
                {"path": rel_path},
            )
            have_hash = have[0]["h"] if have else None
            have_ver = int(have[0]["v"]) if have and have[0].get("v") is not None else 0

            needs_embed = force or (have_hash != content_hash) or (have_ver != EMBEDDING_VERSION)

            params = {
                "path": rel_path,
                "title": title,
                "status": status,
                "content": content,
                "content_hash": content_hash,
                "embed_version": EMBEDDING_VERSION,
                "embed_model": EMBEDDING_MODEL,
            }
            if needs_embed:
                emb = None
                try:
                    emb = await get_embedding(f"ADR: {title}\nStatus: {status}\n\n{content}", dimensions=VECTOR_DIM)
                except Exception:
                    emb = None
                params["embedding"] = emb

            set_emb = ", a.embedding=$embedding" if needs_embed else ""
            await cypher_query(
                f"""
                MERGE (a:ArchitecturalDecision {{path:$path}})
                SET a.title=$title, a.status=$status, a.content=$content,
                    a.content_hash=$content_hash, a.embedding_version=$embed_version,
                    a.embedding_model=$embed_model, a.updated_at=timestamp(){set_emb}
                """,
                params,
            )
            nodes_upserted += 1

            # Link ADR -> CodeFile for any declared related paths
            if related_paths:
                await cypher_query(
                    f"""
                    UNWIND $rels AS code_path
                    MATCH (a:ArchitecturalDecision {{path:$adr}}), (c:{LABEL_CODEFILE} {{path: code_path}})
                    MERGE (a)-[:DOCUMENTS]->(c)
                    """,
                    {"adr": rel_path, "rels": related_paths},
                )

        except Exception as e:
            logger.exception("ADR ingest failed for %s: %s", adr_path, e)
            continue
    return nodes_upserted


# =============================================================================
# Orchestrator
# =============================================================================
async def patrol_and_ingest(
    root_dir: str = ".",
    *,
    force: bool = False,
    changed_only: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Main entry point.
    - If Git available and changed_only=True, only process files changed since last successful run.
    - Within each changed file, only re-embed symbols whose content changed (or embedding version bumped).
    - Relationships are rebuilt only for touched files.
    """
    repo_root = Path(root_dir).resolve()

    # Ensure indices/constraints
    from .schema import ensure_all_graph_indices
    try:
        await ensure_all_graph_indices()
    except Exception:
        pass

    total_nodes, total_rels, adr_nodes = 0, 0, 0
    files_processed = 0

    head = _git_head(repo_root)
    last = await _get_last_commit_from_graph() if head else None

    if force or not changed_only or not head or not last:
        candidates = _all_py_files(repo_root)
    else:
        diffed = _git_changed_py(repo_root, last)
        candidates = diffed if diffed else _all_py_files(repo_root)

    # PASS 1: upsert nodes for candidate files
    file_cache: Dict[str, Dict[str, Any]] = {}
    for file_path in candidates:
        up = await _pass_one_create_nodes(file_path, repo_root, file_cache, force=force)
        if up > 0:
            total_nodes += up
            files_processed += 1

    # PASS 2: clear/rebuild relationships only for files we touched
    module_to_file_path = {info["module"]: key for key, info in file_cache.items()}
    for file_key in file_cache.keys():
        await _clear_outgoing_rels_for_file(file_key)
        rels = await _pass_two_create_relationships(file_key, file_cache, module_to_file_path)
        total_rels += rels

    # PASS 3: ADRs (incremental)
    adr_nodes = await _pass_three_ingest_adrs_incremental(repo_root, force=force)
    total_nodes += adr_nodes

    if head and not dry_run:
        await _set_last_commit_in_graph(head)

    return {
        "ok": True,
        "files_processed": files_processed,
        "nodes_upserted": total_nodes,
        "rels_created": total_rels,
        "adrs_ingested": adr_nodes,
        "mode": "force_full" if force else ("changed_only" if changed_only else "full_scan"),
        "head": head,
        "since": last,
    }
