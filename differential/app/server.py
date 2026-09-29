"""Demo web app: FastAPI backend + a no-build single-page front end (``static/``).

Run: ``make demo`` (or ``python -m differential.app.server``), then open
http://localhost:8000. Modes: ``offline`` (default without a key), ``live``
(``DIFFERENTIAL_API_KEY`` set), ``replay`` (cached responses / recorded sessions).

A session is one diagnosis of one unit on a *simulated bench*: a hidden fault is
drawn (or chosen for a scripted demo) and simulated with ngspice; every
"Measure" click returns what an instrument would read on that unit. Readings can
also be typed, or read from a meter photo and confirmed.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, FiniteFloat

from differential import __version__
from differential.agent.agent import DifferentialAgent, Turn
from differential.agent.format import fault_label, fmt_reading
from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import CIRCUITS_DIR, REPLAY_DIR, app_mode, llm_settings
from differential.instruments.simulated import SimulatedBench
from differential.safety.hazards import circuit_has_hv, hazard
from differential.sim.observables import KIND_INSTRUMENT, KIND_LABEL

STATIC = Path(__file__).resolve().parent / "static"
MAX_PHOTO_BYTES = 10 * 1024 * 1024

MAX_SESSIONS = 200  # a bench runs a handful; the oldest is dropped beyond this

app = FastAPI(title="Differential", version=__version__)
_sessions: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


@app.exception_handler(RequestValidationError)
async def _invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the input: a NaN in the body cannot be written back as JSON (it
    would turn a refused request into a server error), and long inputs are not repeated."""
    detail = [{k: e[k] for k in ("loc", "msg", "type") if k in e} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


# ---------------------------------------------------------------- helpers
def _session(sid: str) -> dict[str, Any]:
    s = _sessions.get(sid)
    if s is None:
        raise HTTPException(404, "unknown session")
    return s


def _turn(t: Turn) -> dict[str, Any]:
    return {"role": t.role, "text": t.text, "t": t.t, "meta": t.meta}


def _state(s: dict[str, Any]) -> dict[str, Any]:
    agent: DifferentialAgent = s["agent"]
    tb = agent.tb
    e = tb.engine
    belief = tb.t_get_belief()
    pending = None
    rec = next((c.result for c in reversed(tb.calls) if c.name == "recommend_measurement"), None)
    if rec and not rec.get("stop") and agent.pending_key in (rec.get("key"), "discharge", "approval",
                                                               "supervisor"):
        pending = rec
    if agent.pending_key == "guess" and agent.withheld is not None:
        # trainee mode: the recommendation stays hidden until the trainee commits a choice
        pending = {"stop": False, "withheld": True, "key": None, "options": tb.trainee_options(),
                   "cost": None}
    banner = None
    if pending and pending.get("blocked") == "supervisor":
        banner = {"level": "danger", "title": "Trainee mode: a supervisor must be named",
                  "lines": [pending["next_step"], *pending["safety"]["lines"]]}
    elif pending and pending.get("blocked") == "owner_approval":
        banner = {"level": "warning", "title": "Owner's approval needed before removing parts",
                  "lines": [str(pending.get("next_step", "")).replace(" (approve_part_removal)", "")]}
    elif pending and (pending.get("high_voltage") or pending.get("blocked")):
        lines = (pending.get("safety") or {}).get("lines", [])
        banner = {"level": "danger", "title": lines[0] if lines else "High voltage",
                  "lines": lines[1:]}
    elif pending and (pending.get("safety") or {}).get("hv_inside"):
        lines = pending["safety"]["lines"]
        banner = {"level": "warning", "title": "High voltage inside: high-voltage supply present",
                  "lines": lines}
    readings = [{"step": r.step, "key": r.key, "value": r.value,
                 "text": fmt_reading(e._obs[r.key].kind, r.value), "source": r.source,
                 "cost": r.cost} for r in e.readings]
    return {
        "session_id": s["id"],
        "circuit": tb.circuit_id,
        "mode": agent.mode,
        "belief": belief,
        "top_hypotheses": [{"fault": h, "label": fault_label(h), "p": round(p, 4)}
                           for h, p in e.top_hypotheses(8)],
        "history": agent.history_snapshots,
        "pending": pending,
        "discharge_verified": tb.discharge_verified,
        "discharge_readings": dict(tb.discharge_readings),
        "removal_approved": tb.removal_approved,
        "trainee": ({"supervisor": tb.supervisor, "log": tb.trainee_log} if tb.trainee else None),
        "banner": banner,
        "readings": readings,
        "transcript": [_turn(t) for t in agent.turns],
        "revealed": s.get("revealed"),
    }


def _circuit_payload(cid: str) -> dict[str, Any]:
    c = get_circuit(cid)
    tp_json = CIRCUITS_DIR / cid / f"{cid}_testpoints.json"
    coords = json.loads(tp_json.read_text()) if tp_json.exists() else {}
    tps = []
    for tp in c.test_points:
        hz = hazard(cid, tp.id)
        tps.append({"id": tp.id, "name": tp.name, "stage": tp.stage, "hint": tp.hint,
                    "measurements": [{"key": f"{k}:{tp.id}", "kind": k, "label": KIND_LABEL[k],
                                      "instrument": KIND_INSTRUMENT[k]} for k in tp.measurements],
                    "hazard": hz.level, "normal_max_v": hz.normal_max_v,
                    "worst_case_v": hz.worst_case_v})
    return {
        "id": cid, "name": c.name, "description": c.description,
        "stages": [{"id": s, "name": n} for s, n in c.stages],
        "test_points": tps,
        "parts": [{"ref": p.ref, "kind": p.kind, "value": p.value, "stage": p.stage}
                  for p in c.components],
        "high_voltage_circuit": circuit_has_hv(cid),
        "schematic": {"light": f"/schematics/{cid}/{cid}_schematic.svg",
                      "dark": f"/schematics/{cid}/{cid}_schematic_dark.svg",
                      "testpoints": coords},
    }


# ------------------------------------------------------------------ API
KEY = Field(max_length=40)  # measurement keys such as "dc:TP12"


class NewSession(BaseModel):
    circuit_id: str = Field(COMPOSITE_ID, max_length=40)
    mode: str | None = Field(None, max_length=10)
    fault: str | None = Field(None, max_length=80)  # hidden fault for a scripted demo; random if omitted
    seed: int | None = Field(None, ge=0, le=2**63 - 1)
    trainee: bool = False


class Guess(BaseModel):
    key: str = KEY


class Supervisor(BaseModel):
    name: str = Field(max_length=200)


class Message(BaseModel):
    text: str = Field(max_length=4000)


class Reading(BaseModel):
    key: str = KEY
    value: FiniteFloat


class Measure(BaseModel):
    key: str = KEY


class Discharge(BaseModel):
    volts: FiniteFloat | None = None
    readings: dict[str, FiniteFloat] | None = Field(None, max_length=40)
    all_points: bool = False


class Approval(BaseModel):
    note: str = Field("", max_length=500)


class SignOff(BaseModel):
    name: str = Field(max_length=200)


@app.get("/api/health")
def health() -> dict[str, Any]:
    s = llm_settings()
    return {"ok": True, "version": __version__, "default_mode": app_mode(),
            "live_available": s.live, "model": s.model}


@app.get("/api/circuits")
def circuits() -> dict[str, Any]:
    out = []
    for cid in [COMPOSITE_ID, *BLOCK_IDS]:
        c = get_circuit(cid)
        out.append({"id": cid, "name": c.name, "components": len(c.components),
                    "test_points": len(c.test_points),
                    "high_voltage_test_points": sum(hazard(cid, tp.id).high_voltage
                                                    for tp in c.test_points)})
    return {"circuits": out}


@app.get("/api/circuits/{cid}")
def circuit(cid: str) -> dict[str, Any]:
    try:
        return _circuit_payload(cid)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/schematics/{cid}/{name}")
def schematic(cid: str, name: str) -> FileResponse:
    path = (CIRCUITS_DIR / cid / name).resolve()
    if CIRCUITS_DIR.resolve() not in path.parents or path.suffix not in (".svg", ".png", ".json"):
        raise HTTPException(404, "not found")
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path)


