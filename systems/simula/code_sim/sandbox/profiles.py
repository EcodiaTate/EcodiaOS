# systems/simula/code_sim/sandbox/profiles.py
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SandboxProfile:
    name: str
    xdist: bool
    nprocs: str
    mem_mb: int
    timeout_sec: int


def current_profile() -> SandboxProfile:
    return SandboxProfile(
        name=os.getenv("SIMULA_PROFILE", "balanced"),
        xdist=os.getenv("SIMULA_USE_XDIST", "1") != "0",
        nprocs=os.getenv("SIMULA_XDIST_PROCS", "auto"),
        mem_mb=int(os.getenv("SIMULA_MEM_MB", "4096")),
        timeout_sec=int(os.getenv("SIMULA_TIMEOUT", "900")),
    )
