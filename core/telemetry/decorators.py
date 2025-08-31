from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Union

from core.telemetry.with_episode import episode_outcome

TaskKeyArg = Union[str, Callable[..., str]]


def episode(task_key: TaskKeyArg):
    """
    Decorator for episode entrypoints. Ensures we ALWAYS write a single outcome.
    Requires that select_arm has already bound the episode (you added that).
    Usage:
        @episode("unity.debate")
        async def run_debate(...): ...

        @episode(lambda self, task_ctx, *args, **kw: task_ctx.task_key)
        async def execute(self, task_ctx: TaskContext, ...): ...
    """

    def _resolve(args, kwargs) -> str:
        if isinstance(task_key, str):
            return task_key
        # callable → pass through args/kwargs so you can derive from task_ctx
        return str(task_key(*args, **kwargs))

    def _decor(fn):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError("@episode must wrap an async function")

        @wraps(fn)
        async def _wrapped(*args, **kwargs):
            tk = _resolve(args, kwargs)
            async with episode_outcome(task_key=tk):
                return await fn(*args, **kwargs)

        return _wrapped

    return _decor
