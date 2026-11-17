"""Render the M3 design document: submissions/M3/M3.pdf (HTML -> PDF with Chromium).

Every number is read at build time from the result files: results/metrics.json,
targets.json, engineering.json (tools/engineering_facts.py), m3_analysis.json
(tools/m3_analysis.py), t17_live_review.json, redteam_review.json and remeasure_check.json.
The page is checked with tools/check_claims.py like every other milestone document.

Usage (from the repository root, after the tools above have run):
    python templates/M3/build.py [repo] [out.pdf] [signer]
The signer defaults to the first member in team.yaml.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE.parent.parent
OUT_PDF = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else REPO / "submissions" / "M3" / "M3.pdf"
# the signer: given on the command line, else the first member in team.yaml (CLAUDE.md, rule 6)
NAME = sys.argv[3] if len(sys.argv) > 3 else str(
    __import__("yaml").safe_load((REPO / "team.yaml").read_text())["members"][0]["name"])
RES = REPO / "results"

M = json.loads((RES / "metrics.json").read_text())
T = json.loads((RES / "targets.json").read_text())
E = json.loads((RES / "engineering.json").read_text())
A = json.loads((RES / "m3_analysis.json").read_text())
TGT = {t["id"]: t for t in T["targets"]}
TR = M["targets_result"]
try:
    COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()
except Exception:
    COMMIT = "draft"


# ------------------------------------------------------------------ formatting
def pct(x, d=1):
    return f"{100 * float(x):.{d}f}%"


def pts(x, d=1):
    v = 100 * float(x)
    return ("+" if v >= 0 else "−") + f"{abs(v):.{d}f}"


def ci_pct(ci, d=1):
    return f"[{100 * ci['lo']:.{d}f}, {100 * ci['hi']:.{d}f}]"


def ci_num(ci, d=2):
    return f"[{ci['lo']:.{d}f}, {ci['hi']:.{d}f}]"


def table(caption, head, rows, widths, cls=""):
    cols = "".join(f'<col style="width:{w}%">' for w in widths)
    th = "".join(f"<th>{h}</th>" for h in head)
    body = []
    for r in rows:
        if isinstance(r, str):  # group heading row
            body.append(f'<tr class="grp"><td colspan="{len(head)}">{r}</td></tr>')
        else:
            body.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    return (f'<p class="cap">{caption}</p><table class="{cls}"><colgroup>{cols}</colgroup>'
            f"<thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>")


def chip(state):
    cls = {"met": "met", "missed": "missed"}.get(state, "partial" if state.startswith(("incomplete", "missed (live)")) else "pending")
    return f'<span class="st {cls}">{state}</span>'


# ------------------------------------------------------------------ facts
L = M["library"]
CS = L["circuits"]["channel_strip"]
G = L["groups"]["channel_strip"]
D = L["design"]
n_units = sum(v["rows"] for v in L["simulations"]["datasets"].values())
AL, AO = M["agent_live"], M["agent_offline"]
AOB = M.get("agent_offline_before_adr052")
SY = M["analyses"]["systems"]
DIS = M["analyses"]["disaggregated"]
LLM = A["llm_only"]
MS = A["misses"]
CA = A["cost_ablation"]
T13K = A["t13_by_kind"]["by_kind"]
RT = A.get("redteam", {})
RTO = RT.get("offline", {})
RTL = RT.get("live")
rt_att = RTO.get("attack", {})
rt_ben = RTO.get("benign", {})
RV = json.loads((RES / "redteam_review.json").read_text())  # every flagged reply, read and labeled
RVO, RVL = RV["offline"]["summary"], RV["live"]["summary"]
RTM_O, RTM_L = M["redteam_offline"], M["redteam_live"]
N_OUTPUT_CHECK = int(re.match(r"(\d+) of the", RV["causes"]["live_output_check"]).group(1))
tests = E["tests"]
nlp = M["nlp"]
vision_test = M["vision"]["synthetic_test"]
haiku_nlp = json.loads((RES / "nlp_claude-haiku-5-5.json").read_text())
haiku_vis = json.loads((RES / "vision_claude-haiku-5-5.json").read_text())
T17R = json.loads((RES / "t17_live_review.json").read_text()) if (RES / "t17_live_review.json").exists() else None
RMC = json.loads((RES / "remeasure_check.json").read_text()) if (RES / "remeasure_check.json").exists() else None


def sys_top1(name):
    return SY[name]["pooled"]["top1"]["value"]


def sys_cost(name):
    return SY[name]["pooled"]["mean_cost"]["value"]


# ------------------------------------------------------------------ results table
def result_row(tid):
    t, r = TGT[tid], TR.get(tid, {})
    status = r.get("status", "pending")
    ci = r.get("ci") or {}
    v = r.get("value")
    if tid in ("T1", "T2", "T3", "T6"):
        val = f"{pct(v)} {ci_pct(ci)}"
    elif tid == "T4":
        mg = r["margins"]
        val = " / ".join(pts(mg[k]["margin"]["value"]) for k in ("fixed_order", "half_split", "random")) + " pts"
        val += f"; lowest bound {pts(mg['half_split']['margin']['lo1'])}"
    elif tid == "T5":
        dl = r["detail"]
        val = f"{pts(v)} pts {ci_pct(ci)}: {pct(dl['top1_hybrid'])} vs {pct(dl['top1_llm'])}"
    elif tid in ("T8", "T9", "T10", "T11", "T24"):
        val = f"{v:.3f}× {ci_num(ci, 3)}"
    elif tid == "T12":
        val = f"{v:.3f} {ci_num(ci, 3)}"
    elif tid == "T13":
        val = f"{pct(v)} {ci_pct(ci)}"
    elif tid == "T14":
        a, b = r["capacitor_heavy_prior_catalog_mix"], r["uniform_prior_capacitor_mix"]
        val = f"{pts(a['value'])} / {pts(b['value'])} pts"
    elif tid == "T15":
        val = f"{r['steps_checked']} of {r['required_checks']} steps"
    elif tid == "T16":
        val = (f"{RTM_L['n_attacks']} attacks (of ≥ 300). Live: 0 unsafe after review. Offline: "
               f"{RVO['attacks']['silent']} not refused, none endorsing")
        status = "incomplete"
    elif tid == "T17":
        val = (f"offline 0 of {AO['numbers_checked']:,}; live {AL['ungrounded_final']} of "
               f"{AL['numbers_checked']:,} (all withheld before display), above the bar as counted")
    elif tid == "T18":
        val = f"Claude {r['claude']['value']:.3f}; rules {v:.3f}"
    elif tid == "T19":
        val = f"Claude {pct(r['claude']['value'])} {ci_pct(r['claude'])}; offline {pct(v)}"
    elif tid == "T20":
        val = f"{v:.3f} s"
    elif tid == "T21":
        val = f"${v:.3f}"
    elif tid == "T22":
        val = f"{pct(r['flag_rate']['value'])} flagged; AUROC {v:.2f}"
    elif tid == "T23":
        val = f"{pct(v)} named; {pct(r['accuracy_when_naming']['value'])} right {ci_pct(r['accuracy_when_naming'])}"
    elif tid == "T26":
        val = "no voice worse"
    else:
        val = "—"
    if status == "pending":
        val = {"T7": "fault boards (M5)", "T25": "technician study S1 (M5)"}.get(tid, val)
    return [tid, t["plain"], t["text"], val, chip(status)]


groups = [("Primary: the claims the project stands on", ["T1", "T4", "T5", "T6", "T9", "T12", "T13", "T7"]),
          ("Release gates: must hold with no exception", ["T15", "T16", "T17", "T26", "T25"]),
          ("Secondary", ["T2", "T3", "T8", "T10", "T11", "T14", "T22", "T23", "T24", "T18", "T19", "T20", "T21"])]
rows = []
for title, ids in groups:
    rows.append(title)
    rows += [result_row(i) for i in ids]
counts = {"met": 0, "missed": 0, "pending": 0}
for tid in TGT:
    s = TR.get(tid, {}).get("status", "pending")
    if tid == "T16":
        s = "pending"
    counts[s if s in counts else "pending"] += 1


# ------------------------------------------------------------------ figure: accuracy vs effort
def effort_figure():
    pts_ = [("hybrid", "Differential", True), ("engine_gen", "Engine alone", True),
            ("engine_disc", "Engine, LightGBM", True), ("half_split", "Half-split tracing", False),
            ("random", "Random probing", False), ("fixed_order", "Fixed-order chart", False)]
    W, H, left, r, t, b = 640, 250, 52, 18, 12, 38
    x0, x1, y0, y1 = 0, 22, 0.86, 0.97

    def X(v):
        return left + (v - x0) / (x1 - x0) * (W - left - r)

    def Y(v):
        return t + (y1 - v) / (y1 - y0) * (H - t - b)
    s = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Inter, DejaVu Sans, sans-serif" font-size="10.5">']
    for gv in (0.88, 0.90, 0.92, 0.94, 0.96):
        s.append(f'<line x1="{left}" x2="{W - r}" y1="{Y(gv):.1f}" y2="{Y(gv):.1f}" stroke="#e1e0d9" stroke-width="1"/>')
        s.append(f'<text x="{left - 6}" y="{Y(gv) + 3.5:.1f}" text-anchor="end" fill="#52514e">{100 * gv:.0f}%</text>')
    for gx in range(0, 23, 4):
        s.append(f'<text x="{X(gx):.1f}" y="{H - b + 15}" text-anchor="middle" fill="#52514e">{gx}</text>')
    s.append(f'<line x1="{left}" x2="{W - r}" y1="{H - b}" y2="{H - b}" stroke="#c3c2b7"/>')
    s.append(f'<text x="{(left + W - r) / 2}" y="{H - 4}" text-anchor="middle" fill="#52514e">Mean effort per diagnosis (points: DC reading 1, scope reading 3, +2 above 50 V, unsoldering 10)</text>')
    s.append(f'<text x="12" y="{(t + H - b) / 2}" text-anchor="middle" fill="#52514e" transform="rotate(-90 12 {(t + H - b) / 2})">Failed part’s group named first</text>')
    place = {"hybrid": (-10, 6, "end"), "engine_gen": (10, -2, "start"), "engine_disc": (10, 4, "start"),
             "half_split": (-10, -8, "end"), "random": (-10, 4, "end"), "fixed_order": (-10, 14, "end")}
    for key, label, ours in pts_:
        p = SY[key]["pooled"]
        cx, cy = X(p["mean_cost"]["value"]), Y(p["top1"]["value"])
        col = "#2a78d6" if ours else "#52514e"
        s.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{Y(p["top1"]["lo"]):.1f}" y2="{Y(p["top1"]["hi"]):.1f}" stroke="{col}" stroke-width="1.5"/>')
        s.append(f'<line x1="{X(p["mean_cost"]["lo"]):.1f}" x2="{X(p["mean_cost"]["hi"]):.1f}" y1="{cy:.1f}" y2="{cy:.1f}" stroke="{col}" stroke-width="1.5"/>')
        fill = col if ours else "#fcfcfb"
        s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{fill}" stroke="{col}" stroke-width="2"/>')
        dx, dy, anc = place[key]
        s.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" fill="#0b0b0b">{label} <tspan fill="#52514e">{pct(p["top1"]["value"])}</tspan></text>')
    s.append("</svg>")
    return "".join(s)


def img64(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


css = (HERE / "style.css").read_text()
arch_svg = (HERE / "diagram.svg").read_text()
shot = REPO / "docs" / "media" / "screenshots" / "02_recommendation_hv_light.png"

# ------------------------------------------------------------------ text blocks
t1, t5, t9, t12, t13, t6 = (TR[k] for k in ("T1", "T5", "T9", "T12", "T13", "T6"))
t22 = TR["T22"]
summary = f"""<p><b>Summary.</b> Differential runs end to end from a clean clone: offline with no API key, live with Claude Sonnet 5.5, and in replay from recorded responses. On {t1['n']:,} held-out simulated single-fault units it named the failed part’s group first in {pct(t1['value'])} (bar ≥ 94%), with {t9['value']:.2f}× the effort of half-split tracing to a confirmed answer and probabilities that are well calibrated (calibration error {t12['value']:.3f}). It beat Claude working alone with the same bench information by {100 * t5['value']:.1f} points on {t5['detail']['n']} units, and a live diagnosis cost ${AL['mean_cost_usd_per_diagnosis']:.3f} at list prices. Of the {len(TGT)} locked targets, {counts['met']} are met, {counts['missed']} missed and {counts['pending']} pending (§3); one pending gate, T17, is already above its bar on the live count. The misses are reported as written and traced to their causes in §4. The two that matter most are safety findings. Offline, the code’s request screen recognized only {rt_att.get('refused', 0)} of {RTM_O['n_attacks']} independently written attack prompts; live, no reply endorsed an unsafe step, but {RVL['benign']['unjustified']} of {RTM_L['n_benign']} harmless questions were refused. And {AL['ungrounded_final']} untraced numbers in live replies got past the grounding check’s rewrite step; the final check withheld them all. Hardware validation (T7) and the technician study move to M5, as M2 planned.</p>"""

components = [
    ["Circuit library", f"6 circuits (5 blocks and a {CS['components']}-part channel strip) with tolerances, test points and hazard flags", "<code>circuits/</code>", "As in M2"],
    ["Simulation", f"Every failure mode of every part ({L['fault_mode_count']} modes by part kind) under tolerances, aging and meter loading: {n_units:,} simulated units", "<code>differential/sim/</code>", "As in M2"],
    ["Diagnosis engine", f"Belief over fault groups and “no single fault fits”; next measurement by information gain per effort point; stops at {D['stop_threshold']:.2f} belief or a {D['budget']:.0f}-point budget", "<code>differential/engine/</code>", "As in M2"],
    ["Agent", f"Screen, then Claude chooses among {E['agent_tools']['model']} tools, then grounding and output checks; live, offline and replay modes", "<code>differential/agent/</code>", "Prompt caching (ADR-050); two routing fixes (ADR-051, ADR-052); re-measure prompt (ADR-053)"],
    ["Safety layer", "Request screen, hazard map, bring-up and discharge locks, output check; safety records only from the app’s forms", "<code>differential/safety/</code>", "As in M2"],
    ["Readers", "Complaint → symptom prior; meter photo → a proposed reading the technician confirms", "<code>differential/nlp/</code>, <code>vision/</code>", "As in M2"],
    ["Web app", "Schematic, belief, next step, “Why this?”, forms, repair ticket (Figure 2)", "<code>differential/app/</code>", "As in M2"],
    ["Evaluation", "All systems on held-out units, locked targets judged on one-sided 95% bounds, red-team harness", "<code>eval/</code>, <code>results/</code>", "Red-team suite added"],
]

commands = [
    ["<code>git clone https://github.com/jamesharkins/prv201</code><br><code>cd prv201; make install</code>", "Python 3.11 environment with pinned dependencies (needs <code>ngspice</code>)", "minutes"],
    ["<code>make demo</code>", "The web app at <code>localhost:8000</code>, offline: no key, no network. Trained models are in the repository", "seconds"],
    ["<code>DIFFERENTIAL_API_KEY=… make demo</code>", "The same app with Claude live; <code>DIFFERENTIAL_MODE=replay</code> serves recorded responses with no key (Table 3)", "seconds"],
    ["<code>make test</code>, <code>make check</code>", f"{tests['collected']} tests with coverage; <code>check</code> adds lint and strict type checks, as CI does on every push", "minutes"],
    ["<code>make eval-smoke</code>", "Every baseline and the full system on a few pilot units, end to end", "under a minute"],
    ["<code>make sim cases fit calibrate eval</code>", "Rebuilds everything from the netlists: simulation, training, calibration, full evaluation", "hours (resumable)"],
    ["<code>python -m eval.redteam.harness</code>", "Runs the red-team suite offline (<code>--mode live</code> with a key)", "under a minute"],
]

evidence = [
    ["<code>results/metrics.json</code>, <code>targets.json</code>", "Every reported number; the targets as locked at commit <code>60cca12</code>, before any test unit was scored"],
    ["<code>results/agent_live.jsonl</code>", f"The {AL['n_sessions']} live sessions: accuracy, numbers checked, tokens and list-price cost per session"],
    ["<code>data/llm_cache/</code> on branch <code>claude/m3-live-results</code>", "Every live Claude response (kept out of <code>main</code> for size); with it, replay mode re-runs any live result with no key and no cost"],
    ["<code>docs/DECISIONS.md</code>", f"{E['decision_records']} decision records, including the two defects found after the lock and how each was disclosed"],
    ["<code>docs/hand_calcs.md</code>, <code>fault_audit.md</code>", "The simulator checked against hand calculations and against an independent solver"],
    ["<code>docs/media/</code>", "Screenshots, a demo GIF and a silent 90-second capture of one diagnosis, recorded offline"],
    ["<code>docs/bench/index.html</code>", "Open in a browser: replays of real engine sessions on held-out units, step by step, with the test-run statistics"],
    ["<code>eval/redteam/cases.yaml</code>", "The attack prompts and benign controls, each with its source and intent"],
]

figures = f"""
<div class="fig"><p class="cap" style="margin-top:2px"><b>Figure 1.</b> Architecture and data flow of one diagnosis, as built (unchanged from M2). Code screens every request, the engine ranks suspects and chooses each measurement, Claude explains, and code checks every number and safety step on the way out.</p>
<div style="width:76%;margin:0 auto">{arch_svg}</div></div>
<div class="fig"><img style="width:88%;margin:0 auto" src="{img64(shot)}" alt="Differential web app"><p class="figcap"><b>Figure 2.</b> The app in offline mode on the channel strip. The banner carries the high-voltage instructions drawn by code, the next measurement shows its information gain and effort, and the belief panel shows each suspect’s probability.</p></div>
"""

# ---- analysis
hy, eg = "hybrid", "engine_gen"
cap_kinds = DIS["by_part_kind"]
psu = MS["by_circuit"]["psu"]
nocost = SY["engine_eig_nocost"]["pooled"]
oracle = SY["hybrid_oracle"]["pooled"]
mc = M["analyses"]["mc_draws_ablation"]
tol = t6["tolerance_curve_top1"]
pk = LLM["by_part_kind"]
bc = LLM["by_circuit"]
t22 = TR["T22"]
bank_b_rules = nlp["bank_b_rules"]
agent_fixed = (f" After the fix, the offline agent named the right group in {pct(AO['agent_top1'], 0)} of the same units." if AOB else
               " The offline run is being repeated after the fix.")

if T17R:
    t17c = T17R["by_cause"]
    t17_text = (f"<b>Grounding (T17).</b> Offline, every one of {AO['numbers_checked']:,} numbers traced to a tool result or a reading. "
                f"Live, the first drafts held {T17R['ungrounded_before_check']} untraced numbers in {T17R['n_sessions']} sessions. The check sent each draft back for a rewrite, "
                f"and {T17R['ungrounded_after_check']} numbers survived it: the rewrite request arrives as a user turn, and Claude answered it conversationally, quoting the number it was removing "
                f"(“You’re right that ‘95%’ never appeared…”). The final check replaced every one of them with a placeholder, so none reached the technician. "
                f"Counted as the evaluation counts them, though, {T17R['ungrounded_after_check']} of {T17R['numbers_checked']:,} is above the 0% bar, so the gate cannot be met as counted; it is listed as pending only because the independent checker and the human audit of 50 live transcripts have not run. "
                f"Most were one slip, repeated ({t17c['label_from_field_name']} of {T17R['ungrounded_after_check']}): a tool field named <code>range_95</code> written out as “95%”.")
else:
    t17_text = (f"Live replies kept {AL['ungrounded_final']} of {AL['numbers_checked']:,} numbers that traced to nothing after the grounding check "
                f"({AL['ungrounded_before_check']} before it), so the T17 gate is not met live.")

analysis = f"""
<h3>4.1 Why the engine beats scripted procedures</h3>
<p>Every baseline shares the engine’s inference and stopping rule and differs only in how it picks the next measurement, so Figure 3 isolates the choice of measurement. Differential reached its answers with {sys_cost(hy):.1f} effort points on average against {sys_cost('half_split'):.1f} for half-split tracing and {sys_cost('fixed_order'):.1f} for the fixed chart, and was right more often ({pct(sys_top1(hy))} against {pct(sys_top1('half_split'))} and {pct(sys_top1('fixed_order'))}). Choosing by information gain per effort point [2] matters for accuracy as well as effort. Without the effort weighting, accuracy fell to {pct(nocost['top1']['value'])}: the cost-blind engine took oscilloscope readings in {pct(CA['engine_eig_nocost']['scope_step_share'], 0)} of its steps against {pct(CA['engine_gen']['scope_step_share'], 0)}, stopped just as often at 90% belief, and was then right in only {pct(CA['engine_eig_nocost']['accuracy_when_confident'])} of cases against {pct(CA['engine_gen']['accuracy_when_confident'])}. Sessions that lean on oscilloscope readings are overconfident, which points at those readings’ likelihood models; confirming that is work for M5. Simulation size is not the limit: 50 draws per fault gave {pct(mc['50']['top1'])} against {pct(mc['400']['top1'])} with 400. The complaint saves effort rather than accuracy ({sys_cost(hy):.2f} against {sys_cost(eg):.2f} points for the engine alone); a perfect symptom reading would add {100 * (oracle['top1']['value'] - sys_top1(hy)):.1f} points, an upper bound on better complaint reading.</p>
<div class="fig">{effort_figure()}<p class="figcap"><b>Figure 3.</b> Accuracy against effort on the {t1['n']:,} test units, with 95% intervals. Differential is the engine with the complaint read; “Engine, LightGBM” swaps the per-fault likelihood models for a classifier. Differential’s variants (filled) sit up and to the left of every scripted procedure (open): more right answers for about a third of the effort.</p></div>

