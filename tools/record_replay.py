"""Record a demo session for the replay fallback (M5 demo runbook).

Drives one scripted session through the web API in-process (the same calls the
interface makes) and saves every state the interface would show, plus the signed
ticket and the reveal, to ``data/demo/replays/<name>.json``. During a demo,
Shift+R in the interface plays the recording back frame by frame (right arrow or
space: next; left arrow: back; Escape: leave), with no engine, simulator or
network call; ``?replay=<name>`` opens it directly.

    python tools/record_replay.py                       # offline agent
    DIFFERENTIAL_API_KEY=... python tools/record_replay.py --mode live --name demo_live

Record the live version during rehearsal, so the fallback shows the same agent
text the audience would have seen.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULTS = {"circuit_id": "channel_strip", "fault": "C105:high_esr", "seed": 7,
            "complaint": "Loud hum on both outputs since it was moved, and it sounds a bit thin."}


def record(name: str, mode: str, circuit_id: str, fault: str, seed: int, complaint: str,
           max_steps: int = 25) -> Path:
    from fastapi.testclient import TestClient

    from differential.app.server import app
    from differential.config import REPLAY_DIR

    c = TestClient(app)
    frames: list[dict[str, Any]] = []

    def keep(caption: str, st: dict[str, Any]) -> dict[str, Any]:
        frames.append({"caption": caption, "state": st})
        return st

    st = keep("A simulated unit with a hidden fault is ready.",
              c.post("/api/sessions", json={"circuit_id": circuit_id, "fault": fault, "seed": seed,
                                            "mode": mode}).json())
    sid = st["session_id"]
    st = keep(f"The technician describes the complaint: “{complaint}”",
              c.post(f"/api/sessions/{sid}/messages", json={"text": complaint}).json()["state"])
    for _ in range(max_steps):
        p = st.get("pending")
        if not p or p.get("stop"):
            break
        if p.get("blocked") == "owner_approval":
            st = keep("The technician records the owner's approval for removing parts.",
                      c.post(f"/api/sessions/{sid}/approve_removal",
                             json={"note": "owner agreed"}).json()["state"])
            continue
        if p.get("blocked"):
            pts = [d["tp"] for d in p.get("discharge_points", [])]
            st = keep("The technician discharges the supply and records a reading at every "
                      "high-voltage point.",
                      c.post(f"/api/sessions/{sid}/discharge",
                             json={"readings": dict.fromkeys(pts, 0.4)}).json()["state"])
            continue
        key = p["key"]
        st = keep(f"Measured {p.get('what', key)} at {p.get('test_point') or p.get('part') or key}.",
                  c.post(f"/api/sessions/{sid}/measure", json={"key": key}).json()["state"])
    c.post(f"/api/sessions/{sid}/ticket/signoff", json={"name": "Demo technician"})
    ticket = c.get(f"/api/sessions/{sid}/ticket").json()
    reveal = c.post(f"/api/sessions/{sid}/reveal", json={}).json()
    out = {"name": name, "mode": mode, "circuit": circuit_id, "recorded": dt.datetime.now(dt.UTC).isoformat(),
           "frames": frames, "ticket": ticket, "reveal": reveal}
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    path = REPLAY_DIR / f"{name}.json"
    path.write_text(json.dumps(out, indent=1))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", default="demo")
    ap.add_argument("--mode", default="offline", choices=["offline", "live", "replay"])
    ap.add_argument("--circuit", default=DEFAULTS["circuit_id"])
    ap.add_argument("--fault", default=DEFAULTS["fault"])
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    ap.add_argument("--complaint", default=DEFAULTS["complaint"])
    args = ap.parse_args(argv)
    path = record(args.name, args.mode, args.circuit, args.fault, args.seed, args.complaint)
    n = len(json.loads(path.read_text())["frames"])
    print(f"wrote {path.relative_to(ROOT)} ({n} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
