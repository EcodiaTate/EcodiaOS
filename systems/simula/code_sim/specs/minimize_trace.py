# systems/simula/code_sim/spec/minimize_trace.py
from __future__ import annotations

import re


def minimize_pytest_stdout(stdout: str) -> list[tuple[str, int]]:
    """
    Return list of (file,line) likely causing failure, de-noising pytest output.
    """
    loc = []
    pat = re.compile(r"^(.+?):(\d+): in .+$")
    for ln in (stdout or "").splitlines():
        m = pat.match(ln.strip())
        if m:
            f, n = m.group(1), int(m.group(2))
            if "/site-packages/" in f:
                continue
            loc.append((f, n))
    return loc[:8]
