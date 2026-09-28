"""Agent, tools, ticket and LLM plumbing (needs trained models in data/models/)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from differential.config import MODELS_DIR, LLMSettings

pytestmark = pytest.mark.skipif(not (MODELS_DIR / "driver" / "generative.npz").exists(),
                                reason="trained models not present")


def _bench(cid: str, fault: str):  # type: ignore[no-untyped-def]
    from differential.instruments.simulated import SimulatedBench

    return SimulatedBench.simulate(cid, fault, unit_index=3)


def test_offline_session_reaches_a_grounded_ticket() -> None:
    from differential.agent.agent import DifferentialAgent

    agent = DifferentialAgent("driver", mode="offline", instrument=_bench("driver", "R503:open"))
    agent.user_message("Output is dead, nothing passes with a tone in.")
    for _ in range(30):
        if agent.pending_key is None:
            break
        agent.measure(agent.pending_key)
    ticket = agent.ticket()
    assert ticket["grounding"]["ungrounded"] == []
    assert all(not g["ungrounded"] for g in agent.grounding_log)
    assert ticket["status"].startswith("draft")
    agent.sign_off("Test Tech")
    assert agent.ticket()["status"] == "signed off"
    assert "Repair ticket" in ticket["markdown"]


def test_lift_steps_are_locked_until_discharge_is_confirmed() -> None:
    from differential.agent.tools import ToolBox

    tb = ToolBox("psu")
    lift = next(o for o in tb.bundle.observables.values() if o.is_lift)
    assert tb.step_payload(lift)["blocked"] == "discharge_verification"
    assert tb.t_confirm_discharge(12.0)["verified"] is False
    assert tb.t_confirm_discharge(0.4)["verified"] is True
    assert not tb.step_payload(lift).get("blocked")
    res = tb.call("record_measurement", {"key": lift.key, "value": 1.0})
    assert "error" not in res
    dc = next(o for o in tb.bundle.observables.values() if o.kind == "dc")
    tb.call("record_measurement", {"key": dc.key, "value": 15.0})
    assert tb.step_payload(lift)["blocked"] == "discharge_verification"


def test_high_voltage_steps_carry_instructions() -> None:
    from differential.agent.tools import ToolBox

    tb = ToolBox("triode")
    tp9 = tb.bundle.observables["dc:TP9"]
    lines = " ".join(tb.step_payload(tp9)["safety"]["lines"])
    assert "HIGH VOLTAGE" in lines and "Hands-off" in lines and "resistor tool" in lines


def test_model_cannot_record_a_value_nobody_typed() -> None:
    from differential.agent.agent import DifferentialAgent, Turn

    agent = DifferentialAgent("driver", mode="offline")
    dc = next(o for o in agent.tb.bundle.observables.values() if o.kind == "dc")
    out = agent._guarded_tool("record_measurement", {"key": dc.key, "value": 12.34})
    assert "refused" in out["error"]
    agent.turns.append(Turn("user", f"I measured 12.34 V at {dc.tp}"))
    ok = agent._guarded_tool("record_measurement", {"key": dc.key, "value": 12.34})
    assert "error" not in ok and ok["recorded"]["value"] == 12.34


class FakeResp:
    def __init__(self, data: dict[str, Any]) -> None:
        self._d = data

    def to_dict(self) -> dict[str, Any]:
        return self._d


class FakeMessages:
    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = script
        self.calls = 0

    def create(self, **params: Any) -> FakeResp:
        r = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return FakeResp(r)


class FakeSDK:
    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.messages = FakeMessages(script)


def test_llm_client_caches_responses(tmp_path: Any) -> None:
    from differential.agent.llm import LLMClient

    resp = {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2}}
    sdk = FakeSDK([resp])
    c = LLMClient(LLMSettings(api_key="k", model="claude-sonnet-5-5"), cache_dir=tmp_path,
                  sdk_client=sdk)
    assert c.text("sys", "hi") == "hello"
    assert c.text("sys", "hi") == "hello"
    assert sdk.messages.calls == 1 and c.usage.cached_calls == 1
    # The cache never contains the key.
    for f in tmp_path.rglob("*.json"):
        assert "\"k\"" not in f.read_text()


def test_llm_baseline_protocol_with_scripted_model(tmp_path: Any) -> None:
    from differential.agent.llm import LLMClient
    from eval.cases import load_cases
    from eval.harness import bundle_for
    from eval.llm_baseline import run_case

    bundle = bundle_for("driver")
    df, _meta = load_cases("driver", "pilot")
    row = df[df["ok"]].iloc[0].to_dict()
    truth = str(row["hypothesis"])
    dc = next(k for k, o in bundle.observables.items() if o.kind == "dc")
    script = [
        {"content": [{"type": "tool_use", "id": "t1", "name": "measure", "input": {"key": dc}}],
         "stop_reason": "tool_use", "usage": {}},
        {"content": [{"type": "tool_use", "id": "t2", "name": "diagnose",
                      "input": {"ranked_faults": [truth], "confidence": 0.8}}],
         "stop_reason": "tool_use", "usage": {}},
        {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn", "usage": {}},
    ]
    c = LLMClient(LLMSettings(api_key="k", model="claude-sonnet-5-5"), cache_dir=tmp_path,
                  sdk_client=FakeSDK(script))
    res = run_case(c, bundle, row, "It has no output.", with_sim=False)
    assert res["correct"] is True and res["cost"] == bundle.observables[dc].cost
    assert json.loads(res["ranked"]) == [truth]