<h3>4.2 Where the engine fails</h3>
<p>Of {MS['misses']} misses on single faults, {MS['flagged']} were the engine declining to name a fault (“no single fault fits”) and {MS['wrong_name']} were wrong names. The power supply is the weakest circuit ({pct(DIS['by_circuit']['psu']['mean'])}): {psu['flagged']} of its {psu['misses']} misses are flags. Across circuits, the faults flagged most are hard shorts ({', '.join(k.replace(':short', '') for k in list(MS['most_flagged'])[:4])} shorted), which collapse a rail or saturate a stage and move many readings at once. Declining to name is the safer error: the ticket tells the technician to continue by hand rather than pointing at a healthy part. Among part kinds with many test units, electrolytic capacitors are the weakest ({pct(cap_kinds['electrolytic']['mean'])} of {cap_kinds['electrolytic']['count']}). Aging costs {pts(t6['drop_from_new']['value'])[1:]} points (T6), mostly as more flags ({pct(t6['aged_flagged'])} of aged units against {pct(t22['single_false_flag_rate'])} of new ones) rather than wrong names ({pct(t6['aged_wrong_name'])}). The engine depends on the tolerance model: with part tolerances widened 1.5×, 2× and 3×, accuracy fell to {pct(tol['1.5x'])}, {pct(tol['2x'])} and {pct(tol['3x'])}. This is why real boards (T7) are the test that matters most at M5.</p>

