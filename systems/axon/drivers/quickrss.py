from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Literal

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from systems.axon.mesh.registry import DriverInterface

log = logging.getLogger("RSSDriver")


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str]
    summary: str


class _Args(BaseModel):
    url: str = Field(..., description="RSS/Atom feed URL")
    max_items: int = Field(10, ge=1, le=50)


class RSSDriver(DriverInterface):
    NAME = "rssdriver"
    VERSION = "1.0.1"
    ACTION: Literal["fetch"] = "fetch"

    def describe(self) -> _Spec:
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[self.ACTION],
            summary="Fetch and parse RSS/Atom feeds into lightweight items.",
        )

    async def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            args = _Args(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        try:
            async with aiohttp.ClientSession() as s:
                r = await s.get(args.url, timeout=20)
                r.raise_for_status()
                text = await r.text()
            # Basic XML parse (tolerant for RSS/Atom)
            root = ET.fromstring(text)
            items = []
            # RSS
            for it in root.findall(".//item")[: args.max_items]:
                items.append(
                    {
                        "title": (it.findtext("title") or "").strip(),
                        "link": (it.findtext("link") or "").strip(),
                        "pubDate": (it.findtext("pubDate") or "").strip(),
                        "description": (it.findtext("description") or "").strip(),
                    }
                )
            # Atom
            if not items:
                for it in root.findall(".//{http://www.w3.org/2005/Atom}entry")[: args.max_items]:
                    link = ""
                    link_el = it.find("{http://www.w3.org/2005/Atom}link")
                    if link_el is not None:
                        link = link_el.get("href", "")
                    items.append(
                        {
                            "title": (
                                it.findtext("{http://www.w3.org/2005/Atom}title") or ""
                            ).strip(),
                            "link": link,
                            "updated": (
                                it.findtext("{http://www.w3.org/2005/Atom}updated") or ""
                            ).strip(),
                            "summary": (
                                it.findtext("{http://www.w3.org/2005/Atom}summary") or ""
                            ).strip(),
                        }
                    )
            return {"status": "ok", "count": len(items), "items": items}
        except Exception as e:
            log.exception("[RSS] failure")
            return {"status": "error", "message": str(e)}

    async def self_test(self) -> dict[str, Any]:
        return await self.fetch({"url": "https://news.google.com/rss", "max_items": 3})
