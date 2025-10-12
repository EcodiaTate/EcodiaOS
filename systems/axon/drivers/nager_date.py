from __future__ import annotations

import logging
from typing import Any, Dict, Literal

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from systems.axon.mesh.registry import DriverInterface

log = logging.getLogger("NagerDate")


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str]
    summary: str


class _Args(BaseModel):
    country_code: str = Field(
        ..., min_length=2, max_length=2, description="ISO-3166-1 alpha-2 (e.g., AU, US)"
    )
    year: int = Field(..., ge=1900, le=2100)


class NagerDate(DriverInterface):
    NAME = "nager"
    VERSION = "1.0.0"
    ACTION: Literal["public_holidays"] = "public_holidays"

    def describe(self) -> _Spec:
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[self.ACTION],
            summary="Official public holidays by country/year (Nager.Date).",
        )

    async def public_holidays(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            args = _Args(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        url = f"https://date.nager.at/api/v3/PublicHolidays/{args.year}/{args.country_code.upper()}"
        try:
            async with aiohttp.ClientSession() as s:
                r = await s.get(url)
                r.raise_for_status()
                data = await r.json()
            return {
                "status": "ok",
                "country_code": args.country_code.upper(),
                "year": args.year,
                "holidays": data,
            }
        except Exception as e:
            log.exception("[NagerDate] failure")
            return {"status": "error", "message": str(e)}