def _pick_fault(cid: str, rng: np.random.Generator) -> str:
    from differential.engine.bundle import cached_bundle

    sm = cached_bundle(cid).symptom_model
    hyps = [h for h in cached_bundle(cid).hypotheses if h != "healthy"]
    if sm is not None and sm.symptomatic_rate is not None:
        hyps = [h for h, r in zip(sm.hypotheses, sm.symptomatic_rate, strict=True)
                if h != "healthy" and r >= 0.5]
    return str(hyps[int(rng.integers(len(hyps)))])


@app.post("/api/sessions")
def new_session(req: NewSession) -> dict[str, Any]:
    mode = req.mode or app_mode()
    if req.circuit_id not in (COMPOSITE_ID, *BLOCK_IDS):
        raise HTTPException(404, f"unknown circuit {req.circuit_id!r}")
    if mode not in ("offline", "live", "replay"):
        raise HTTPException(400, "mode must be offline, live or replay")
    if mode == "live" and not llm_settings().live:
        raise HTTPException(400, "live mode needs DIFFERENTIAL_API_KEY; use offline or replay")
    rng = np.random.default_rng(req.seed)
    if req.fault is not None:
        from differential.engine.bundle import cached_bundle

        if req.fault not in cached_bundle(req.circuit_id).hypotheses:
            raise HTTPException(400, f"unknown fault {req.fault!r}")
    fault = req.fault or _pick_fault(req.circuit_id, rng)
    unit = int(rng.integers(0, 10_000))
    bench = SimulatedBench.simulate(req.circuit_id, fault, unit_index=unit)
    agent = DifferentialAgent(req.circuit_id, mode=mode, instrument=bench, trainee=req.trainee)
    sid = uuid.uuid4().hex[:12]
    with _lock:
        while len(_sessions) >= MAX_SESSIONS:
            _sessions.pop(next(iter(_sessions)))
        _sessions[sid] = {"id": sid, "agent": agent, "bench": bench, "photos": {},
                          "revealed": None}
    return _state(_sessions[sid])


