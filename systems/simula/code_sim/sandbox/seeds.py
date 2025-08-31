# systems/simula/code_sim/sandbox/seeds.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

import sys

from systems.simula.config import settings

# Define the required toolchain packages. These are now managed centrally.
REQUIRED_PIP: list[str] = [
    "pytest==8.2.0",
    "ruff==0.5.6",
    "mypy==1.10.0",
    "bandit==1.7.9",
    "pytest-xdist",
    "black",
]


def seed_config() -> dict[str, object]:
    """
    Derive the sandbox configuration directly from the central settings singleton.
    """
    sbx = settings.sandbox
    return {
        "mode": sbx.mode,
        "image": sbx.image,
        "timeout_sec": sbx.timeout_sec,
        "cpus": sbx.cpus,
        "memory": sbx.memory,
        "network": sbx.network,
        "workdir": ".",  # Always operate from the repo root
        "env_allow": ["PYTHONPATH"],
        "env_set": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "SIMULA_REPO_ROOT": "/workspace",  # The path inside the container
        },
        # Persist these directories across runs for caching and performance
        "mount_rw": [".simula", ".venv", ".mypy_cache", ".pytest_cache"],
        "pip_install": sbx.pip_install or REQUIRED_PIP,
    }


async def ensure_toolchain(session) -> dict[str, str]:
    """
    Ensures a persistent toolchain in the repo's .venv/ directory.
    This logic is now robust and works for both Docker and Local sessions.
    """
    all_pkgs = session.cfg.pip_install

    # This Python script is executed inside the sandbox to bootstrap the environment
    code = (
        "import os, sys, subprocess, pathlib\n"
        "root = pathlib.Path('.').resolve()\n"
        "venv = root / '.venv'\n"
        "py_exe = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')\n"
        "def run(cmd): subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "if not py_exe.exists():\n"
        "    run([sys.executable, '-m', 'venv', str(venv)])\n"
        "run([str(py_exe), '-m', 'pip', 'install', '-U', 'pip', 'setuptools', 'wheel'])\n"
        f"run([str(py_exe), '-m', 'pip', 'install', '-U'] + {repr(all_pkgs)})\n"
        "print('VERS', 'python', '.'.join(map(str, sys.version_info[:3])))\n"
        "try:\n"
        "    from importlib.metadata import version as v\n"
        "except ImportError:\n"
        "    from importlib_metadata import version as v\n"
        "for pkg in ['pytest', 'ruff', 'mypy', 'bandit', 'black']:\n"
        "    try: print('VERS', pkg, v(pkg))\n"
        "    except Exception: print('VERS', pkg, 'missing')\n"
    )

    out = await session._run_tool([sys.executable, "-c", code], timeout=1200)

    # Extract versions from the structured stdout
    stdout = out.get("stdout", "")
    versions: dict[str, str] = {}
    for line in stdout.splitlines():
        if line.startswith("VERS "):
            parts = line.split(None, 2)
            if len(parts) == 3:
                _, name, value = parts
                versions[name] = value.strip()

    return versions
