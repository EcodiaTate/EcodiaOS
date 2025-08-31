# systems/equor/core/identity/homeostasis.py
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import deque
from typing import Any

import numpy as np

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from systems.equor.core.identity.composer import PromptComposer
from systems.equor.schemas import Attestation, ComposeRequest, DriftReport, PatchProposalEvent
from systems.synapse.core.snapshots import stamp as rcu_stamp
from systems.equor.core.identity.homeostasis_helper import HomeostasisHelper

logger = logging.getLogger(__name__)

# Tunables via env with safe defaults
_ALERT_COOLDOWN_SEC = float(os.getenv("EQUOR_HOMEOSTASIS_ALERT_COOLDOWN_SEC", "3600"))  # 1h
_MIN_SAMPLES_TO_EVAL = int(os.getenv("EQUOR_HOMEOSTASIS_MIN_SAMPLES", "10"))  # need some signal
_ALERT_THRESHOLD = float(
    os.getenv("EQUOR_HOMEOSTASIS_COVERAGE_DROP", "0.30"),
)  # alert if avg < 0.70
_EMA_ALPHA = float(os.getenv("EQUOR_HOMEOSTASIS_EMA_ALPHA", "0.2"))  # smoothing factor
_DEFAULT_PROFILE = os.getenv("EQUOR_HOMEOSTASIS_PROFILE", "prod")

# ---- Homeostasis gating helper (prevents compose/escalate loops) ----
# Optional Redis wiring (safe if unavailable)
try:
    from redis.asyncio import Redis  # type: ignore
except Exception:  # pragma: no cover
    Redis = None  # type: ignore

_redis = None
try:
    _redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_URI")
    if Redis and _redis_url:
        _redis = Redis.from_url(_redis_url)
except Exception:
    _redis = None

_homeo_helper = HomeostasisHelper(redis=_redis)


class HomeostasisMonitor:
    """
    Stateful singleton service that measures identity adherence/drift and proposes corrective patches.
    Also acts as a controlled gateway for follow-up /equor/compose calls after attestations, using
    HomeostasisHelper to prevent re-entrancy loops.
    """

    _instance: HomeostasisMonitor | None = None
    _monitors: dict[str, AgentMonitor] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.composer = PromptComposer()
        return cls._instance

    def get_monitor_for_agent(self, agent_name: str) -> AgentMonitor:
        """Get or create a per-agent monitor."""
        if agent_name not in self._monitors:
            self._monitors[agent_name] = AgentMonitor(agent_name, self.composer)
        return self._monitors[agent_name]

    async def process_attestation(self, attestation: Attestation):
        """
        Process a new attestation for the corresponding agent, update drift metrics,
        and (gated) trigger a compose only if state actually changed.
        """
        monitor = self.get_monitor_for_agent(attestation.agent)
        await monitor.update_metrics(attestation)

        # ---- Gated compose to avoid loops ----
        try:
            await _homeo_helper.maybe_compose(
                agent=attestation.agent,
                episode_id=attestation.episode_id,
                profile_name=_DEFAULT_PROFILE,
                context={
                    "source": "attestation",
                    "run_id": attestation.run_id,
                },
                applied_patch_id=attestation.applied_prompt_patch_id,
                breaches=(attestation.breaches or []),
                decision_id=attestation.episode_id,  # mirror governance episode id
            )
        except Exception:
            # Best-effort; never let this break request paths
            logger.exception(
                "[Homeostasis] Gated compose failed (agent=%s, episode=%s)",
                attestation.agent,
                attestation.episode_id,
            )

    async def run_monitor_cycle(self):
        """
        Periodic drift check + proposal emission when thresholds are crossed.
        """
        logger.info("[Homeostasis] Running periodic drift check cycle...")
        for agent_name, monitor in list(self._monitors.items()):
            try:
                if monitor.should_alert():
                    report = monitor.generate_report()
                    await monitor.propose_tightened_patch(report)
                    monitor.reset_alert_trigger()
            except Exception:
                logger.exception("[Homeostasis] Drift cycle error for agent=%s", agent_name)


