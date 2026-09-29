"""Demo web API end to end on a simulated bench (needs trained models in data/models/)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from differential.config import DATA_DIR, MODELS_DIR

pytestmark = pytest.mark.skipif(not (MODELS_DIR / "tone" / "generative.npz").exists(),
                                reason="trained models not present")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from differential.app.server import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIFFERENTIAL_API_KEY", raising=False)


def test_catalog_endpoints(client: TestClient) -> None:
    h = client.get("/api/health").json()
    assert h["ok"] and h["default_mode"] == "offline" and not h["live_available"]
    cs = client.get("/api/circuits").json()["circuits"]
    assert {c["id"] for c in cs} >= {"channel_strip", "tone", "triode"}
    strip = next(c for c in cs if c["id"] == "channel_strip")
    assert strip["high_voltage_test_points"] > 0
    tone = client.get("/api/circuits/tone").json()
    assert tone["test_points"] and not tone["high_voltage_circuit"]
    assert all(tp["hazard"] == "lv" for tp in tone["test_points"])
    assert client.get("/api/circuits/nope").status_code == 404
    assert client.get("/schematics/tone/tone_schematic.svg").status_code == 200
    assert client.get("/schematics/tone/..%2F..%2Fpyproject.toml").status_code == 404
    assert client.get("/schematics/tone/tone.yaml").status_code == 404


def test_session_flow(client: TestClient) -> None:
    assert client.post("/api/sessions", json={"circuit_id": "tone", "mode": "live"}).status_code == 400
    st = client.post("/api/sessions", json={"circuit_id": "tone", "fault": "R301:open",
                                            "seed": 3}).json()
    sid = st["session_id"]
    assert st["mode"] == "offline" and st["readings"] == []
    r = client.post(f"/api/sessions/{sid}/messages", json={"text": "The bass is gone and it sounds thin."})
    body = r.json()
    assert r.status_code == 200 and body["reply"]["role"] == "assistant"
    pending = body["state"]["pending"]
    assert pending is not None and pending["key"]
    assert client.post(f"/api/sessions/{sid}/measure", json={"key": "dc:NOPE"}).status_code == 400
    for _ in range(12):  # measure every recommendation until the engine stops
        pending = client.get(f"/api/sessions/{sid}").json()["pending"]
        if pending is None:
            break
        r = client.post(f"/api/sessions/{sid}/measure", json={"key": pending["key"]})
        assert r.status_code == 200
    state = client.get(f"/api/sessions/{sid}").json()
    assert len(state["readings"]) >= 1 and state["belief"]
    typed = client.post(f"/api/sessions/{sid}/readings",
                        json={"key": state["readings"][0]["key"],
                              "value": state["readings"][0]["value"]})
    assert typed.status_code == 200
    d = client.post(f"/api/sessions/{sid}/discharge", json={"volts": 0.5}).json()
    assert "reply" in d
    a = client.post(f"/api/sessions/{sid}/approve_removal", json={"note": "owner agreed"}).json()
    assert a["state"]["removal_approved"] is True
    assert client.post(f"/api/sessions/{sid}/discharge", json={}).status_code == 400
    t = client.get(f"/api/sessions/{sid}/ticket").json()
    assert t["status"].startswith("draft") and t["markdown"]
    signed = client.post(f"/api/sessions/{sid}/ticket/signoff", json={"name": "Bench tech"}).json()
    assert signed["status"].startswith("signed off")
    rev = client.post(f"/api/sessions/{sid}/reveal").json()
    assert rev["revealed"]["fault"] == "R301:open"
    exp = client.get(f"/api/sessions/{sid}/export").json()
    assert exp["hidden_fault"] == "R301:open" and json.dumps(exp)
    assert client.get("/api/sessions/unknown").status_code == 404


def test_photo_upload_is_a_proposal_until_confirmed(client: TestClient) -> None:
    labels = DATA_DIR / "meter_photos" / "synthetic" / "labels.jsonl"
    if not labels.exists():
        pytest.skip("synthetic meter photos not generated")
    first = json.loads(labels.read_text().splitlines()[0])
    photo = labels.parent / first.get("file", "meter_0000.jpg")
    sid = client.post("/api/sessions", json={"circuit_id": "tone", "fault": "R301:open",
                                             "seed": 4}).json()["session_id"]
    up = client.post(f"/api/sessions/{sid}/photos",
                     files={"file": ("meter.jpg", photo.read_bytes(), "image/jpeg")}).json()
    assert "photo_id" in up and "proposal" in up
    before = client.get(f"/api/sessions/{sid}").json()["readings"]
    assert before == []  # nothing is recorded until the technician confirms
    key = client.get("/api/circuits/tone").json()["test_points"][0]["measurements"][0]["key"]
    ok = client.post(f"/api/sessions/{sid}/photos/{up['photo_id']}/confirm",
                     json={"key": key, "value": 1.0})
    assert ok.status_code == 200
    assert client.post(f"/api/sessions/{sid}/photos/nope/confirm",
                       json={"key": key, "value": 1.0}).status_code == 404
    big = client.post(f"/api/sessions/{sid}/photos",
                      files={"file": ("big.jpg", b"0" * (10 * 1024 * 1024 + 1), "image/jpeg")})
    assert big.status_code == 413


def test_recorded_sessions_replay_without_a_session(client: TestClient, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from differential.app import server

    monkeypatch.setattr(server, "REPLAY_DIR", tmp_path)
    (tmp_path / "demo.json").write_text(json.dumps({"circuit": "tone", "frames": [{"caption": "c",
                                                                                      "state": {}}]}))
    assert client.get("/api/replays").json() == {"replays": ["demo"]}
    assert client.get("/api/replays/demo").json()["circuit"] == "tone"
    assert client.get("/api/replays/missing").status_code == 404
    assert client.get("/api/replays/..%2Fsecrets").status_code == 404


def test_trainee_session_flow() -> None:
    from fastapi.testclient import TestClient

    from differential.app.server import app

    client = TestClient(app)
    st = client.post("/api/sessions", json={"circuit_id": "driver", "fault": "R505:open", "seed": 3,
                                             "trainee": True}).json()
    sid = st["session_id"]
    st = client.post(f"/api/sessions/{sid}/messages", json={"text": "No output at all."}).json()["state"]
    assert st["pending"]["withheld"] is True and st["pending"]["options"]
    key = st["pending"]["options"][0]["key"]
    assert client.post(f"/api/sessions/{sid}/guess", json={"key": "nope"}).status_code == 400
    st = client.post(f"/api/sessions/{sid}/guess", json={"key": key}).json()["state"]
    assert st["pending"].get("withheld") is None and st["trainee"]["log"][0]["guess"] == key


def test_bad_input_is_refused_cleanly(client: TestClient) -> None:
    assert client.post("/api/sessions", json={"circuit_id": "nope"}).status_code == 404
    assert client.post("/api/sessions", json={"circuit_id": "psu", "fault": "Z9:open"}).status_code == 400
    assert client.post("/api/sessions", json={"circuit_id": "psu", "mode": "root"}).status_code == 400
    sid = client.post("/api/sessions", json={"circuit_id": "psu", "mode": "offline", "seed": 1}).json()["session_id"]
    body = '{"key": "dc:TP4", "value": NaN}'
    r = client.post(f"/api/sessions/{sid}/readings", content=body,
                    headers={"content-type": "application/json"})
    assert r.status_code == 422
    r = client.post(f"/api/sessions/{sid}/discharge", content='{"volts": Infinity, "all_points": true}',
                    headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": "x" * 5000}).status_code == 422
    assert client.get(f"/api/sessions/{sid}").json()["discharge_verified"] is False
