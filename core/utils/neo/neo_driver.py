# db.py
import os

from dotenv import load_dotenv
from neo4j import AsyncDriver, AsyncGraphDatabase

load_dotenv(dotenv_path="D:/EcodiaOS/config/.env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver: AsyncDriver | None = None


async def init_driver() -> None:
    """Initialize the Neo4j AsyncDriver once for the app lifespan."""
    global driver

    if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
        raise OSError(
            "NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set in the environment.",
        )

    if driver is None:
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


async def close_driver() -> None:
    """Close the Neo4j driver on app shutdown."""
    global driver
    if driver is not None:
        await driver.close()
        driver = None


def get_driver() -> AsyncDriver:
    """
    Return the active Neo4j AsyncDriver instance.
    Must call init_driver() before using this.
    """
    if driver is None:
        raise RuntimeError("Neo4j driver is not initialized. Call init_driver() at startup.")
    return driver
