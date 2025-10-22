# systems/voxis/core/result_store.py

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

# --- Configuration ---
# This allows us to switch between Redis and in-memory with a single env var.
REDIS_URL = os.getenv("REDIS_URL")
RESULT_TTL_SEC = int(os.getenv("VOXIS_RESULT_TTL_SEC", "900"))  # 15 minutes
logger = logging.getLogger(__name__)


# --- Abstract Interface ---
class AbstractResultStore(ABC):
    """Defines the contract for any result store implementation."""

    @abstractmethod
    async def initialize(self): ...
    @abstractmethod
    async def close(self): ...
    @abstractmethod
    async def get(self, decision_id: str) -> dict[str, Any] | None: ...
    @abstractmethod
    async def put(self, decision_id: str, data: dict[str, Any]): ...
    @abstractmethod
    async def update_field(self, decision_id: str, field: str, value: Any): ...


# --- Production-Ready Redis Implementation ---
class RedisResultStore(AbstractResultStore):
    """A scalable result store backed by Redis, suitable for multi-worker deployments."""

    def __init__(self, url: str, ttl: int):
        self._url = url
        self._ttl = ttl
        self._redis: aioredis.Redis | None = None

    async def initialize(self):
        logger.info(f"Initializing Redis result store connection to {self._url}...")
        try:
            self._redis = aioredis.from_url(self._url, encoding="utf-8", decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connection successful.")
        except Exception:
            logger.exception(
                "Failed to connect to Redis. The application may not function correctly.",
            )
            self._redis = None

    async def close(self):
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed.")

    async def get(self, decision_id: str) -> dict[str, Any] | None:
        if not self._redis:
            return None
        data = await self._redis.get(f"voxis:result:{decision_id}")
        return json.loads(data) if data else None

    async def put(self, decision_id: str, data: dict[str, Any]):
        if not self._redis:
            return
        # Use Redis's built-in TTL for efficient, automatic key expiration.
        await self._redis.set(f"voxis:result:{decision_id}", json.dumps(data), ex=self._ttl)

    async def update_field(self, decision_id: str, field: str, value: Any):
        if not self._redis:
            return
        key = f"voxis:result:{decision_id}"
        # Use a transaction (pipeline) to prevent race conditions when updating.
        async with self._redis.pipeline(transaction=True) as pipe:
            raw_data = await pipe.get(key)
            if raw_data:
                data = json.loads(raw_data)
                data[field] = value
                pipe.set(key, json.dumps(data), ex=self._ttl)
                await pipe.execute()


# --- Developer-Friendly In-Memory Fallback ---
class InMemoryResultStore(AbstractResultStore):
    """A simple, synchronous result store for local development when Redis is not available."""

    def __init__(self, ttl: int):
        self._entries: dict[str, dict[str, Any]] = {}

    async def initialize(self):
        logger.warning(
            "Using IN-MEMORY result store. This is not suitable for production or multi-worker setups.",
        )

    async def close(self):
        pass  # No-op

    async def get(self, decision_id: str) -> dict[str, Any] | None:
        return self._entries.get(decision_id)

    async def put(self, decision_id: str, data: dict[str, Any]):
        self._entries[decision_id] = data

    async def update_field(self, decision_id: str, field: str, value: Any):
        if decision_id in self._entries:
            self._entries[decision_id][field] = value


# --- Singleton Factory ---
# This pattern allows the rest of the application to easily get the configured store
# without worrying about the implementation details.
_store_instance: AbstractResultStore | None = None


def get_result_store() -> AbstractResultStore:
    """Factory function to get the configured result store instance."""
    global _store_instance
    if _store_instance is None:
        if REDIS_URL:
            _store_instance = RedisResultStore(url=REDIS_URL, ttl=RESULT_TTL_SEC)
        else:
            _store_instance = InMemoryResultStore(ttl=RESULT_TTL_SEC)
    return _store_instance
