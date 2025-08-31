# core/llm/env_bootstrap.py
import os
from pathlib import Path


def _load():
    try:
        from dotenv import find_dotenv, load_dotenv  # pip install python-dotenv
    except Exception:
        return

    # Highest priority: explicit ENV_FILE
    env_file = os.getenv("ENV_FILE")
    if env_file and Path(env_file).exists():
        load_dotenv(env_file, override=False)
        return

    # Project discovery (.env in workspace root)
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)

    # Fallback to our canonical path (Windows host)
    for p in (r"D:\EcodiaOS\config\.env", r"./config/.env"):
        if Path(p).exists():
            load_dotenv(p, override=False)
            break


_load()