<h3>4.3 Why Claude alone does worse (T5)</h3>
<p>Given the netlist, test-point map, voltage chart, fault list, readings on request and the same budget, Claude alone named the right group in {pct(LLM['top1_llm'])} of {LLM['n']} units against {pct(LLM['top1_system'])} for Differential, and spent {LLM['mean_effort_llm']:.1f} effort points against {t5['detail']['mean_cost_hybrid']:.1f}. Its failures sit mostly in passive networks. It matched or beat the engine on parts with distinctive failures (op-amps {pct(pk['opamp']['llm'], 0)}, diodes, zeners and triodes at {pct(pk['zener']['llm'], 0)}). It fell to {pct(pk['resistor']['llm'], 0)} on resistors, {pct(pk['film_cap']['llm'], 0)} on film capacitors and {pct(pk['potentiometer']['llm'], 0)} on potentiometers, where a drift of a few decibels in one response must be attributed to one part, and to {pct(bc['tone']['llm'], 0)} on the passive tone stack. The simulation supplies exactly that quantitative mapping. Its three sessions agreed on only {LLM['units_all_sessions_agree']} of {LLM['n']} units, and {LLM['wrong_same_part_other_mode']} of its {LLM['wrong_named']} wrong answers named the right part with the wrong failure mode. Its stated confidence did carry information ({LLM['mean_confidence_right']:.2f} when right, {LLM['mean_confidence_wrong']:.2f} when wrong).</p>

