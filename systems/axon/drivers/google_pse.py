from __future__ import annotations

import os
from typing import Any, Dict, Literal

import aiohttp
from pydantic import BaseModel

from systems.axon.mesh.registry import DriverInterface


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str] = ["probe"]
    summary: str = "Google Programmable Search (Custom Search Engine)"


class GooglePse(DriverInterface):
    MODE: Literal["probe"] = "probe"
    NAME: str = "google_pse"
    VERSION: str = "1.1.0"  # Version bumped to reflect new methods

    def __init__(self):
        # These will raise a KeyError if missing, providing a clear startup failure.
        self.key = os.environ["GENERAL_GOOGLE_API_KEY"]
        self.cx = os.environ["GOOGLE_PSE_CX"]
        self.service_url = "https://www.googleapis.com/customsearch/v1"

    def describe(self) -> _Spec:
        """Returns metadata about the driver."""
        return _Spec(driver_name=self.NAME, version=self.VERSION)

    async def probe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Performs a web search using the Google PSE API."""
        q = params.get("query")
        if not q:
            raise ValueError("'query' parameter is required for probe.")

        num = int(params.get("num", 5))
        safe = params.get("safe", "active")

        async with aiohttp.ClientSession() as s:
            r = await s.get(
                self.service_url,
                params={
                    "key": self.key,
                    "cx": self.cx,
                    "q": q,
                    "num": min(num, 10),
                    "safe": safe,
                },
                timeout=12,
            )
            r.raise_for_status()
            data = await r.json()

        out = []
        for it in data.get("items", []):
            out.append(
                {
                    "title": it.get("title"),
                    "link": it.get("link"),
                    "snippet": it.get("snippet"),
                    "displayLink": it.get("displayLink"),
                }
            )
        return {"query": q, "results": out}

    def repro_bundle(self) -> dict[str, Any]:
        """
        Returns a dictionary of non-sensitive configuration details
        for reproducibility and debugging.
        """
        return {
            "driver_name": self.NAME,
            "version": self.VERSION,
            "cx_id": self.cx,  # The Search Engine ID is not a secret
            "service_url": self.service_url,
        }

    async def self_test(self) -> dict[str, Any]:
        """
        Performs a live health check of the driver by executing a minimal,
        safe query to validate credentials and connectivity.
        """
        try:
            async with aiohttp.ClientSession() as s:
                r = await s.get(
                    self.service_url,
                    params={"key": self.key, "cx": self.cx, "q": "test", "num": 1},
                    timeout=5,
                )
                r.raise_for_status()
                # We just need a successful 200 OK, we don't need the body
                return {"status": "ok", "message": "Successfully connected to Google PSE API."}
        except aiohttp.ClientResponseError as e:
            return {
                "status": "error",
                "message": f"API request failed with status {e.status}. Check your API Key and CX ID.",
                "details": str(e),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": "A general error occurred during the self-test.",
                "details": str(e),
            }