@app.get("/api/sessions/{sid}")
def get_state(sid: str) -> dict[str, Any]:
    return _state(_session(sid))


@app.post("/api/sessions/{sid}/messages")
def post_message(sid: str, msg: Message) -> dict[str, Any]:
    s = _session(sid)
    reply = s["agent"].user_message(msg.text)
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/measure")
def measure(sid: str, req: Measure) -> dict[str, Any]:
    s = _session(sid)
    agent: DifferentialAgent = s["agent"]
    if req.key not in agent.tb.engine._obs:
        raise HTTPException(400, f"unknown measurement {req.key}")
    reply = agent.measure(req.key)
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/readings")
def reading(sid: str, req: Reading) -> dict[str, Any]:
    s = _session(sid)
    reply = s["agent"].reading_event(req.key, req.value, source="technician")
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/discharge")
def discharge(sid: str, req: Discharge) -> dict[str, Any]:
    s = _session(sid)
    agent: DifferentialAgent = s["agent"]
    args: dict[str, Any] = {"all_points": req.all_points}
    if req.readings:
        args["readings"] = req.readings
    if req.volts is not None:
        args["volts"] = req.volts
    if "readings" not in args and "volts" not in args:
        raise HTTPException(400, "give readings per test point or one reading")
    res = agent.tb.call("confirm_discharge", args)
    if "error" in res:
        raise HTTPException(400, res["error"])
    text = res["message"]
    if res.get("verified"):
        agent.pending_key = None
        text += "\n\n" + agent._next_step()
    reply = agent._reply(text)
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/guess")
def guess(sid: str, req: Guess) -> dict[str, Any]:
    """Trainee mode: the trainee's own choice of next measurement, before the tool's."""
    s = _session(sid)
    agent: DifferentialAgent = s["agent"]
    if req.key not in agent.tb.engine._obs:
        raise HTTPException(400, f"unknown measurement {req.key}")
    reply = agent.trainee_guess(req.key)
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/supervisor")
def supervisor(sid: str, req: Supervisor) -> dict[str, Any]:
    s = _session(sid)
    try:
        reply = s["agent"].name_supervisor(req.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/approve_removal")
def approve_removal(sid: str, req: Approval) -> dict[str, Any]:
    """The owner has agreed that parts may be removed for testing (recorded on the ticket)."""
    s = _session(sid)
    agent: DifferentialAgent = s["agent"]
    res = agent.tb.call("approve_part_removal", {"note": req.note})
    text = res["message"]
    if agent.pending_key == "approval":
        agent.pending_key = None
        text += "\n\n" + agent._next_step()
    reply = agent._reply(text)
    return {"reply": _turn(reply), "state": _state(s)}


@app.post("/api/sessions/{sid}/photos")
async def photo(sid: str, file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    s = _session(sid)
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo too large")
    pid = uuid.uuid4().hex[:8]
    agent: DifferentialAgent = s["agent"]
    agent.tb.photos[pid] = data
    args: dict[str, Any] = {"photo_id": pid}
    if agent.pending_key and agent.pending_key not in ("discharge", "approval"):
        args["key"] = agent.pending_key
    proposal = agent.tb.call("read_meter_photo", args)
    return {"photo_id": pid, "proposal": proposal}


@app.post("/api/sessions/{sid}/photos/{pid}/confirm")
def confirm_photo(sid: str, pid: str, req: Reading) -> dict[str, Any]:
    s = _session(sid)
    agent: DifferentialAgent = s["agent"]
    if pid not in agent.tb.photos:
        raise HTTPException(404, "unknown photo")
    reply = agent.confirm_photo(pid, req.key, req.value)
    return {"reply": _turn(reply), "state": _state(s)}


@app.get("/api/sessions/{sid}/ticket")
def ticket(sid: str) -> dict[str, Any]:
    return dict(_session(sid)["agent"].ticket())


@app.post("/api/sessions/{sid}/ticket/signoff")
def signoff(sid: str, req: SignOff) -> dict[str, Any]:
    agent: DifferentialAgent = _session(sid)["agent"]
    agent.sign_off(req.name)
    return dict(agent.ticket())


@app.post("/api/sessions/{sid}/reveal")
def reveal(sid: str) -> dict[str, Any]:
    """Demo only: show the hidden fault of the simulated unit after the diagnosis."""
    s = _session(sid)
    bench: SimulatedBench = s["bench"]
    s["revealed"] = {"fault": bench.hypothesis, "label": fault_label(bench.hypothesis)}
    return _state(s)


@app.get("/api/replays")
def replays() -> dict[str, Any]:
    """Recorded sessions the interface can replay with no server work (demo fallback)."""
    return {"replays": sorted(p.stem for p in REPLAY_DIR.glob("*.json"))}


@app.get("/api/replays/{name}")
def replay(name: str) -> JSONResponse:
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", name):
        raise HTTPException(404, "unknown replay")
    path = REPLAY_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, "unknown replay")
    return JSONResponse(json.loads(path.read_text()))


@app.get("/api/sessions/{sid}/export")
def export(sid: str) -> JSONResponse:
    s = _session(sid)
    data = s["agent"].export()
    data["hidden_fault"] = s["bench"].hypothesis
    return JSONResponse(data)


if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
