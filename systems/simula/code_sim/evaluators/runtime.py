# systems/simula/code_sim/evaluators/runtime.py
from __future__ import annotations


def run(objective: dict, sandbox_session) -> dict:
    """
    FIX: Changed function signature from 'step' to 'objective' to match the caller.
    """
    runtime = objective.get("runtime", {})
    imports: list[str] = runtime.get("import_modules", ["systems", "systems.synk", "systems.axon"])
    cmds: list[list[str]] = runtime.get("commands", [])

    import_ok = True
    import_logs: list[str] = []
    for mod in imports:
        rc, out = sandbox_session.run(
            ["python", "-c", f"import importlib; importlib.import_module('{mod}'); print('OK')"],
            timeout=120,
        )
        ok = (rc == 0) and ("OK" in out)
        import_ok &= ok
        import_logs.append(f"{'OK' if ok else 'FAIL'} import {mod}")

    cmd_ok = True
    cmd_logs: list[str] = []
    for cmd in cmds:
        rc, out = sandbox_session.run(cmd, timeout=300)
        ok = rc == 0
        cmd_ok &= ok
        cmd_logs.append(f"{'OK' if ok else 'FAIL'} {' '.join(cmd)}")

    return {
        "start_ok": import_ok and cmd_ok,
        "health_ok": import_ok,
        "details": {"imports": import_logs, "commands": cmd_logs},
    }
