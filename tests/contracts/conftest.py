# tests/contracts/conftest.py
from collections.abc import AsyncGenerator

import httpx
import pytest
import respx

# The base URL must use the service name 'api' from the docker-compose.test.yml file,
# as this is the hostname within the Docker network.
API_BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    A session-scoped HTTP client for making requests to the EcodiaOS API
    running inside the Docker test environment.
    """
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture
async def respx_router() -> AsyncGenerator[respx.MockRouter, None]:
    """
    A fixture that provides a respx mock router, allowing tests to intercept
    and inspect HTTP requests made between services.
    """
    async with respx.mock(base_url=API_BASE_URL) as mock:
        yield mock
