from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from core.utils.neo.cypher_query import cypher_query


class Switchboard:
    def __init__(self, ttl_sec: int = 60):
        self.ttl = int(ttl_sec)
        self.cache: dict[str, Any] = {}
        self.expiry: float = 0.0
        self._lock = asyncio.Lock()

    async def _refresh(self, prefix: str | None = None) -> None:
        """
        Refresh the in-memory cache of flags for a given prefix.
        - Uses dynamic property access: properties(f)['value_json'] to avoid
          UnknownPropertyKey warnings before the key exists.
        - WHERE guard tolerates NULL/empty prefix explicitly.
        """
        if self.ttl > 0 and time.time() < self.expiry:
            return

        async with self._lock:
            if self.ttl > 0 and time.time() < self.expiry:
                return

            query = """
            MATCH (f:Flag)
            WHERE $p IS NULL OR $p = '' OR f.key STARTS WITH $p
            RETURN
              f.key AS key,
              coalesce(properties(f)['value_json'], properties(f)['default_json'], 'null') AS vjson
            ORDER BY key
            """
            rows = await cypher_query(query, {"p": prefix or ""}) or []

            # Rebuild only the slice we fetched; keep others in cache if they’re from other prefixes
            # but overwrite any keys we just refreshed.
            for r in rows:
                key = r.get("key")
                vjson = r.get("vjson")
                try:
                    self.cache[key] = json.loads(vjson) if isinstance(vjson, str) else vjson
                except Exception:
                    self.cache[key] = vjson

            self.expiry = time.time() + self.ttl if self.ttl > 0 else 0.0

    async def get(self, key: str, default: Any = None) -> Any:
        # Refresh by namespace (prefix before the first dot), e.g., "synapse."
        prefix = key.split(".", 1)[0] + "." if "." in key else ""
        if self.ttl == 0 or time.time() >= self.expiry:
            await self._refresh(prefix=prefix)
        return self.cache.get(key, default)

    async def get_bool(self, key: str, default: bool = False) -> bool:
        v = await self.get(key, default)
        return bool(v)

    async def get_int(self, key: str, default: int = 0) -> int:
        v = await self.get(key, default)
        try:
            return int(v)
        except Exception:
            return default

    async def get_float(self, key: str, default: float = 0.0) -> float:
        v = await self.get(key, default)
        try:
            return float(v)
        except Exception:
            return default
