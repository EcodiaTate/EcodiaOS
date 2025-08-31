# systems/qora/wm/service.py
# --- PROJECT SENTINEL UPGRADE (Final Corrected with TYPE_CHECKING) ---
from __future__ import annotations

import ast
import json
import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

# --- Optional Dependency Handling for Redis ---
try:
    # Runtime import of the asyncio redis module
    import redis.asyncio as redis_async
except ImportError:
    redis_async = None

# Type-only import so the checker sees a real type without requiring it at runtime
if TYPE_CHECKING:
    from redis.asyncio import Redis as RedisClient

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Blackboard Service (Redis-backed with Pylance-safe typing)
# -----------------------------------------------------------------------------


class BlackboardService:
    """
    A production-ready blackboard service backed by Redis for high-performance,
    scalable, and persistent agent state management.
    """

    # Pylance-safe: refer to the type name only as a string literal (forward reference).
    _client: RedisClient | None = None
    _lock = threading.Lock()

    @classmethod
    def _get_client(cls) -> RedisClient:
        """Initializes and returns a singleton Redis client instance."""
        if cls._client is None:
            with cls._lock:
                if cls._client is None:
                    if redis_async is None:
                        raise RuntimeError(
                            "Redis client is not installed. Please `pip install redis`.",
                        )

                    redis_host = os.getenv("REDIS_HOST", "localhost")
                    redis_port = int(os.getenv("REDIS_PORT", 6379))
                    redis_db = int(os.getenv("REDIS_DB", 0))
                    logger.info(f"Connecting to Redis at {redis_host}:{redis_port}/{redis_db}")
                    try:
                        # Use the runtime module alias to create the client instance.
                        client = redis_async.from_url(
                            f"redis://{redis_host}:{redis_port}/{redis_db}",
                            decode_responses=True,
                        )
                        cls._client = client
                    except Exception as e:
                        logger.critical(f"Failed to connect to Redis: {e}")
                        raise

        # At this point, _client is set; cast for the type checker's benefit.
        return cast("RedisClient", cls._client)

    @classmethod
    async def write(cls, key: str, value: Any) -> bool:
        """Serializes a Python object to JSON and writes it to a Redis key."""
        try:
            client = cls._get_client()
            namespaced_key = f"qora:bb:{key}"
            json_value = json.dumps(value, default=str)
            await client.set(namespaced_key, json_value)
            return True
        except Exception as e:
            logger.exception(f"Blackboard WRITE failed for key '{key}': {e}")
            return False

    @classmethod
    async def read(cls, key: str) -> Any | None:
        """Reads a key from Redis and deserializes its JSON content."""
        try:
            client = cls._get_client()
            namespaced_key = f"qora:bb:{key}"
            json_value = await client.get(namespaced_key)
            if json_value is None:
                return None
            return json.loads(json_value)
        except Exception as e:
            logger.exception(f"Blackboard READ failed for key '{key}': {e}")
            return None


# -----------------------------------------------------------------------------
# World Model Index and Dossier Builder
# -----------------------------------------------------------------------------


class DossierBuilder:
    @staticmethod
    def _split_target(target_fqname: str) -> tuple[str, str | None]:
        if "::" in target_fqname:
            file_part, *rest = target_fqname.split("::")
            return file_part, "::".join(rest)
        return target_fqname, None

    @staticmethod
    def _read_ast(file_path: str) -> tuple[ast.AST | None, str]:
        try:
            text = Path(file_path).read_text(encoding="utf-8")
            return ast.parse(text), text
        except Exception:
            return None, ""

    @staticmethod
    def _collect_imports(tree: ast.AST | None) -> list[str]:
        if not tree:
            return []
        imps: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imps.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                for n in node.names:
                    imps.append(f"{base}.{n.name}" if base else n.name)
        return sorted(set(imps))

    @classmethod
    def dossier(cls, target_fqname: str, intent: str) -> dict[str, Any]:
        file_path, symbol = cls._split_target(target_fqname)
        entry: dict[str, Any] = {
            "meta": {"target_fqname": target_fqname, "intent": intent},
            "files": [],
            "imports": [],
            "related": [],
        }
        if not os.path.exists(file_path):
            return entry

        tree, text = cls._read_ast(file_path)
        imports = cls._collect_imports(tree)
        entry["files"].append({"path": file_path, "size": len(text)})
        entry["imports"] = imports

        related = []
        for f, f_imps in WMIndex.imports.items():
            if f == file_path:
                continue
            if set(f_imps).intersection(imports):
                related.append(
                    {
                        "path": f,
                        "shared_imports": sorted(list(set(f_imps).intersection(imports)))[:8],
                    },
                )
                if len(related) >= 16:
                    break
        entry["related"] = related
        return entry


class WMIndex:
    _lock = threading.RLock()
    files: set[str] = set()
    imports: dict[str, list[str]] = {}

    @classmethod
    def add_file(cls, path: str) -> bool:
        p = Path(path)
        if not p.is_file():
            return False
        with cls._lock:
            cls.files.add(str(p))
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
                cls.imports[str(p)] = DossierBuilder._collect_imports(tree)
            except Exception:
                cls.imports[str(p)] = []
        return True


# -----------------------------------------------------------------------------
# Main Service Façade (Integrated)
# -----------------------------------------------------------------------------


class WMService:
    """The main service façade for all World Model operations."""

    @staticmethod
    async def bb_write(key: str, value: Any) -> bool:
        """Writes to the Redis-backed blackboard."""
        return await BlackboardService.write(key, value)

    @staticmethod
    async def bb_read(key: str) -> Any:
        """Reads from the Redis-backed blackboard."""
        return await BlackboardService.read(key)

    @staticmethod
    def index_file(path: str) -> bool:
        """Adds a file to the in-memory index."""
        return WMIndex.add_file(path)

    @staticmethod
    def dossier(target_fqname: str, intent: str) -> dict[str, Any]:
        """Builds a dossier for a given target."""
        return DossierBuilder.dossier(target_fqname, intent)

    @staticmethod
    def subgraph(fqname: str, hops: int = 1) -> dict[str, Any]:
        """Generates a heuristic subgraph of related files based on shared imports."""
        file_path, _ = DossierBuilder._split_target(fqname)
        center = str(Path(file_path))
        if not os.path.exists(center):
            return {"nodes": [], "edges": []}

        nodes = [{"id": center, "type": "file"}]
        edges = []
        center_imports = set(WMIndex.imports.get(center, []))

        for f, f_imps in WMIndex.imports.items():
            if f == center:
                continue
            if center_imports.intersection(f_imps):
                nodes.append({"id": f, "type": "file"})
                edges.append({"source": center, "target": f, "kind": "shared_imports"})

        return {"nodes": nodes, "edges": []}
