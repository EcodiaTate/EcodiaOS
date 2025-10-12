# api/endpoints/axon/probecraft_intake.py
from __future__ import annotations

# highlight-start
import time
import uuid

# highlight-end
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.atune.gaps.schema import CapabilityGapEvent
from systems.axon.mesh.lifecycle import DriverLifecycleManager, DriverStatus
from systems.axon.mesh.registry import DriverRegistry
from systems.axon.mesh.scorecard import ScorecardManager

# highlight-start
from systems.axon.schemas import AxonIntent

# highlight-end
from systems.axon.security.attestation import AttestationManager  # expected in your tree

router = APIRouter()

# --- Local helpers -----------------------------------------------------------


async def _synthesize_from_spec(
    manager: DriverLifecycleManager,
    name: str,
    spec_url: str,
) -> dict[str, Any]:
    """
    Ask lifecycle manager to synthesize a driver directly from an API spec URL.
    Returns the DriverState-like dict (including artifact path).
    """
    state = await manager.request_synthesis(driver_name=name, api_spec_url=spec_url)
    return state.model_dump() if hasattr(state, "model_dump") else dict(state)


async def _discover_with_simula(
    driver_name: str,
    docs: list[str],
    exemplars: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Call Simula to discover/spec a new capability and return an artifact module path + class.
    Expects Simula to respond with {"artifact_path": "...", "class_name": "...", "capability": "..."}.
    """
    client = await get_http_client()
    path = getattr(ENDPOINTS, "SIMULA_DISCOVERY", "/simula/jobs/discovery")
    payload = {
        "driver_name": driver_name,
        "doc_urls": docs,
        "exemplars": exemplars,
        "requirements": {
            "produce_openapi_spec": True,
            "produce_driver_module": True,
            "produce_evaluators": True,
        },
    }
    r = await client.post(path, json=payload)
    r.raise_for_status()
    return r.json()


async def _load_and_register(
    registry: DriverRegistry,
    driver_name: str,
    artifact_path: str,
    class_name: str,
) -> None:
    registry.load_and_register_driver(
        driver_name=driver_name,
        module_path=artifact_path,
        class_name=class_name,
    )


async def _request_unity_playbook(
    decision_id: str,
    capability: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Ask Atune (who owns Unity) for a playbook/constraints for the new capability.
    """
    client = await get_http_client()
    escalate_path = getattr(ENDPOINTS, "ATUNE_ESCALATE", "/atune/escalate")
    req = {
        "decision_id": decision_id,
        "type": "playbook_request",
        "capability": capability,
        "context": context,
    }
    r = await client.post(escalate_path, json=req)
    r.raise_for_status()
    return r.json()


async def _post_ab_trial(
    # highlight-start
    challenger: str,
    capability: str,
    decision_id: str,
    gap: CapabilityGapEvent,
    # highlight-end
) -> dict[str, Any]:
    """
    Kick off A/B (or shadow-only) to compare the challenger vs incumbent.
    """
    client = await get_http_client()
    ab_path = getattr(ENDPOINTS, "AXON_AB_RUN", "/ab/run")
    # highlight-start
    # Construct a valid AxonIntent for the A/B trial.
    # Use the first exemplar from the gap event to form the parameters.
    params = {}
    if gap.exemplars:
        # Assuming exemplars have a 'request' field with the parameters
        params = (gap.exemplars[0].model_dump().get("request") or {}).get("params", {})

    intent = AxonIntent(
        intent_id=str(uuid.uuid4()),
        purpose=f"A/B trial for new driver '{challenger}' addressing capability gap.",
        target_capability=capability,
        params=params,
        risk_tier="low",
        constraints={"dry_run": True},
        policy_trace={"decision_id": decision_id, "source": "probecraft_intake"},
        rollback_contract={},
    )
    headers = {"x-decision-id": decision_id}
    r = await client.post(ab_path, json=intent.model_dump(), headers=headers)
    # highlight-end
    r.raise_for_status()
    return r.json()


def _derive_driver_name(gap: CapabilityGapEvent) -> str:
    if gap.missing_capability:
        return gap.missing_capability.replace(".", "_") + "_driver"
    if gap.failing_capability:
        return gap.failing_capability.replace(".", "_") + "_v2_driver"
    return "autogen_driver"


# --- API surface -------------------------------------------------------------


@router.post("/probecraft/intake")
async def probecraft_intake(
    gap: CapabilityGapEvent,
    x_budget_ms: str | None = Header(default=None, alias="x-budget-ms"),
    x_deadline_ts: str | None = Header(default=None, alias="x-deadline-ts"),
    x_decision_id: str | None = Header(default=None, alias="x-decision-id"),
) -> dict[str, Any]:
    """
    Intake of a CapabilityGapEvent:
      1) Synthesize driver (direct from spec or via Simula discovery).
      2) Register driver as 'testing'.
      3) Request Unity playbook constraints via Atune.
      4) Launch shadow/A-B against incumbent.
      5) Return a structured result Atune can merge (constraints/rollback template + driver label).
    """
    decision_id = x_decision_id or gap.decision_id
    headers = {}
    if x_budget_ms:
        headers["x-budget-ms"] = x_budget_ms
    if x_deadline_ts:
        headers["x-deadline-ts"] = x_deadline_ts
    if x_decision_id:
        headers["x-decision-id"] = x_decision_id

    manager = (
        DriverLifecycleManager()
    )  # assume DI available in your project; direct construct otherwise
    registry = DriverRegistry()
    ScorecardManager()
    attestor = AttestationManager()

    # 1) Synthesis path
    driver_name = _derive_driver_name(gap)
    artifact_path = None
    class_name = None
    realized_capability = (
        gap.missing_capability or gap.failing_capability or gap.meta.get("capability", "")
    )

    try:
        if gap.api_spec_url:
            state = await _synthesize_from_spec(manager, driver_name, gap.api_spec_url)
            artifact_path = state.get("artifact_path")
            class_name = state.get("class_name") or "".join(
                w.capitalize() for w in driver_name.split("_")
            )
            realized_capability = state.get("capability") or realized_capability
        else:
            disc = await _discover_with_simula(
                driver_name=driver_name,
                docs=gap.doc_urls,
                exemplars=[e.model_dump() for e in gap.exemplars],
            )
            artifact_path = disc.get("artifact_path")
            class_name = disc.get("class_name")
            realized_capability = disc.get("capability") or realized_capability

        if not artifact_path or not class_name:
            raise ValueError("discovery_or_synthesis_missing_artifact")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"synthesis_failed: {e}")

    # 2) Register & set status = testing
    try:
        await _load_and_register(registry, driver_name, artifact_path, class_name)
        manager.update_driver_status(driver_name, DriverStatus.testing)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"driver_register_failed: {e}")

    # 3) Unity playbook (constraints + rollback template)
    playbook = {}
    try:
        playbook = await _request_unity_playbook(
            decision_id=decision_id,
            capability=realized_capability,
            context={
                "whytrace_barcodes": gap.whytrace_barcodes,
                "postcondition_violations": [p.model_dump() for p in gap.postcondition_violations],
                "regret": gap.regret.model_dump() if gap.regret else None,
                "source": gap.source,
            },
        )
    except Exception as e:
        # Non-fatal; Atune can still escalate later. Return empty playbook to force cautious defaults.
        playbook = {"warning": f"playbook_request_failed: {e}"}

    # 4) Start shadow/A-B
    ab_result = {}
    try:
        ab_result = await _post_ab_trial(
            # highlight-start
            challenger=driver_name,
            capability=realized_capability,
            decision_id=decision_id,
            gap=gap,
            # highlight-end
        )
    except Exception as e:
        ab_result = {"warning": f"ab_start_failed: {e}"}

    # 5) Attestation binding (artifact hash → capability)
    try:
        artifact_hash = attestor.compute_artifact_hash(artifact_path)
        attestor.bind_artifact_to_capability(
            driver_name=driver_name,
            capability=realized_capability,
            artifact_hash=artifact_hash,
        )
    except Exception as e:
        # Non-fatal; Autoroll should refuse promotion without a valid binding.
        ab_result["attestation_warning"] = f"binding_failed: {e}"

    # Respond with structured envelope Atune can merge into constraints/rollback synth
    return {
        "status": "ok",
        "decision_id": decision_id,
        "driver": {
            "name": driver_name,
            "artifact_path": artifact_path,
            "class_name": class_name,
            "capability": realized_capability,
            "status": "testing",
        },
        "playbook": playbook,
        "ab": ab_result,
    }