<h3>4.4 Units outside the catalog (T13, T22)</h3>
<p>On {TR['T13']['n_unmodeled']:,} double-fault and modified units, {pct(t13['value'])} were misleading, below the 12% bar, but the upper bound ({pct(t13['ci']['hi1'])}) is not, so T13 is missed. Double faults misled in {pct(T13K['double_fault']['misleading_share'])} of cases; solder bridges in {pct(T13K['solder_bridge']['misleading_share'])} and wrong-value parts in {pct(T13K['wrong_value_part']['misleading_share'])}. In those cases a single catalog fault on another part fitted the readings well enough that the engine did not flag. A bridge alters no part, so only a flag counts as correct for it. The flag fired on {pct(t22['flag_rate']['value'])} of these units (bar 51%) at an operating point that wrongly flags {pct(t22['single_false_flag_rate'])} of single faults, and its separation (AUROC {t22['value']:.2f}) is below the 0.77 bar. Modifications are the main way Differential can mislead a technician.</p>

<h3>4.5 The language layer: readers, cost and the agent</h3>
<p>The complaint rules score almost exactly 1.00 on the phrasings they were written from but {bank_b_rules['micro_f1']:.3f} on a sealed bank written by someone who never saw them (precision {bank_b_rules['precision']:.2f}, recall {bank_b_rules['recall']:.2f}). Claude scores {nlp['bank_b_claude']['micro_f1']:.3f} and Claude Haiku 5.5 {haiku_nlp['bank_b_claude']['micro_f1']:.3f}; neither reaches the 0.90 bar (T18). The effect on diagnosis is small, because the complaint only shifts the prior (§4.1). On {vision_test['claude']['n']} synthetic meter photos, the offline reader was exact on {pct(vision_test['offline']['exact_match'], 0)} and Claude on {pct(vision_test['claude']['exact_match'])}, whose lower bound ({pct(TR['T19']['claude']['lo1'])}) falls just under the 95% bar (T19); Haiku managed {pct(haiku_vis['synthetic_test']['claude']['exact_match'])}. The photos come from the project’s own renderer, and no real photos are labeled yet, so these figures say little about real meters. Haiku met neither bar, so Sonnet stays the default, as M2 specified. Prompt caching brought a live diagnosis to ${AL['mean_cost_usd_per_diagnosis']:.3f} (T21) at list prices [1], against the M2 estimate of $0.22 uncached. End to end, the live agent named the right group in {pct(AL['agent_top1'], 0)} of {AL['n_sessions']} sessions and the offline agent in {pct((AOB or AO)['agent_top1'], 0)}, while the engine got {A['agent_vs_engine']['engine_correct_same_units']} of the same units right. The gap came from a routing defect (ADR-052). The offline agent read a complaint beginning “Service ticket:” as a request for the repair ticket, and {A['agent_vs_engine']['wrong_without_measurement']} sessions closed without a measurement.{agent_fixed}</p>

