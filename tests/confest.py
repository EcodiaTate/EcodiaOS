import httpx
import pytest


# 1) stable env for tests
@pytest.fixture(scope="session", autouse=True)
def _simula_env(tmp_path_factory, monkeypatch):
    art = tmp_path_factory.mktemp("sim_artifacts")
    monkeypatch.setenv("SIMULA_ARTIFACTS_ROOT", str(art))
    monkeypatch.setenv("DEV", "1")  # keep dev-only routes/features on
    monkeypatch.setenv("QORA_API_KEY", "dev")
    yield


# 2) route httpx client to the in-process ASGI app
@pytest.fixture(autouse=True)
def _patch_http_client(monkeypatch):
    from app import app  # your FastAPI instance

    async def fake_get_http_client():
        transport = httpx.ASGITransport(app=app)
        # base_url is arbitrary but must be set for ASGITransport
        return httpx.AsyncClient(base_url="http://testserver", transport=transport, timeout=10.0)

    # IMPORTANT: path must match where the app imports it
    monkeypatch.setattr("core.utils.net_api.get_http_client", fake_get_http_client, raising=True)
    yield
