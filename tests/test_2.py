def test_list_tools_names_only():
    from fastapi.testclient import TestClient

    from app import app  # adjust if your ASGI is elsewhere

    with TestClient(app) as c:
        r = c.get("/synapse/tools?names_only=1")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert isinstance(data.get("names"), list)
        assert "write_file" in data["names"]
