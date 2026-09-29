"""Repair ticket: the diagnosis, its confidence and the evidence trail (brief §2.6).

Every number in the ticket is copied from the session state (readings, the
engine's posterior and its predictions); the ticket passes the same grounding
check as agent messages.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from differential import __version__
from differential.agent.format import fault_label, fmt_reading, pct
from differential.safety.hazards import DISCHARGE_VERIFY_MAX_V, discharge_points, needs_bring_up
from differential.sim.faults import parse_fault_id
from differential.sim.observables import KIND_LABEL

if TYPE_CHECKING:
    from differential.agent.tools import ToolBox


def build_ticket(tb: ToolBox) -> dict[str, Any]:
    e = tb.engine
    circuit = tb.bundle.circuit
    belief = tb.t_get_belief()
    stop, reason = e.status()
    top = belief["ranked_groups"][0]
    unmodeled = top["group"] == -1
    confident = top["probability"] >= e.stop_threshold
    if unmodeled:
        verdict = ("No single-fault explanation fits the readings. Suspect more than one "
                   "fault or a modification; continue by hand from the readings below.")
    elif confident:
        verdict = "Diagnosis: " + " or ".join(f["label"] for f in top["faults"]) + "."
    else:
        verdict = ("Not yet conclusive. Leading candidates: "
                   + "; ".join(f"{', '.join(x['label'] for x in g['faults'])} ({pct(g['probability'])})"
                               for g in belief["ranked_groups"][:3]) + ".")
    readings = []
    for r in e.readings:
        o = e._obs[r.key]
        readings.append({"step": r.step, "key": r.key, "what": KIND_LABEL[o.kind],
                         "value": r.value, "text": fmt_reading(o.kind, r.value),
                         "source": r.source, "cost": r.cost})
    actions: list[str] = []
    if not unmodeled and confident:
        for f in top["faults"]:
            if f["fault"] == "healthy":
                actions.append("No fault found within tolerance; re-check the complaint.")
                continue
            ref = parse_fault_id(f["fault"]).ref
            comp = circuit.component(ref)
            actions.append(f"Replace or repair {ref} ({comp.value} {comp.kind}): {f['label']}.")
        if len(top["faults"]) > 1:
            actions.append("The readings cannot separate these parts; lift-test them to "
                           "confirm which one failed before replacing anything.")
        actions.append("After the repair, repeat the measurements above and confirm they "
                       "return to their healthy values.")
    hv_parts = [p.ref for p in circuit.components if p.kind == "electrolytic"
                and circuit.component_is_hv(p.ref)]
    safety = []
    if hv_parts:
        pts = discharge_points(circuit.id)
        safety.append("This unit carries high voltage. Before any hands-in work: switch off, "
                      "unplug, discharge " + ", ".join(hv_parts) + " through a resistor and "
                      f"confirm below {DISCHARGE_VERIFY_MAX_V:g} V at " + ", ".join(pts)
                      + " with a meter proved on a live source before and after; re-check after "
                        "any power cycle.")
    if needs_bring_up(circuit.id):
        # after the repair (M2 review, round 1): what the owner gets back must be safe
        safety.append("Before the unit goes back to its owner: replace any safety-marked part "
                      "only with the type the manual specifies, and do the manual's leakage or "
                      "ground-continuity check.")
    removed = [{"part": str(r["key"])[5:], "verdict": "out of tolerance"
                if float(r["value"]) >= 0.5 else "within tolerance"}  # type: ignore[arg-type]
               for r in readings if str(r["key"]).startswith("lift:")]
    ticket = {
        "circuit": {"id": circuit.id, "name": circuit.name},
        "created": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "complaint_symptoms": tb.symptoms.classes if tb.symptoms else [],
        "verdict": verdict,
        "confident": bool(confident and not unmodeled),
        "top_groups": belief["ranked_groups"][:3],
        "unmodeled_probability": belief["unmodeled_probability"],
        "stop_reason": reason if stop else "in progress",
        "readings": readings,
        "effort_spent": e.cost_spent,
        "actions": actions,
        "safety": safety,
        "part_removal": {"owner_approved": tb.removal_approved, "note": tb.removal_note,
                         "parts_removed": removed},
        "discharge_attestations": list(tb.discharge_log),
        "bring_up": dict(tb.bring_up) if tb.bring_up else None,
        "trainee": ({"supervisor": tb.supervisor, "steps": len(tb.trainee_log),
                     "matched": sum(1 for x in tb.trainee_log if x["match"]),
                     "log": list(tb.trainee_log)} if tb.trainee else None),
        "signoff_meaning": SIGNOFF_MEANING,
        "ai_disclosure": AI_DISCLOSURE,
        "provenance": {
            "differential_version": __version__,
            "likelihood": e.likelihood,
            "policy": e.policy,
            "extractor": tb.symptoms.source if tb.symptoms else "none",
            "note": "Probabilities come from simulation of this circuit's design under "
                    "component tolerances; the technician confirmed every reading.",
        },
    }
    ticket["markdown"] = ticket_markdown(ticket)
    return ticket


AI_DISCLOSURE = ("Prepared with Differential, an AI diagnostic assistant. It recommends; "
                 "the technician who signs this ticket makes the diagnosis.")
SIGNOFF_MEANING = ("Signing confirms that the technician took the readings listed and accepts "
                   "the recommended next steps; it does not certify that the tool's diagnosis is "
                   "correct. The record belongs to this job, not to a person's performance.")


def ticket_markdown(t: dict[str, Any]) -> str:
    lines = [f"# Repair ticket: {t['circuit']['name']}", "", f"_{t['created']}_", "",
             f"> {t['ai_disclosure']}", "", f"**{t['verdict']}**", ""]
    if t["complaint_symptoms"]:
        lines += ["Reported symptoms: " + ", ".join(s.replace("_", " ")
                                                    for s in t["complaint_symptoms"]), ""]
    lines += ["## Belief at close", "", "| Candidate | Probability |", "|---|---|"]
    for g in t["top_groups"]:
        name = ", ".join(f["label"] for f in g["faults"])
        lines.append(f"| {name} | {pct(g['probability'])} |")
    lines += ["", f"Probability that no single-fault model fits: "
                  f"{pct(t['unmodeled_probability'])}.", "", "## Evidence", "",
              "| Step | Measurement | Reading | Source |", "|---|---|---|---|"]
    for r in t["readings"]:
        lines.append(f"| {r['step']} | {r['key']} ({r['what']}) | {r['text']} | {r['source']} |")
    lines += ["", f"Effort: {t['effort_spent']:g} units.", ""]
    if t["actions"]:
        lines += ["## Recommended action", ""] + [f"- {a}" for a in t["actions"]] + [""]
    if t["safety"]:
        lines += ["## Safety", ""] + [f"- {s}" for s in t["safety"]] + [""]
    bu = t.get("bring_up")
    if bu:
        lines.append(f"Bring-up recorded by the technician at {bu['time']}: the unit {bu['text']}.")
    for a in t.get("discharge_attestations", []):
        lines.append("Discharge attested by the technician at " + a["time"] + ": " + ", ".join(
            f"{tp} {v:g} V" for tp, v in a["readings"].items())
            + (" (bleeder attached)" if a.get("bleeder") else "") + ".")
    pr = t.get("part_removal") or {}
    if pr.get("parts_removed") or pr.get("owner_approved"):
        lines += ["", "## Parts removed for testing", "",
                  "Owner approval: " + ("recorded" if pr.get("owner_approved") else "not recorded"), ""]
        lines += [f"- {x['part']}: {x['verdict']}" for x in pr.get("parts_removed", [])]
        lines.append("")
    tr = t.get("trainee")
    if tr:
        lines += ["## Trainee mode", "",
                  f"Supervisor: {tr['supervisor'] or 'not named'}. The trainee chose the same next "
                  f"measurement as the tool in {tr['matched']} of {tr['steps']} steps.", ""]
    lines += [f"_{t['signoff_meaning']}_", ""]
    p = t["provenance"]
    lines += ["---", f"Differential {p['differential_version']} · likelihood {p['likelihood']} · "
              f"policy {p['policy']} · symptom extractor {p['extractor']}. {p['note']}"]
    return "\n".join(lines)


def fault_line(h: str) -> str:
    return fault_label(h)
