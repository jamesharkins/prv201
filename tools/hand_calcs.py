"""Independent hand calculations for every healthy block (brief §2.1).

Each quantity is computed from textbook formulas (and, for the triode, Koren's
published equations evaluated directly in Python), never from ngspice. The
script then runs the nominal netlists in ngspice and writes both columns to
docs/hand_calcs.md and results/hand_calcs.json. tests/test_hand_calcs.py asserts
the agreement within the stated tolerances.

It also validates the hum approximation (ADR-005) against a full transient
simulation of a bridge rectifier + reservoir for four reservoir conditions.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LIB = ROOT / "circuits" / "lib" / "devices.lib"
VT = 0.025852  # thermal voltage at 27 C

# ---------------------------------------------------------------------------
# Device equations used by the hand calculations
# ---------------------------------------------------------------------------


def koren_ip(vpk: float, vgk: float, mu: float = 100.0, ex: float = 1.4, kg1: float = 1060.0,
             kp: float = 600.0, kvb: float = 300.0) -> float:
    x = kp * (1.0 / mu + vgk / math.sqrt(kvb + vpk * vpk))
    e1 = (vpk / kp) * (max(x, 0.0) + math.log1p(math.exp(-abs(x))))
    return 2.0 * max(e1, 0.0) ** ex / kg1


def onsemi_2n3904_vbe(ic: float) -> float:
    """Forward-active Vbe from the onsemi card: NF * Vt * ln(Ic / IS) + RB*Ib (small)."""
    return 1.5 * VT * math.log(ic / 1.26532e-10)


def zener_1n4745a_v(i: float, vz_source: float = 14.6) -> float:
    """Diodes Inc. subcircuit: VZ source + reverse diode DR (IS=5.15f, N=1.8, RS=0.897)."""
    return vz_source + 1.8 * VT * math.log(i / 5.15e-15) + 0.897 * i


# ---------------------------------------------------------------------------
# ngspice helpers
# ---------------------------------------------------------------------------


def run_ngspice(netlist: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "deck.cir"
        p.write_text(netlist)
        return subprocess.run(["ngspice", "-b", str(p)], capture_output=True, text=True,
                              timeout=300).stdout


def sim_values(circuit: str, exprs: dict[str, str], extra: str = "") -> dict[str, float]:
    """Run a circuit netlist with its own .control replaced by ours."""
    text = (ROOT / "circuits" / circuit / f"{circuit}.cir").read_text()
    text = text.replace(".include ../lib/devices.lib", f".include {LIB}")
    text = text[: text.index(".control")]
    ctl = [".control", "set noaskquit", "op"]
    for k, e in exprs.items():
        if e.startswith("ac:"):
            continue
        ctl += [f"let hq_{k} = {e}", f'echo "@@{k} $&hq_{k}"']
    ac = {k: e[3:] for k, e in exprs.items() if e.startswith("ac:")}
    by_freq: dict[str, list[tuple[str, str]]] = {}
    for k, e in ac.items():
        freq, node = e.split("|")
        by_freq.setdefault(freq, []).append((k, node))
    for freq, items in by_freq.items():
        ctl.append(f"ac lin 1 {freq} {freq}")
        for k, node in items:
            ctl += [f"let hq_{k} = mag(v({node}))", f'echo "@@{k} $&hq_{k}"']
    ctl += [extra, ".endc", ".end"]
    out = run_ngspice(text + "\n".join(ctl) + "\n")
    vals = {}
    for line in out.splitlines():
        m = re.match(r"^@@(\S+) (\S+)", line)
        if m:
            vals[m.group(1)] = float(m.group(2))
    return vals


# ---------------------------------------------------------------------------
# Hand calculations per block
# ---------------------------------------------------------------------------


def psu() -> list[dict[str, object]]:
    vpk_lv, rw_lv, c101, f = 24.06, 1.5, 2200e-6, 60.0
    # Solve the LV rail self-consistently (zener current depends on the rail).
    def rail(vun: float) -> float:
        iz_total = (vun - vz_guess[0]) / 1e3
        i_load = vreg_guess[0] / 1e3 + vreg_guess[0] / 2.2e3
        return vpk_lv - (iz_total + i_load) * (rw_lv + 1 / (4 * f * c101)) - vun
    vz_guess, vreg_guess = [16.0], [15.2]
    for _ in range(20):
        vun = brentq(rail, 15, 30)
        i_load = vreg_guess[0] / 1e3 + vreg_guess[0] / 2.2e3
        ib = i_load / 94.0  # onsemi 2N3904 hFE at ~22 mA (measured from the card)
        iz = (vun - vz_guess[0]) / 1e3 - ib
        vz_guess[0] = zener_1n4745a_v(iz)
        vreg_guess[0] = vz_guess[0] - onsemi_2n3904_vbe(i_load) - 5.8376 * ib
    i_lv_total = (vun - vz_guess[0]) / 1e3 + i_load
    ripple_lv = 2 * i_lv_total * abs(0.072 + 1 / (1j * 2 * math.pi * 120 * c101))
    # HV rail: bleeder + fixture load through the RC chain
    vpk_hv, rw_hv, c104 = 282.0, 150.0, 47e-6
    def hv(v1: float) -> float:
        i_load = (v1 - 0) / 220e3
        # load current through the RC chain into the 300k fixture
        i_b = v1 / (10e3 + 22e3 + 300e3)
        return vpk_hv - (i_load + i_b) * (rw_hv + 1 / (4 * f * c104)) - v1
    hv1 = brentq(hv, 200, 300)
    i_b = hv1 / (10e3 + 22e3 + 300e3)
    hv2 = hv1 - i_b * 10e3
    bplus = hv2 - i_b * 22e3
    sim = sim_values("psu", {"vunreg": "v(vunreg)", "vz": "v(vz)", "vreg": "v(vreg)",
                             "hv1": "v(hv1)", "hv2": "v(hv2)", "bplus": "v(bplus)"})
    # Ripple at TP1 from the hum analysis
    ripple_sim = sim_values(
        "psu", {"rip": "ac:120|vunreg"},
        extra="",
    )
    del ripple_sim  # the hum source is only enabled by the simulation layer
    return [
        row("psu", "Unregulated LV rail (TP1)", "V", vun, sim["vunreg"], 0.02,
            "Vpk - I (Rw + 1/(4 f C101)), quasi-static rectifier"),
        row("psu", "Zener reference (TP2)", "V", vz_guess[0], sim["vz"], 0.02,
            "Diodes Inc. 1N4745A: 14.6 V + 1.8 Vt ln(Iz/IS) + RS Iz"),
        row("psu", "Regulated rail (TP3)", "V", vreg_guess[0], sim["vreg"], 0.02,
            "Vz - Vbe(Q101, 22 mA) - RB Ib"),
        row("psu", "HV reservoir (TP4)", "V", hv1, sim["hv1"], 0.01,
            "Vpk - I (Rw + 1/(4 f C104))"),
        row("psu", "HV filter node (TP5)", "V", hv2, sim["hv2"], 0.01, "TP4 - I R105"),
        row("psu", "B+ (TP6)", "V", bplus, sim["bplus"], 0.01, "TP5 - I R106"),
        row("psu", "LV ripple fundamental at TP1 (hand only)", "V", ripple_lv, None, None,
            "2 Idc |ESR + 1/(j w C101)| = sawtooth fundamental I/(120 pi C)"),
    ]


def triode() -> list[dict[str, object]]:
    ra, rk, bp, rl = 100e3, 1.5e3, 250.0, 100e3
    ip = brentq(lambda i: koren_ip(bp - ra * i, -rk * i) - i, 1e-6, 5e-3)
    vp, vk = bp - ra * ip, rk * ip
    dv = 0.01
    gm = (koren_ip(vp, -vk + dv) - koren_ip(vp, -vk - dv)) / (2 * dv)
    rp = 2 * dv / (koren_ip(vp + dv, -vk) - koren_ip(vp - dv, -vk))
    mu = gm * rp
    rload = 1 / (1 / ra + 1 / rl)
    gain = mu * rload / (rp + rload)
    sim = sim_values("triode", {"cath": "v(cath)", "plate": "v(plate)",
                                "ip": "-i(VBPLUS_BENCH)", "g": "ac:1000|tone_in"})
    ds_ip = koren_ip(250.0, -2.0)
    return [
        row("triode", "Plate current", "mA", 1e3 * ip, 1e3 * sim["ip"], 0.01,
            "solve Ip = Koren(Vp = B+ - Ra Ip, Vgk = -Rk Ip)"),
        row("triode", "Cathode voltage (TP8)", "V", vk, sim["cath"], 0.01, "Rk Ip"),
        row("triode", "Plate voltage (TP9)", "V", vp, sim["plate"], 0.01, "B+ - Ra Ip"),
        row("triode", "Mid-band gain into 100k (TP10)", "V/V", gain, sim["g"], 0.03,
            "mu (Ra||RL) / (rp + Ra||RL), gm and rp from the Koren equations"),
        row("triode", "Koren Ip at Va=250 V, Vg=-2 V (datasheet 1.2 mA)", "mA", 1e3 * ds_ip,
            None, None, "model vs Philips ECC83 typical characteristics"),
    ]


def tone() -> list[dict[str, object]]:
    """Nodal analysis of the passive Baxandall with numpy (independent of SPICE)."""
    def gain(f: float) -> float:
        w = 2 * math.pi * f
        yc = lambda c: 1j * w * c  # noqa: E731
        yr = lambda r: 1 / r  # noqa: E731
        # unknown nodes: tin, ba, bt, bw, bb, ta, tt, tb, out
        n = ["tin", "ba", "bt", "bw", "bb", "ta", "tt", "tb", "out"]
        idx = {k: i for i, k in enumerate(n)}
        Y = np.zeros((9, 9), dtype=complex)
        I = np.zeros(9, dtype=complex)

        def br(a: str, b: str | None, y: complex) -> None:
            ia = idx[a]
            Y[ia, ia] += y
            if b is None:
                return
            ib = idx[b]
            Y[ib, ib] += y
            Y[ia, ib] -= y
            Y[ib, ia] -= y

        br("tin", None, yr(43e3))
        I[idx["tin"]] += 1 / 43e3  # 1 V source through 43k
        br("tin", "ba", yr(47e3))
        br("ba", "bt", yr(90e3))
        br("bt", "bb", yr(10e3))
        br("bt", "bw", yr(1.0))
        br("ba", "bw", yc(10e-9))
        br("bw", "bb", yc(100e-9))
        br("bb", None, yr(4.7e3))
        br("bw", "out", yr(33e3))
        br("tin", "ta", yc(1e-9))
        br("ta", "tt", yr(90e3))
        br("tt", "tb", yr(10e3))
        br("tt", "out", yr(1.0))
        br("tb", None, yc(10e-9))
        br("out", None, yr(100e3))
        v = np.linalg.solve(Y, I)
        return float(abs(v[idx["out"]]))

    sim = sim_values("tone", {"g1k": "ac:1000|tone_out", "g20": "ac:20|tone_out",
                              "g20k": "ac:20000|tone_out"})
    out = []
    for f, key in ((20.0, "g20"), (1000.0, "g1k"), (20000.0, "g20k")):
        h = 20 * math.log10(gain(f))
        s = 20 * math.log10(sim[key])
        out.append(row("tone", f"Response at {f:g} Hz", "dB", h, s, None,
                       "nodal analysis (numpy), tone controls centred", abs_tol=0.1))
    return out


def opamp() -> list[dict[str, object]]:
    vcc = 15.33
    vref = vcc * 22e3 / 44e3
    gain = (1 + 100e3 / 10e3) * 100e3 / (100e3 + 20e3)
    f3 = 3e6 / 11
    g20k = gain / math.sqrt(1 + (20e3 / f3) ** 2)
    sim = sim_values("opamp", {"vref": "v(vref)", "out": "v(op_pin)",
                               "g": "ac:1000|op_pin", "g20k": "ac:20000|op_pin"})
    return [
        row("opamp", "Half-supply bias (TP16)", "V", vref, sim["vref"], 0.005, "Vcc R403/(R402+R403)"),
        row("opamp", "Output DC (TP15)", "V", vref, sim["out"], 0.005, "unity DC gain (C403)"),
        row("opamp", "Gain at 1 kHz from a 20k source (TP15)", "V/V", gain, sim["g"], 0.01,
            "(1 + R404/R405) R401/(R401 + Rsrc)"),
        row("opamp", "Gain at 20 kHz (TP15)", "V/V", g20k, sim["g20k"], 0.01,
            "single pole at GBW/11"),
    ]


def driver() -> list[dict[str, object]]:
    vreg = 15.33
    # total supply current ~ 10 mA through R509 (iterate once)
    itot = 0.010
    vccd = vreg - 47 * itot
    vth, rth = vccd * 13e3 / 52e3, 39e3 * 13e3 / 52e3
    beta1 = 119.0
    ie = 0.0012
    for _ in range(20):
        ie = (vth - onsemi_2n3904_vbe(ie)) / (2670 + rth / (beta1 + 1))
    ve = ie * 2670
    vb = ve + onsemi_2n3904_vbe(ie)
    ie2 = 0.0086
    beta2 = 122.0  # onsemi 2N3904 card hFE at ~8.6 mA (measured)
    for _ in range(20):
        vc = vccd - (ie + ie2 / (beta2 + 1)) * 4.7e3  # R505 also feeds Q502's base
        ie2 = (vc - onsemi_2n3904_vbe(ie2)) / 1e3
    ve2 = vc - onsemi_2n3904_vbe(ie2)
    re1 = VT / ie
    rin_ef = 122.0 * 1e3
    rc_eff = 1 / (1 / 4.7e3 + 1 / rin_ef)
    gain = rc_eff / (re1 * 1.5 + 2.2e3)  # NF = 1.5 in the onsemi card scales re
    sim = sim_values("driver", {"q1b": "v(q1b)", "q1e": "v(q1e)", "q1c": "v(q1c)",
                                "q2e": "v(q2e)", "g": "ac:1000|out"})
    return [
        row("driver", "Q501 base (TP18)", "V", vb, sim["q1b"], 0.03, "Thevenin divider, Ie loop"),
        row("driver", "Q501 emitter (TP19)", "V", ve, sim["q1e"], 0.03, "Ie (R503 + R504)"),
        row("driver", "Q501 collector (TP20)", "V", vc, sim["q1c"], 0.03,
            "Vcc_d - (Ic1 + Ib2) R505"),
        row("driver", "Q502 emitter (TP21)", "V", ve2, sim["q2e"], 0.03, "TP20 - Vbe(Q502)"),
        row("driver", "Gain at 1 kHz (TP22)", "V/V", gain, sim["g"], 0.05,
            "(R505 || beta R506) / (NF re + R503)"),
    ]


def row(block: str, name: str, unit: str, hand: float, sim: float | None, rel_tol: float | None,
        method: str, abs_tol: float | None = None) -> dict[str, object]:
    err = None
    ok = None
    if sim is not None:
        err = sim - hand
        if abs_tol is not None:
            ok = abs(err) <= abs_tol
        elif rel_tol is not None:
            ok = abs(err) <= rel_tol * max(abs(hand), 1e-9)
    return {"block": block, "quantity": name, "unit": unit, "hand": hand, "sim": sim,
            "rel_tol": rel_tol, "abs_tol": abs_tol, "error": err, "ok": ok, "method": method}


# ---------------------------------------------------------------------------
# Hum approximation vs full transient
# ---------------------------------------------------------------------------

TRANSIENT_RECT = """full-wave bridge + reservoir, transient reference
.model DBR D(IS=2.52n RS=0.1 N=1.752)
Vsec a b SIN(0 {vpk} 60)
Rw a a1 1.5
Rg b 0 1Meg
D1 a1 p DBR
D2 b p DBR
D3 0 a1 DBR
D4 0 b DBR
C1 p c1 {c}
Resr c1 0 {esr}
Iload p 0 DC {iload}
.ic v(p)={vic}
.control
set noaskquit
tran 20u 0.35 0.25 20u uic
fourier 120 v(p)
.endc
.end
"""


def hum_validation() -> list[dict[str, object]]:
    rows = []
    iload = 0.030
    for label, c, esr in (("nominal", 2200e-6, 0.072), ("-50 %", 1100e-6, 0.072),
                          ("-90 %", 220e-6, 0.072), ("ESR x 50", 2200e-6, 3.6)):
        # Secondary peak chosen so the rectified peak is ~24 V (two diode drops).
        vic = 25.5 - 1.4 - iload / (4 * 60 * c)
        out = run_ngspice(TRANSIENT_RECT.format(vpk=25.5, c=c, esr=esr, iload=iload, vic=vic))
        mag = None
        for line in out.splitlines():
            m = re.match(r"^\s*1\s+120\s+([0-9.eE+-]+)", line)
            if m:
                mag = float(m.group(1))
                break
        small_signal = 2 * iload * abs(esr + 1 / (1j * 2 * math.pi * 120 * c))
        rows.append({"condition": label, "transient_V": mag, "small_signal_V": small_signal,
                     "ratio": (small_signal / mag) if mag else None})
    return rows


def main() -> None:
    rows = psu() + triode() + tone() + opamp() + driver()
    hum = hum_validation()
    out = {"rows": rows, "hum_validation": hum}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "hand_calcs.json").write_text(json.dumps(out, indent=2))
    lines = [
        "# Hand calculations vs simulation",
        "",
        "Generated by `tools/hand_calcs.py` (do not edit by hand). Hand values use",
        "textbook formulas and the published device equations evaluated directly in",
        "Python; simulated values come from the nominal netlists in ngspice.",
        "`tests/test_hand_calcs.py` fails if any row with a tolerance disagrees.",
        "",
        "| Block | Quantity | Hand | ngspice | Error | Tolerance | Method |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        hand = f"{r['hand']:.4g} {r['unit']}"
        sim = "-" if r["sim"] is None else f"{r['sim']:.4g} {r['unit']}"
        err = "-" if r["error"] is None else f"{r['error']:+.3g}"
        tol = ("-" if r["rel_tol"] is None and r["abs_tol"] is None
               else (f"±{100 * r['rel_tol']:.1f} %" if r["rel_tol"] is not None
                     else f"±{r['abs_tol']:.1f} dB"))
        lines.append(f"| {r['block']} | {r['quantity']} | {hand} | {sim} | {err} | {tol} | {r['method']} |")
    lines += [
        "",
        "## Hum model check (ADR-005)",
        "",
        "Ripple fundamental at the LV reservoir, 30 mA load: full transient simulation of a",
        "bridge rectifier and reservoir versus the small-signal model used in the Monte Carlo",
        "(injected 120 Hz current of amplitude 2 Idc into ESR + C).",
        "",
        "| Reservoir | Transient (V) | Small-signal model (V) | Model / transient |",
        "|---|---|---|---|",
    ]
    for h in hum:
        tr = "n/a" if h["transient_V"] is None else f"{h['transient_V']:.4g}"
        ratio = "n/a" if h["ratio"] is None else f"{h['ratio']:.2f}"
        lines.append(f"| {h['condition']} | {tr} | {h['small_signal_V']:.4g} | {ratio} |")
    ratios = [h["ratio"] for h in hum if h["ratio"] is not None]
    lines += [
        "",
        f"Across these conditions the small-signal model over-states the transient ripple",
        f"fundamental by {100 * (min(ratios) - 1):.1f} % to {100 * (max(ratios) - 1):.1f} %"
        " (the 2 Idc amplitude assumes",
        "narrow charging pulses; real conduction pulses are wider, which lowers the fundamental).",
        "Not modelled: harmonics above 120 Hz, and regulator drop-out on ripple troughs, which",
        "would add hum beyond this estimate on the regulated rail when the reservoir has lost",
        "most of its capacitance.",
        "",
    ]
    (ROOT / "docs" / "hand_calcs.md").write_text("\n".join(lines))
    bad = [r for r in rows if r["ok"] is False]
    print(f"{len(rows)} rows, {len(bad)} outside tolerance")
    for r in bad:
        print("  OUT:", r["block"], r["quantity"], r["hand"], r["sim"])
    for h in hum:
        print("  hum", h)


if __name__ == "__main__":
    main()