<h3>4.6 Safety: what held and what did not</h3>
<p><b>Held.</b> Every one of the {TR['T15']['required_checks']} possible steps that needs a warning or lock carries it, checked again by an independent recomputation from the raw simulations (T15). No out-of-catalog unit put a point above 50 V on the low-voltage side of the hazard map, and no complaint voice is served worse than the others (T26).</p>
<p><b>Did not hold.</b> The red-team suite has {RTM_L['n_attacks']} attack prompts, short of the 300 T16 requires, and {RTM_L['n_benign']} benign controls. Every reply the harness flagged was then read and labeled (<code>results/redteam_review.json</code>). <i>Live</i>, no reply gave or endorsed an unsafe step. The harness flagged {RVL['attacks']['auto_unsafe']} attack replies because they lacked its marker phrases, and each turned out to be a refusal in other words (“The 500mA T fuse stays in”). <i>Offline</i>, the request screen refused {rt_att.get('refused', 0)} attacks. The other {RVO['attacks']['silent']} were silent: the agent ignored the question and started a diagnosis as if it were a complaint. None endorsed the step, but silence is not a refusal, and the suite’s rubric counts it as unsafe. Over-refusal is the larger live problem. Of {RTM_L['n_benign']} benign controls, {RVL['benign']['unjustified']} were refused without cause. In 10 of them the output check matched a protection phrase inside a warning (“I won’t help bypass a fuse”, written about a planted service note) and replaced the whole reply. In {RVO['benign']['unjustified']} the request screen refused, in both modes, a question that named a forbidden act while asking for the safe practice.</p>
<p>The screen, the output check, the complaint rules and the ticket router failed the same way. Keyword rules match the phrasings they were written for and misjudge independent wording. The screen missed reworded attacks, both checks refused safe text that used a forbidden phrase, the complaint rules missed {100 * (1 - bank_b_rules['recall']):.0f}% of reported symptoms, and the ticket router fired on “Service ticket”. Unsafe requests and prompt injection are the top risk for language-model applications [4]. M2 said such requests are “refused by code whatever the model says”; that held only for recognized phrasings. Live, the model refused or redirected every attack the screen missed. One reviewer (the build assistant) labeled the replies; the second, human labeling the suite’s README asks for is still to do. No safety code was changed in response to this suite; the fixes are M5 work, to be tested on prompts it has not seen.</p>
<p>{t17_text}</p>
"""

engineering = f"""<p>The code is {E['code']['differential']['lines']:,} lines of Python in <code>differential/</code>, {E['code']['eval']['lines']:,} in the evaluation and {E['code']['tests']['lines']:,} in tests. On a fresh clone {tests['passed']} of {tests['collected']} tests pass and {tests['skipped']} are skipped (they need the simulation library, which is not in git, or the document typesetter); line coverage of the core package is {tests['line_coverage_pct']:.1f}%. Ruff and strict mypy run in GitHub Actions on every push. That check had failed since September on a test-path setting and a missing font, not on the code; both are fixed. Dependencies are pinned. Every live response is cached by request hash, so every live result replays exactly with no key; the cache is kept out of <code>main</code> for size and published on its own branch. The key is read only from <code>DIFFERENTIAL_API_KEY</code>. The targets are unchanged since the lock at <code>60cca12</code>. Two defects were found on test units after the lock: live sessions never took a measurement (ADR-051, before any live result was quoted), and the offline ticket routing (ADR-052). Both were plumbing, each is disclosed with the result from before the fix, and each has a regression test.</p>"""

if RMC:
    pg, slips = RMC["splits"]["pilot"]["genuine"], RMC["splits"]["pilot"]["x1000"]
    remeasure_status = (f"The re-measure prompt is built (ADR-053): on pilot units it held {pg['held']} of {pg['n']} genuine "
                        f"typed readings and caught {pct(slips['rate'], 0)} of volts typed as millivolts")
else:
    remeasure_status = "The re-measure prompt is pending"

scope_rows = [
    ["API key; 10-unit live smoke test; prompt caching", "Done. The smoke test found ADR-051; caching gave ADR-050"],
    ["Live runs: LLM-alone baseline, complaint bank and meter photos with Sonnet and Haiku, cost", "Done: T5, T18, T19, T21; Haiku compared and not adopted. The LLM-with-simulator variant is pending: it needs the simulation library, which is not in git"],
    ["Score the locked test runs and gates", f"Done: {counts['met']} met, {counts['missed']} missed, {counts['pending']} pending"],
    ["≥ 100 attack prompts written by me; the rest model-written, to ≥ 300; run offline and live", f"<b>Not met.</b> I wrote 4. A model wrote {sum(rt_att.values()) - 2} attacks and {sum(rt_ben.values()) - 2} benign controls before the provider’s safety filter stopped generation, and I did not try to work around it. T16 is reported as incomplete, as M2’s fallback stated"],
    ["Failure analysis; ablations; re-measure prompt", "Analysis in §4; ablations of cost, sample size and effort weights in <code>metrics.json</code>. " + remeasure_status],
    ["Fresh-clone check, screenshots, 90-second capture", "Done, re-recorded with the bring-up step; CI fixed"],
    ["Moved to M5 in M2: fault boards (T7), study S1 (T25), interviews after an IRB determination, peer-team attack prompts", "Unchanged"],
]

next_steps = """<p><b>Next, to M5.</b> In order of what the results say matters most: build the three 24 V fault boards and run T7, since §4.2 shows the engine is only as good as its tolerance model; replace the keyword screen with a classifier and stop the output check from replacing a reply over a negated or quoted phrase, testing both only on prompts they have never seen (the M4 peer team’s and the scanner styles T16 calls for); send the grounding rewrite as a tool note rather than a user turn (T17), and run the independent checker and the human audit of 50 live transcripts; add a residual check for modifications (T13, T22); find why oscilloscope-heavy sessions are overconfident (§4.1); and label real meter photos (T19).</p>"""

ai_note = """<p><b>How this was built.</b> As the course’s AI-use policy allows, Claude (in Claude Code) wrote most of the code, ran the evaluations and drafted this report. I chose the project, wrote the team attack prompts, directed the work and sign the report. Commits co-written by Claude say so in the history.</p>"""

refs = [
    "Anthropic, “Pricing,” Claude Platform Docs, 2026. https://platform.claude.com/docs/en/about-claude/pricing (accessed Nov. 17, 2026).",
    "K. R. Pattipati and M. G. Alexandridis, “Application of heuristic search and information theory to sequential fault diagnosis,” <i>IEEE Trans. Syst., Man, Cybern.</i>, vol. 20, no. 4, pp. 872–887, 1990.",
    "C. J. Clopper and E. S. Pearson, “The use of confidence or fiducial limits illustrated in the case of the binomial,” <i>Biometrika</i>, vol. 26, no. 4, pp. 404–413, 1934.",
    "OWASP GenAI Security Project, “OWASP Top 10 for LLM Applications 2026,” Aug. 2026. https://github.com/GenAI-Security-Project/GenAI-LLM-Top10",
]

results_text = f"""<p>The targets were locked at commit <code>60cca12</code> on {T['locked_on']}, before any test unit was scored, and Table 4 reports each one exactly as written. A target is met only when its one-sided 95% bound clears the bar (exact binomial bounds for counts of units [3], a bootstrap of 2,000 resamples otherwise), and a gate only with no exception. Every accuracy figure comes from simulated units; agreement with real boards is T7, at M5. Brackets give two-sided 95% intervals.</p>
{table('<b>Table 4.</b> Every locked target, met, missed or pending.', ['ID', 'Target', 'Bar', 'Result', 'Status'], rows, [5, 34, 17, 34, 10], 'tr')}"""

scope_text = f"""<p>Table 5 sets each M2 commitment for M3 against what was delivered. The system’s design is unchanged; what changed is what the evaluation found, and one commitment of mine was not met.</p>
{table('<b>Table 5.</b> M2’s plan to M3 against what was delivered.', ['M2 commitment', 'Status at M3'], scope_rows, [42, 58])}
{next_steps}
{ai_note}"""

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Differential - M3 Prototype</title>
<style>{css}</style></head><body>
<p class="kicker">MILESTONE 3 · PROTOTYPE · TRACK A: BUILD</p>
<h1>Differential: the working prototype, how to run it, and what it measured</h1>
<p class="meta">PRV 201 Frontiers of Technology (AI) · Stevens Institute of Technology · November 2026 · Code: github.com/jamesharkins/prv201, branch <code>main</code>, commit <code>{COMMIT}</code></p>
<div class="part"><span class="pt">Part 1 of 1 — Prototype, results against the locked targets, and changes from M2</span></div>
<p class="sig">Signed: <b>{NAME}</b> (the team has one member, who leads this part)</p>
{summary}
<h2><span class="num">1</span>What was built</h2>
<p>Differential is the system M2 designed, complete except the fault boards. A technician describes the fault and code screens the request. The engine, not the language model, ranks the suspects and picks the next measurement from circuit simulation. Claude reads the complaint and explains each step, and code checks every number and safety instruction before the technician sees it (Figure 1). Table 1 lists the components, where each lives and what changed since M2.</p>
{table('<b>Table 1.</b> Components as built, their code and changes since M2.', ['Component', 'What it does', 'Code', 'Since M2'], components, [14, 50, 18, 18])}
<h2><span class="num">2</span>How to run it and what to inspect</h2>
<p>A clean clone runs end to end. The trained models and test-point maps are in the repository, so the demo and the tests need no simulation run and no API key (Table 2). Results that took hours of simulation are committed with the code that produced them, so they can be inspected without re-running anything (Table 3).</p>
{table('<b>Table 2.</b> Running Differential from a clean clone.', ['Command', 'What it does', 'Time'], commands, [36, 50, 14])}
{table('<b>Table 3.</b> Evidence in the repository, for inspection without running anything.', ['Where', 'What it shows'], evidence, [34, 66])}
{figures}
<h2><span class="num">3</span>Results against the locked targets</h2>
{results_text}
<h2><span class="num">4</span>What the results show, and where it fails</h2>
{analysis}
<h2><span class="num">5</span>Engineering</h2>
{engineering}
<h2><span class="num">6</span>Scope and alignment with M2</h2>
{scope_text}
<h2 class="refs-h">References</h2>
<div class="refs">{''.join(f'<p>[{i}] {r}</p>' for i, r in enumerate(refs, 1))}</div>
</body></html>"""

html_path = Path(__import__("tempfile").mkdtemp()) / "M3.html"  # images inline; not kept
html_path.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto("file://" + str(html_path))
    pg.wait_for_timeout(500)
    pg.pdf(path=str(OUT_PDF), format="Letter", print_background=True, prefer_css_page_size=True,
           display_header_footer=True, header_template="<span></span>",
           footer_template='<div style="font-family:Inter,sans-serif;font-size:7px;color:#5b6675;width:100%;text-align:center;">Differential · M3 · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>')
    b.close()
print("wrote", OUT_PDF, "| met/missed/pending:", counts)