class AgentMonitor:
    """Tracks metrics for a single agent and generates corrective proposals."""

    def __init__(
        self,
        agent_name: str,
        composer: PromptComposer,
        window_size: int = 50,
        alert_threshold: float = _ALERT_THRESHOLD,
    ):
        self.agent_name = agent_name
        self.composer = composer
        self.window_size = int(max(5, window_size))
        self.alert_threshold = float(min(max(alert_threshold, 0.0), 1.0))
        self.recent_coverages: deque[float] = deque(maxlen=self.window_size)
        self.recent_breaches: deque[int] = deque(maxlen=self.window_size)
        self.last_alert_time = 0.0
        self._ema_coverage: float | None = None  # exponential moving average

    async def update_metrics(self, attestation: Attestation):
        """Update rolling metrics with a new attestation."""
        cov = await self._calculate_coverage(attestation)
        cov_ratio = float(cov.get("coverage_ratio", 1.0))
        breaches = int(len(cov.get("breaches", [])))
        self.recent_coverages.append(cov_ratio)
        self.recent_breaches.append(breaches)

        # EMA smoothing for responsive yet stable drift detection
        if self._ema_coverage is None:
            self._ema_coverage = cov_ratio
        else:
            self._ema_coverage = (1.0 - _EMA_ALPHA) * self._ema_coverage + _EMA_ALPHA * cov_ratio

        # Optional: write a compact metric point to the graph for auditability
        try:
            await cypher_query(
                """
                MERGE (a:Agent {name:$agent})
                CREATE (m:HomeostasisMetric {
                  id: $id,
                  agent: $agent,
                  coverage: $coverage,
                  breaches: $breaches,
                  ema_coverage: $ema,
                  at: datetime()
                })
                MERGE (a)-[:OBSERVED]->(m)
                """,
                {
                    "id": f"hm_{uuid.uuid4().hex}",
                    "agent": self.agent_name,
                    "coverage": cov_ratio,
                    "breaches": breaches,
                    "ema": float(self._ema_coverage),
                },
            )
        except Exception:
            logger.exception("[Homeostasis] Metric write failed for agent=%s", self.agent_name)

    def should_alert(self) -> bool:
        """Return True when drift warrants a tightening proposal."""
        if len(self.recent_coverages) < max(_MIN_SAMPLES_TO_EVAL, 5):
            return False
        if (time.monotonic() - self.last_alert_time) < _ALERT_COOLDOWN_SEC:
            return False

        avg = float(np.mean(self.recent_coverages))
        ema = float(self._ema_coverage if self._ema_coverage is not None else avg)
        threshold = 1.0 - self.alert_threshold

        # Trigger if both window average and EMA fall below the threshold
        alert = (avg < threshold) and (ema < threshold)
        logger.debug(
            "[Homeostasis] agent=%s avg=%.3f ema=%.3f threshold=%.3f alert=%s",
            self.agent_name,
            avg,
            ema,
            threshold,
            alert,
        )
        return alert

    def reset_alert_trigger(self):
        """Start cooldown after emitting a proposal."""
        self.last_alert_time = time.monotonic()

    def generate_report(self) -> DriftReport:
        """Snapshot report for the current window."""
        avg_cov = float(np.mean(self.recent_coverages)) if self.recent_coverages else 1.0
        std_cov = float(np.std(self.recent_coverages)) if self.recent_coverages else 0.0
        return DriftReport(
            agent=self.agent_name,
            window=f"last_{len(self.recent_coverages)}_outputs",
            style_delta=0.0,
            content_delta=0.0,
            rule_breach_count=int(sum(self.recent_breaches)),
            uncertainty=std_cov,
            details={
                "average_coverage": avg_cov,
                "ema_coverage": float(self._ema_coverage)
                if self._ema_coverage is not None
                else avg_cov,
                "samples": len(self.recent_coverages),
            },
        )

    async def propose_tightened_patch(self, report: DriftReport):
        """
        Generate a stricter PromptPatch and publish it for review.
        """
        logger.info(
            "[Homeostasis] Drift detected for agent=%s; generating proposal.",
            self.agent_name,
        )
        try:
            # Capture an RCU snapshot for replayability
            rcu_ref = rcu_stamp()

            # Compose with explicit tightening context
            request = ComposeRequest(
                agent=self.agent_name,
                profile_name=_DEFAULT_PROFILE,
                context={
                    "tightening_request": True,
                    "breaches": report.rule_breach_count,
                    "avg_coverage": report.details.get("average_coverage"),
                    "ema_coverage": report.details.get("ema_coverage"),
                },
            )

            response = await self.composer.compose(request, rcu_ref=str(rcu_ref))

            proposal = PatchProposalEvent(
                proposal_id=f"prop_{uuid.uuid4().hex}",
                agent=self.agent_name,
                triggering_report=report,
                proposed_patch_text=response.text,
                notes=(
                    f"Automated proposal to improve rule coverage "
                    f"(avg={report.details['average_coverage']:.2f}, "
                    f"ema={report.details.get('ema_coverage', report.details['average_coverage']):.2f})."
                ),
            )

            # Persist and emit
            await cypher_query(
                """
                MERGE (a:Agent {name:$agent})
                CREATE (p:PatchProposal {id:$pid, created_at: datetime(), notes:$notes})
                SET p.text = $text
                MERGE (a)-[:PROPOSED]->(p)
                """,
                {
                    "agent": self.agent_name,
                    "pid": proposal.proposal_id,
                    "notes": proposal.notes,
                    "text": proposal.proposed_patch_text,
                },
            )

            await event_bus.publish(
                {
                    "topic": "equor.patch_proposal.created",
                    "payload": {"proposal": proposal.model_dump()},
                },
            )
            logger.info(
                "[Homeostasis] Proposal emitted id=%s agent=%s",
                proposal.proposal_id,
                self.agent_name,
            )

        except Exception as e:
            logger.exception(
                "[Homeostasis] Failed to generate/publish patch proposal for agent=%s",
                self.agent_name,
            )
            # Emit a failure event so upstream can observe and alert
            try:
                await event_bus.publish(
                    "equor.patch_proposal.failed",
                    {"agent": self.agent_name, "error": str(e), "report": report.model_dump()},
                )
            except Exception:
                # Avoid masking the original failure
                pass

    async def _calculate_coverage(self, attestation: Attestation) -> dict[str, Any]:
        """Compute coverage ratio and valid breaches for a given attestation."""
        rows = await cypher_query(
            """
            MATCH (:PromptPatch {id: $patch_id})-[:DERIVED_FROM]->(r:ConstitutionRule)
            RETURN r.id AS rule_id
            """,
            {"patch_id": attestation.applied_prompt_patch_id},
        )

        if not rows:
            return {"coverage_ratio": 1.0, "breaches": [], "applicable_rules": 0}

        applicable_rules = {r.get("rule_id") for r in rows if r.get("rule_id")}
        att_breaches = set(attestation.breaches or [])
        valid_breaches = applicable_rules.intersection(att_breaches)

        num_applicable = len(applicable_rules)
        num_honored = num_applicable - len(valid_breaches)
        coverage_ratio = (num_honored / num_applicable) if num_applicable > 0 else 1.0

        return {
            "coverage_ratio": round(float(coverage_ratio), 4),
            "breaches": list(valid_breaches),
            "applicable_rules": num_applicable,
        }
