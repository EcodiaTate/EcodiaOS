# db.py (container-safe)
from __future__ import annotations

import os
from typing import Optional, Tuple

from neo4j import AsyncDriver, AsyncGraphDatabase

# --- Make dotenv optional & pathless ---
try:
    from dotenv import find_dotenv, load_dotenv  # type: ignore
except Exception:  # not installed in containers = fine
    load_dotenv = None
    find_dotenv = None

# Load a .env if available (local dev), but don't require it in containers
if load_dotenv:
    try:
        # Respect an explicit DOTENV_PATH if provided; otherwise just look up the tree.
        dotenv_path = os.getenv("DOTENV_PATH")
        load_dotenv(dotenv_path or (find_dotenv() if find_dotenv else None))
    except Exception:
        pass


def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _get_env(*names: str, default: str | None = None) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v is not None:
            return v
    return default


# Accept common variants used across services
NEO4J_URI = _get_env("NEO4J_URI", "NEO4J_URL") or "bolt://neo4j:7687"
NEO4J_USER = _get_env("NEO4J_USER", "NEO4J_USERNAME")
NEO4J_PASSWORD = _get_env("NEO4J_PASSWORD", "NEO4J_PASS")
NEO4J_ENCRYPTION = _get_bool("NEO4J_ENCRYPTION", default=False)
NEO4J_TRUST_ALL_CERTS = _get_bool("NEO4J_TRUST_ALL_CERTS", default=False)

driver: AsyncDriver | None = None


def _build_auth() -> tuple[str, str] | None:
    # If both set, use them; if neither set, connect without auth (e.g., NEO4J_AUTH=none).
    # If only one is set, that's a misconfiguration.
    if NEO4J_USER and NEO4J_PASSWORD:
        return (NEO4J_USER, NEO4J_PASSWORD)
    if NEO4J_USER or NEO4J_PASSWORD:
        raise OSError("Provide both NEO4J_USER and NEO4J_PASSWORD, or neither (for auth=none).")
    return None  # no auth


async def init_driver() -> None:
    """Initialize the Neo4j AsyncDriver once for the app lifespan."""
    global driver
    if driver is not None:
        return

    auth = _build_auth()

    # Prefer URI schemes for encryption (neo4j+s / bolt+s), but allow env override for dev.
    # NOTE: 'encrypted' kw still works for driver v5; the URI scheme also controls TLS.
    driver_config = {}
    if "bolt://" in NEO4J_URI or "neo4j://" in NEO4J_URI:
        driver_config["encrypted"] = (
            NEO4J_ENCRYPTION  # False for local dev unless you've enabled TLS
        )

    # Optional: trust all certs for local self-signed TLS (dev only)
    if NEO4J_TRUST_ALL_CERTS:
        driver_config["trust"] = "TRUST_ALL_CERTIFICATES"  # type: ignore[arg-type]

    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=auth, **driver_config)


async def close_driver() -> None:
    """Close the Neo4j driver on app shutdown."""
    global driver
    if driver is not None:
        await driver.close()
        driver = None


def get_driver() -> AsyncDriver:
    """Return the active Neo4j AsyncDriver instance. Call init_driver() before using this."""
    if driver is None:
        raise RuntimeError("Neo4j driver is not initialized. Call init_driver() at startup.")
    return driver
