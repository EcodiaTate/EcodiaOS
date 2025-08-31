# systems/axon/drivers/rss_driver.py
from __future__ import annotations

import hashlib
import uuid
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from typing import Any

from core.utils.net_api import get_http_client
from systems.axon.mesh.sdk import CapabilitySpec, DriverInterface, HealthStatus, ReplayCapsule
from systems.axon.schemas import ActionResult, AxonEvent, AxonIntent


class RssDriver(DriverInterface):
    """Pull-only driver that ingests RSS feeds with replay support."""

    NAME = "rss"
    VERSION = "1.0.3"
    CAPABILITY = None  # no push

    def __init__(self):
        # pull_id → raw xml; guid → pull_id
        self._pull_cache: dict[str, str] = {}
        self._id_map: dict[str, str] = {}

    def describe(self) -> CapabilitySpec:
        return CapabilitySpec(
            driver_name=self.NAME,
            driver_version=self.VERSION,
            supported_actions=[],  # pull-only
            risk_profile={},
            budget_model={"pull": 1.0},
            auth_requirements=["none"],
        )

    async def pull(self, params: dict[str, Any]) -> AsyncIterator[AxonEvent]:
        """
        Pulls from a feed URL and yields AxonEvent(s) directly.
        """
        feed_url = params.get("url")
        if not feed_url:
            raise ValueError("RSS Driver 'pull' requires a 'url' in params.")

        client = await get_http_client()
        try:
            response = await client.get(feed_url)
            response.raise_for_status()
            raw_content = response.text

            pull_id = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
            self._pull_cache[pull_id] = raw_content

            root = ET.fromstring(raw_content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                guid = (item.findtext("guid") or link or str(uuid.uuid4())).strip()
                self._id_map[guid] = pull_id

                yield AxonEvent(
                    event_id=str(uuid.uuid4()),
                    t_observed=None,  # set by Atune on ingest if desired
                    source=f"rss:{feed_url}",
                    event_type="article_published",
                    modality="html",
                    payload_ref=link,
                    parsed={"title": title, "description": desc, "guid": guid},
                    embeddings={},
                    provenance={
                        "driver_id": self.NAME,
                        "version": self.VERSION,
                        "feed_url": feed_url,
                        "pull_id": pull_id,
                    },
                    salience_hints={},
                    quality={},
                    triangulation={},
                    cost_ms=None,
                    cost_usd=0.0,
                )
        except Exception as e:
            print(f"RssDriver failed for {feed_url}: {e}")
            return

    async def push(self, intent: AxonIntent) -> ActionResult:
        raise NotImplementedError("RssDriver does not support 'push'.")

    async def self_test(self) -> HealthStatus:
        # Basic health = we can instantiate and parse a tiny sample doc
        try:
            ET.fromstring("<rss><channel><item><title>x</title></item></channel></rss>")
            return HealthStatus(status="ok", details="XML parser OK")
        except Exception as e:
            return HealthStatus(status="error", details=f"xml error: {e}")

    async def repro_bundle(self, *, id: str, kind: str) -> ReplayCapsule:
        pull_id = self._id_map.get(id)  # here `id` is the item guid
        if not pull_id or pull_id not in self._pull_cache:
            raise KeyError(f"No cached content for GUID {id}")
        raw_content = self._pull_cache[pull_id]
        env_hash = hashlib.blake2b(pull_id.encode("utf-8"), digest_size=16).hexdigest()
        return ReplayCapsule(
            id=id,
            type="event",
            driver_version=self.VERSION,
            environment_hash=env_hash,
            inputs={"params": {"url": "unknown"}, "pull_id": pull_id},
            outputs={"raw_content": raw_content},
        )
