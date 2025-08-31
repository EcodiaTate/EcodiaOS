# systems/simula/code_sim/fuzz/hypo_driver.py
from __future__ import annotations

import os
import tempfile

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

_TEMPLATE = """
import importlib, inspect, builtins, pytest
try:
    import hypothesis, hypothesis.strategies as st
except Exception:
    hypothesis = None

MOD_PATH = {mod_path!r}
FUNC_NAME = {func_name!r}

@pytest.mark.skipif(hypothesis is None, reason="hypothesis not installed")
def test_fuzz_smoke():
    m = importlib.import_module(MOD_PATH)
    fn = getattr(m, FUNC_NAME)
    sig = inspect.signature(fn)
    # Heuristic: support up to 2 positional args with common primitives
    @hypothesis.given(st.one_of(st.none(), st.text(), st.integers(), st.floats(allow_nan=False)),
                      st.one_of(st.none(), st.text(), st.integers(), st.floats(allow_nan=False)))
    def _prop(a, b):
        params = list(sig.parameters.values())
        args = []
        if len(params) >= 1 and params[0].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            args.append(a)
        if len(params) >= 2 and params[1].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            args.append(b)
        try:
            fn(*args[:len(params)])
        except Exception:
            # property: should not catastrophically fail for arbitrary inputs
            pytest.fail("fuzz-triggered exception")
    _prop()
"""


async def run_hypothesis_smoke(
    mod_path: str,
    func_name: str,
    *,
    timeout_sec: int = 600,
) -> tuple[bool, dict]:
    tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_fuzz_test.py")
    tf.write(_TEMPLATE.format(mod_path=mod_path, func_name=func_name))
    tf.flush()
    tf.close()
    async with DockerSandbox(seed_config()).session() as sess:
        cmd = ["bash", "-lc", f"pytest -q {tf.name} || true"]
        out = await sess._run_tool(cmd, timeout=timeout_sec)
        ok = out.get("returncode", 0) == 0 and "failed" not in (out.get("stdout") or "")
        try:
            os.unlink(tf.name)
        except Exception:
            pass
        return ok, out
