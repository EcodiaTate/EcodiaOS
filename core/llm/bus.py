# core/utils/events/bus.py
from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from collections.abc import Callable
from typing import Any

Callback = Callable[[Any], Any]  # can be sync or async


class EventBus:
    """
    Minimal async-friendly pub/sub bus (singleton).
    - subscribe(topic, cb) -> returns an unsubscribe handle (callable)
    - unsubscribe(topic, cb)
    - subscribe_once(topic, timeout: float | None) -> await payload
    - publish(topic_or_event, payload=None)

    Notes
    -----
    * Callbacks may be sync or async.
    * Topics are arbitrary strings.
    * You can also publish(dict) with keys: 'topic' | 'type' | 'event' and 'payload'.
    """

    _instance: EventBus | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # initialize per-instance storage
            cls._instance._subscribers = defaultdict(list)  # type: ignore[attr-defined]
            cls._instance._lock = asyncio.Lock()  # type: ignore[attr-defined]
        return cls._instance

    # ----- subscription API -------------------------------------------------

    def subscribe(self, topic: str, cb: Callback) -> Callable[[], None]:
        """
        Register a callback for a topic. Returns an unsubscribe handle you can call.
        """
        self._subscribers[topic].append(cb)
        # print(f"[EventBus] subscribe: {topic} -> {getattr(cb, '__name__', repr(cb))}")

        def _unsub() -> None:
            try:
                self._subscribers[topic].remove(cb)
            except (ValueError, KeyError):
                pass

        return _unsub

    def unsubscribe(self, topic: str, cb: Callback) -> None:
        """
        Remove a callback for a topic. Safe to call multiple times.
        """
        try:
            self._subscribers[topic].remove(cb)
        except (ValueError, KeyError):
            pass

    async def subscribe_once(self, topic: str, timeout: float | None = None) -> Any:
        """
        Await the *next* payload published to `topic`, then auto-unsubscribe.
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        def _cb(payload: Any) -> None:
            if not fut.done():
                fut.set_result(payload)
            # remove ourselves
            try:
                self._subscribers[topic].remove(_cb)
            except (ValueError, KeyError):
                pass

        self._subscribers[topic].append(_cb)

        if timeout is not None:
            try:
                return await asyncio.wait_for(fut, timeout=timeout)
            except TimeoutError:
                # ensure we detach if timing out
                try:
                    self._subscribers[topic].remove(_cb)
                except (ValueError, KeyError):
                    pass
                raise
        else:
            return await fut

    # ----- publishing -------------------------------------------------------

    async def publish(
        self,
        topic_or_event: str | dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> None:
        """
        Publish an event. Accepts either:
        - (topic: str, payload: dict)
        - (event: dict) with keys:
            * 'topic' | 'type' | 'event'  -> topic name
            * 'payload'                   -> payload dict
        """
        if isinstance(topic_or_event, str):
            topic = topic_or_event
            data = payload or {}
        elif isinstance(topic_or_event, dict):
            topic = (
                topic_or_event.get("topic")
                or topic_or_event.get("type")
                or topic_or_event.get("event")
                or ""
            )
            data = topic_or_event.get("payload") or {}
        else:
            return  # unsupported

        # Snapshot subscribers to avoid mutation during iteration
        subscribers: list[Callback] = list(self._subscribers.get(topic, []))
        # print(f"[EventBus] publish: {topic} -> {len(subscribers)} listener(s)")

        for cb in subscribers:
            try:
                if inspect.iscoroutinefunction(cb):
                    await cb(data)  # type: ignore[arg-type]
                else:
                    result = cb(data)  # type: ignore[arg-type]
                    # If a sync callback returns a coroutine, await it
                    if inspect.iscoroutine(result):
                        await result
            except Exception as e:
                # Non-fatal: keep other subscribers running
                print(f"[EventBus] subscriber error on '{topic}': {e!r}")


# Global singleton instance
event_bus = EventBus()
