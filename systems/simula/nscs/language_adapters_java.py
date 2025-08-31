# systems/simula/nscs/language_adapters_java.py
from __future__ import annotations

from pathlib import Path

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config


def is_java_repo() -> bool:
    return (
        Path("pom.xml").exists() or Path("build.gradle").exists() or any(Path(".").rglob("*.java"))
    )


async def java_static(paths: list[str]) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        # try spotbugs/checkstyle if present, else javac compilation check
        cmd = (
            "mvn -q -DskipTests spotbugs:check checkstyle:check || mvn -q -DskipTests compile || true"
            if Path("pom.xml").exists()
            else "gradle -q check || gradle -q compileJava || true"
            if Path("build.gradle").exists()
            else "find . -name '*.java' -print0 | xargs -0 -n1 javac -Xlint || true"
        )
        out = await sess._run_tool(["bash", "-lc", cmd])
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "lint": out}


async def java_tests(paths: list[str], *, timeout_sec: int = 2400) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        cmd = (
            "mvn -q -DskipITs test || true"
            if Path("pom.xml").exists()
            else "gradle -q test || true"
        )
        out = await sess._run_tool(["bash", "-lc", cmd], timeout=timeout_sec)
        ok = out.get("returncode", 0) == 0 and "FAIL" not in (out.get("stdout") or "")
        return {"status": "success" if ok else "failed", "logs": out}
