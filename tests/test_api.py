from fastapi.testclient import TestClient
from app.main import app


def test_healthz():
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "version" in body


def test_http_probe_success():
    with TestClient(app) as client:
        r = client.post("/api/http/probe", json={"url": "https://example.com", "method": "GET", "timeout_sec": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["url"].startswith("https://")
    assert data["latency_ms"] >= 0
    assert "success" in data


def test_tcp_probe_timeout():
    # Port unlikely to accept connections on localhost; low timeout to keep test fast
    payload = {"host": "127.0.0.1", "port": 9, "timeout_sec": 0.2}
    with TestClient(app) as client:
        r = client.post("/api/ping/tcp", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["host"] == "127.0.0.1"
    assert data["success"] in (True, False)


def test_config_state_and_add_delete_tcp():
    with TestClient(app) as client:
        r = client.get("/api/config/state")
        assert r.status_code == 200
        tid = f"test-tcp-1"
        add = client.post("/api/config/tcp", json={"id": tid, "host": "1.1.1.1", "port": 443, "interval_sec": 5.0})
        assert add.status_code == 200
        after = add.json()
        assert any(t["id"] == tid for t in after["tcp"])
        dele = client.delete(f"/api/config/tcp/{tid}")
        assert dele.status_code == 200
        final = dele.json()
        assert all(t["id"] != tid for t in final["tcp"])


def test_metrics_recent():
    with TestClient(app) as client:
        # Seed one HTTP probe
        client.post("/api/http/probe", json={"url": "https://example.com", "method": "HEAD", "timeout_sec": 5})
        r = client.get("/api/metrics/recent?limit=10")
    assert r.status_code == 200
    items = r.json()["items"]
    assert isinstance(items, list)

