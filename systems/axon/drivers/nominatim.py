from __future__ import annotations

import logging
from typing import Any, Dict, Literal

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from systems.axon.mesh.registry import DriverInterface

log = logging.getLogger("Nominatim")


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str]
    summary: str


class _Args(BaseModel):
    query: str = Field(..., description="Place search (city/town/POI)")
    limit: int = Field(3, ge=1, le=10)


class Nominatim(DriverInterface):
    NAME = "nominatim"
    VERSION = "1.0.0"
    ACTION: Literal["geocode"] = "geocode"

    def describe(self) -> _Spec:
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[self.ACTION],
            summary="OpenStreetMap geocoding via Nominatim (simple forward search).",
        )

    async def geocode(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            args = _Args(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        url = "https://nominatim.openstreetmap.org/search"
        q = {"q": args.query, "format": "json", "addressdetails": 1, "limit": args.limit}
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": "EcodiaOS/1.0"}) as s:
                r = await s.get(url, params=q)
                r.raise_for_status()
                data = await r.json()
            return {"status": "ok", "results": data}
        except Exception as e:
            log.exception("[Nominatim] failure")
            return {"status": "error", "message": str(e)}
