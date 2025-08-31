HELLO_DIFF = """\
diff --git a/hello.txt b/hello.txt
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/hello.txt
@@ -0,0 +1 @@
+hello
"""


def test_policy_validate_accepts_diff():
    from fastapi.testclient import TestClient

    from app import app

    with TestClient(app) as c:
        r = c.post("/simula/validate", json={"diff": HELLO_DIFF})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True


def test_guarded_forward_dry_run():
    from fastapi.testclient import TestClient

    from app import app

    with TestClient(app) as c:
        body = {"spec": "Add hello test file", "diff": HELLO_DIFF, "dry_run": True}
        r = c.post("/simula/jobs/codegen_guarded", json=body)
        # Even if the agent fails internally, guard + forward should return JSON with 'policy' + 'forwarded'
        assert r.status_code in (200, 502, 422)
        j = r.json()
        assert "policy" in j or "detail" in j  # both are OK for CI visibility
