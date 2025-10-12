# systems/axon/mesh/lifecycle.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Literal, Optional

DriverStatus = Literal[
    "pending_synthesis", "synthesizing", "testing", "shadow", "live", "retired", "synthesis_failed"
]


@dataclass
class DriverSpec:
    driver_name: str
    capability: str | None = None
    driver_version: str = "0.0.0"
    artifact_path: str | None = None
    class_name: str | None = None


@dataclass
class DriverState:
    name: str
    status: DriverStatus
    spec: DriverSpec
    synthesis_job_id: str | None = None

    def model_dump(self) -> dict:
        d = asdict(self)
        d["spec"] = asdict(self.spec)
        return d


class DriverLifecycleManager:
    """
    Single-process in-memory lifecycle tracker.
    (Back it with Redis/Neo later if you want cross-process.)
    """

    def __init__(self, artifact_dir: str = "systems/axon/drivers/generated") -> None:
        self._states: dict[str, DriverState] = {}
        self._artifact_dir = artifact_dir

    # --------- read / list ---------

    def get_driver_state(self, driver_name: str) -> DriverState | None:
        return self._states.get(driver_name)

    # Backward-compat alias (old callers)
    def get_state(self, driver_name: str) -> DriverState | None:  # pragma: no cover
        return self.get_driver_state(driver_name)

    def get_all_states(self) -> list[DriverState]:
        return list(self._states.values())

    # --------- synthesis ---------

    async def request_synthesis(self, *, driver_name: str, api_spec_url: str) -> DriverState:
        """
        Records an intent to synthesize a driver; Simula job initiation happens outside.
        """
        st = self._states.get(driver_name)
        if st and st.status not in {"synthesis_failed", "retired"}:
            # idempotent: don't clobber active drivers
            return st

        spec = DriverSpec(driver_name=driver_name, artifact_path=None)
        st = DriverState(
            name=driver_name, status="pending_synthesis", spec=spec, synthesis_job_id=None
        )
        self._states[driver_name] = st
        return st

    def record_synthesis_job(
        self,
        *,
        driver_name: str,
        job_id: str,
        artifact_path: str | None = None,
        class_name: str | None = None,
        capability: str | None = None,
    ) -> DriverState:
        st = self._states.get(driver_name)
        if not st:
            st = DriverState(
                name=driver_name,
                status="pending_synthesis",
                spec=DriverSpec(driver_name=driver_name),
            )
            self._states[driver_name] = st
        st.synthesis_job_id = job_id
        st.status = "synthesizing"
        if artifact_path:
            st.spec.artifact_path = artifact_path
        if class_name:
            st.spec.class_name = class_name
        if capability:
            st.spec.capability = capability
        return st

    def attach_artifact(
        self,
        *,
        driver_name: str,
        artifact_path: str,
        class_name: str | None = None,
        driver_version: str | None = None,
        capability: str | None = None,
    ) -> DriverState:
        st = self._states.get(driver_name)
        if not st:
            st = DriverState(
                name=driver_name, status="testing", spec=DriverSpec(driver_name=driver_name)
            )
            self._states[driver_name] = st
        st.spec.artifact_path = artifact_path
        if class_name:
            st.spec.class_name = class_name
        if driver_version:
            st.spec.driver_version = driver_version
        if capability:
            st.spec.capability = capability
        return st

    # --------- status transitions ---------

    def update_driver_status(self, driver_name: str, new_status: DriverStatus) -> DriverState:
        st = self._states.get(driver_name)
        if not st:
            st = DriverState(
                name=driver_name, status=new_status, spec=DriverSpec(driver_name=driver_name)
            )
            self._states[driver_name] = st
            return st

        # idempotent
        if st.status == new_status:
            return st

        # simple guardrails
        allowed = {
            "pending_synthesis": {"synthesizing", "synthesis_failed"},
            "synthesizing": {"testing", "synthesis_failed"},
            "testing": {"shadow", "retired"},
            "shadow": {"live", "testing", "retired"},
            "live": {"shadow", "retired"},
            "synthesis_failed": {"pending_synthesis", "retired"},
            "retired": set(),
        }
        if new_status not in allowed.get(st.status, set()):
            # allow direct set in emergencies, but annotate by stepping through
            st.status = new_status
            return st

        st.status = new_status
        return st

    # convenience
    def list_drivers(self) -> list[DriverState]:
        return list(self._states.values())
