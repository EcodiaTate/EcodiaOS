from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    @abstractmethod
    async def execute(self, task: dict[str, Any]) -> dict[str, Any]: ...
