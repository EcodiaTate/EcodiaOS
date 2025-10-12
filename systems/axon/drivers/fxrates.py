from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from systems.axon.mesh.registry import DriverInterface

log = logging.getLogger("FXRates")


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str]
    summary: str


class _Args(BaseModel):
    base: str = Field("AUD", min_length=3, max_length=3, description="Base currency (ISO 4217)")
    symbols: list[str] | None = Field(None, description="Target currencies; omit for all.")


class FXRates(DriverInterface):
    NAME = "fxrates"
    VERSION = "1.0.0"
    ACTION: Literal["latest"] = "latest"

    def describe(self) -> _Spec:
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[self.ACTION],
            summary="Latest foreign exchange rates (exchangerate.host).",
        )

    async def latest(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            args = _Args(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        url = "https://api.exchangerate.host/latest"
        q: dict[str, Any] = {"base": args.base.upper()}
        if args.symbols:
            q["symbols"] = ",".join([s.upper() for s in args.symbols])

        try:
            async with aiohttp.ClientSession() as s:
                r = await s.get(url, params=q)
                r.raise_for_status()
                data = await r.json()
            return {
                "status": "ok",
                "base": data.get("base"),
                "date": data.get("date"),
                "rates": data.get("rates"),
            }
        except Exception as e:
            log.exception("[FXRates] failure")
            return {"status": "error", "message": str(e)}
