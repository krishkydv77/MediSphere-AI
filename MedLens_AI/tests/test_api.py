import pytest
pytest.importorskip("langgraph")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_reject_unsupported_file():
    res = client.post("/api/analyze", files={"file": ("malware.exe", b"no", "application/octet-stream")})
    assert res.status_code == 415
