# core/utils/events/bus.py

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Dict, List

import redis.asyncio as aioredis
from redis.exceptions import ResponseError  # <- redis-py 5.x exceptions live here

log = logging.getLogger(__name__)
Callback = Callable[[Any], Any]


class EventBus:
    """
    [MDO-UPGRADE] A hybrid, Redis-backed, async-friendly pub/sub bus (singleton).
    - Retains the simple Python API and in-memory speed for local subscribers.
    - Uses Redis Streams as a robust backbone for inter-service communication.
    - Any event published on one service is broadcast to all other services.
    """

    _instance: EventBus | None = None

    _subscribers: dict[str, list[Callback]]
    _lock: asyncio.Lock
    _redis_client: aioredis.Redis
    _stream_key: str
    _consumer_group: str
    _consumer_name: str
    _redis_listener_task: asyncio.Task | None
    _running: bool

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

            # In-memory components
            cls._instance._subscribers = defaultdict(list)
            cls._instance._lock = asyncio.Lock()

            # Redis components for inter-service communication
            cls._instance._redis_client = aioredis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379/0"),
            )
            cls._instance._stream_key = "mdo:event_stream"
            cls._instance._consumer_group = "mdo_bus_group"
            cls._instance._consumer_name = f"consumer_{os.getpid()}"
            cls._instance._redis_listener_task = None
            cls._instance._running = True

            # Try to start the listener immediately if a loop exists; otherwise defer.
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(cls._instance._start_redis_listener())
            except RuntimeError:
                log.info("[EventBus] Deferring Redis listener start until app lifespan.")

        return cls._instance

    async def start(self):
        """Idempotent starter for the Redis listener."""
        if self._redis_listener_task and not self._redis_listener_task.done():
            return
        await self._start_redis_listener()

    async def _start_redis_listener(self):
        """Initializes the Redis consumer group and starts the listener loop."""
        try:
            await self._redis_client.xgroup_create(
                self._stream_key,
                self._consumer_group,
                id="0",
                mkstream=True,
            )
            log.info(
                f"[EventBus] Ensured Redis consumer group '{self._consumer_group}' exists for stream '{self._stream_key}'.",
            )
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                log.error(f"[EventBus] Failed to create Redis consumer group: {e!r}")
                return

        self._redis_listener_task = asyncio.create_task(self._redis_listener_loop())

    async def _redis_listener_loop(self):
        """The core loop that listens for events from other services via Redis."""
        log.info(f"[EventBus] Redis listener started. Consumer: {self._consumer_name}")
        while self._running:
            try:
                events = await self._redis_client.xreadgroup(
                    self._consumer_group,
                    self._consumer_name,
                    {self._stream_key: ">"},
                    count=1,
                    block=1000,
                )
                for _stream, messages in events or []:
                    for message_id, event_data in messages:
                        try:
                            payload_bytes = event_data.get(b"payload", b"{}")
                            topic = event_data.get(b"topic", b"").decode("utf-8")
                            if topic:
                                payload = json.loads(
                                    payload_bytes.decode("utf-8")
                                    if isinstance(payload_bytes, (bytes, bytearray))
                                    else payload_bytes,
                                )
                                await self.publish(topic, payload, _from_redis=True)
                        except json.JSONDecodeError:
                            log.error(
                                f"[EventBus] Received non-JSON payload from Redis: {payload_bytes!r}",
                            )
                        except Exception as e:
                            log.error(
                                f"[EventBus] Error processing message from Redis: {e!r}",
                            )
                        finally:
                            try:
                                await self._redis_client.xack(
                                    self._stream_key,
                                    self._consumer_group,
                                    message_id,
                                )
                            except Exception:
                                # Don’t crash the loop on ack errors
                                pass
            except Exception as e:
                log.error(
                    f"[EventBus] Redis listener loop error: {e!r}",
                    exc_info=True,
                )
                await asyncio.sleep(5)

    async def publish(
        self,
        topic_or_event: str | dict[str, Any],
        payload: dict[str, Any] | None = None,
        *,
        _from_redis: bool = False,
    ):
        if isinstance(topic_or_event, str):
            topic, data = topic_or_event, payload or {}
        elif isinstance(topic_or_event, dict):
            topic = topic_or_event.get("topic") or topic_or_event.get("type") or ""
            data = topic_or_event.get("payload") or {}
        else:
            return
        if not topic:
            log.warning("[EventBus] Attempted to publish event with no topic.")
            return

        subscribers = list(self._subscribers.get(topic, []))
        for cb in subscribers:
            try:
                res = cb(data)
                if inspect.iscoroutine(res):
                    await res
            except Exception as e:
                log.error(f"[EventBus] Subscriber error on '{topic}': {e!r}")

        if not _from_redis:
            try:
                event_data = {"topic": topic, "payload": json.dumps(data)}
                await self._redis_client.xadd(self._stream_key, event_data)
            except Exception as e:
                log.error(f"[EventBus] Failed to publish to Redis stream: {e!r}")

    async def shutdown(self):
        self._running = False
        if self._redis_listener_task:
            self._redis_listener_task.cancel()
            try:
                await self._redis_listener_task
            except asyncio.CancelledError:
                pass
        try:
            await self._redis_client.close()
        except Exception:
            pass
        log.info("[EventBus] Shutdown complete.")

    def subscribe(self, topic: str, cb: Callback) -> Callable[[], None]:
        self._subscribers[topic].append(cb)

        def _unsub():
            try:
                self._subscribers[topic].remove(cb)
            except (ValueError, KeyError):
                pass

        return _unsub

    def unsubscribe(self, topic: str, cb: Callback) -> None:
        try:
            self._subscribers[topic].remove(cb)
        except (ValueError, KeyError):
            pass

    async def subscribe_once(self, topic: str, timeout: float | None = None) -> Any:
        fut = asyncio.get_running_loop().create_future()

        def _cb(payload: Any):
            if not fut.done():
                fut.set_result(payload)
            self.unsubscribe(topic, _cb)

        self.subscribe(topic, _cb)
        return await asyncio.wait_for(fut, timeout=timeout)


event_bus = EventBus()
