# api/middleware/governance.py
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import Request, Response
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from core.utils.net_api import ENDPOINTS, post_internal
from systems.equor.schemas import Attestation, ComposeResponse

logger = logging.getLogger(__name__)

IMMUNE_HEADER = "x-ecodia-immune"
DECISION_HEADER = "x-decision-id"
BUDGET_HEADER = "x-budget-ms"

# Routes where we avoid noisy warnings if governance context is missing.
_SILENT_PATHS: set[str] = {
     "/evo/escalate",
     "/equor/compose",
     "/equor/attest",
 }
_RECURSION_SKIP_PATHS: set[str] = {
    "/equor/compose",
    "/equor/attest",
}

# ---------- background submit ----------

async def _submit_attestation_task(attestation: Attestation) -> None:
    """
    Fire-and-forget submit of the post-flight attestation.
    Immune header prevents middleware recursion on this internal call.
    """
    try:
        payload = attestation.model_dump(exclude_none=True)
        headers = {
            IMMUNE_HEADER: "1",
            DECISION_HEADER: attestation.episode_id or f"auto-{uuid.uuid4().hex[:8]}",
        }
        resp = await post_internal(ENDPOINTS.EQUOR_ATTEST, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        logger.info("Attestation submitted for episode: %s", attestation.episode_id)
    except Exception:
        # We keep this non-fatal and avoid recursive conflict logging.
        logger.exception("Failed to submit attestation for episode: %s", attestation.episode_id)

# ---------- low-level header helpers ----------

def _inject_scope_header(request: Request, name: str, value: str) -> None:
    """
    Safely inject a header into ASGI scope so downstream dependencies can read it.
    """
    headers = list(request.scope.get("headers", []))
    headers.append((name.lower().encode(), value.encode()))
    request.scope["headers"] = headers

# ---------- preflight dependency ----------

async def constitutional_preamble(request: Request) -> None:
    """
    Pre-flight governance: try to fetch an active constitutional patch.
    - Honors x-ecodia-immune to avoid recursion on internal calls.
    - If X-Decision-Id is missing, mint one (quietly for hot paths).
    - If Equor lacks a matching Profile (422), proceed without a patch.
    - On network/parse errors, fail-open: continue without patch.

    Side-effects on request.state:
      - decision_id: str | None
      - agent: str
      - governance_started_at: float (perf counter for SLA)
      - constitutional_patch: ComposeResponse | None
    """
    path = request.url.path
    agent = (path.strip("/").split("/") or ["system"])[0]

   # Hard-stop recursion: do not call Equor from inside Equor's own routes
    if path in _RECURSION_SKIP_PATHS:
        request.state.governance_started_at = time.perf_counter()
        request.state.decision_id = request.headers.get(DECISION_HEADER) or f"auto-{uuid.uuid4().hex[:8]}"
        request.state.agent = agent
        request.state.constitutional_patch = None
        return
    
    # Skip governance for immune internal calls
    if request.headers.get(IMMUNE_HEADER) == "1":
        request.state.governance_started_at = time.perf_counter()
        request.state.decision_id = request.headers.get(DECISION_HEADER)
        request.state.agent = agent
        request.state.constitutional_patch = None
        return

    # Ensure we have a decision id for governance traceability
    decision_id = request.headers.get(DECISION_HEADER)
    if not decision_id:
        decision_id = f"auto-{uuid.uuid4().hex[:8]}"
        _inject_scope_header(request, DECISION_HEADER, decision_id)
        if path not in _SILENT_PATHS:
            logger.info("Governance: minted X-Decision-Id=%s for %s", decision_id, path)

    # Stamp the clock for SLA checks
    request.state.governance_started_at = time.perf_counter()
    request.state.decision_id = decision_id
    request.state.agent = agent

    # Best-effort fetch of a patch (immune internal call to Equor)
    try:
        compose_request: dict[str, Any] = {
            "agent": agent,
            "profile_name": "prod",             # default operational profile
            "episode_id": decision_id,          # governance episode id
            "context": {"request_path": path},  # minimal context
        }
        headers = {IMMUNE_HEADER: "1", DECISION_HEADER: decision_id}
        r = await post_internal(ENDPOINTS.EQUOR_COMPOSE, json=compose_request, headers=headers, timeout=10.0)

        # No profile configured yet → treat as "no patch"
        if r.status_code == 422:
            if path not in _SILENT_PATHS:
                logger.warning(
                    "Governance preamble: no active profile for agent '%s' (422). Proceeding without patch.",
                    agent,
                )
            request.state.constitutional_patch = None
            return

        r.raise_for_status()

        # Validate shape; if bad shape, treat as no patch
        try:
            patch = ComposeResponse(**r.json())
        except Exception as e:
            if path not in _SILENT_PATHS:
                logger.warning("Governance preamble: invalid ComposeResponse: %s", e)
            request.state.constitutional_patch = None
            return

        request.state.constitutional_patch = patch

    except Exception as e:
        # Fail-open if Equor is offline or returns non-JSON, etc.
        if path not in _SILENT_PATHS:
            logger.warning("Governance preamble failed for agent '%s' (%s). Proceeding without patch.", agent, e)
        request.state.constitutional_patch = None

# ---------- postflight middleware ----------

class AttestationMiddleware(BaseHTTPMiddleware):
    """
    Post-flight governance attestation:
      - Skips immune internal calls.
      - Mirrors a generated X-Decision-Id to the response header.
      - Computes basic breach signals (SLA/HTTP class/content flags).
      - Submits Attestation asynchronously (best-effort).
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip attestation on immune internal calls and Equor endpoints
        if request.headers.get(IMMUNE_HEADER) == "1" or request.url.path in _RECURSION_SKIP_PATHS:
            return await call_next(request)

        started_at = getattr(request.state, "governance_started_at", time.perf_counter())
        response = await call_next(request)

        patch: ComposeResponse | None = getattr(request.state, "constitutional_patch", None)
        agent: str | None = getattr(request.state, "agent", None)
        decision_id: str | None = getattr(request.state, "decision_id", None) or request.headers.get(DECISION_HEADER)

        # Mirror decision id onto the response for traceability
        if decision_id and DECISION_HEADER not in response.headers:
            response.headers[DECISION_HEADER.upper()] = decision_id  # "X-DECISION-ID"

        # Only attest governed requests (we had a patch AND an episode id)
        if not (patch and agent and decision_id):
            return response

        # Breach detection (SLA + HTTP class + basic content flags)
        breaches: list[str] = []

        # SLA based on caller budget
        try:
            hdr = request.headers.get(BUDGET_HEADER)
            if hdr:
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                if elapsed_ms > int(hdr):
                    breaches.append("SLA_BREACH")
        except Exception:
            pass

        # HTTP class
        try:
            if 500 <= response.status_code:
                breaches.append("UPSTREAM_ERROR")
            elif 400 <= response.status_code < 500:
                breaches.append("CLIENT_ERROR")
        except Exception:
            pass

        # Content quick-check (only if body is accessible & JSON)
        try:
            ct = response.headers.get("content-type", "")
            if "application/json" in ct and hasattr(response, "body") and response.body:
                try:
                    payload = json.loads(response.body.decode("utf-8"))
                    if isinstance(payload, dict) and (
                        payload.get("policy_violation") is True or payload.get("unsafe") is True
                    ):
                        breaches.append("CONTENT_POLICY_FLAG")
                except Exception:
                    pass
        except Exception:
            pass

        # Fire-and-forget attestation (immune internal call)
        attestation = Attestation(
            run_id=f"run_{decision_id}",
            episode_id=decision_id,
            agent=agent,
            applied_prompt_patch_id=patch.prompt_patch_id,
            breaches=breaches,
        )
        response.background = BackgroundTask(_submit_attestation_task, attestation)
        return response
