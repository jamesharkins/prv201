# Fault board: jumper-selectable faults

The board realises **ten single faults**. Each one maps to exactly one hypothesis id of
the engine's catalog: `REF:mode` in `differential/sim/faults.py`, the same ids used in
training data, sessions and reports. Only catalog modes are used:

| Part kind | Catalog modes | Used on the board |
|---|---|---|
| Resistor | open, short, drift_x0.5, drift_x2, drift_x10 | open, drift_x2, drift_x10 |
| Electrolytic | open, short, cap_loss_50, cap_loss_90, high_esr | open, cap_loss_90 |
| BJT | ce_short, be_open, beta_low, cb_leak | be_open, cb_leak, ce_short |

Every number below is copied from `expected_readings.md` / `expected_readings.json`,
which `make_expected.py` generates with the project's simulation code. Those files
hold the full per-fault tables, including 5–95 % bands and accept windows.

## 1. The fault set

Each fault is one 3-pin header JFn with one shunt: **H** (pins 1–2) = healthy,
**F** (pins 2–3) = fault. In the symptom column, healthy nominal values are in
brackets. Gains are CH1 (test point) ÷ CH2 (GEN) at 0.20 Vpp.

| Shunt on F | Catalog id | Engine label | Physical realisation | Main symptom (nominal) |
|---|---|---|---|---|
| **JF1** | `C501:open` | C501 open circuit | JF1 sits in series with C501's − lead. F leaves the lead on a pin with no connection. | All DC normal. No signal after C501: gain at TP18 < 0.001 (0.988), at TP22 < 0.001 (1.94). |
| **JF2** | `Q501:be_open` | Q501 base-emitter open | JF2 sits in series with Q501's base lead. F leaves the base floating. | TP19 0.0000 V (2.999), TP20 14.13 V (9.30), TP21 13.39 V (8.59). No output. Supply 13.67 mA (9.99). |
| **JF3** | `Q501:cb_leak` | Q501 collector-base leakage | F connects RF3 (100 kΩ) from Q501's collector (TP20) to its base (TP18). | TP18 4.048 V (3.624), TP19 3.418 V (2.999), TP20 8.43 V (9.30), TP21 7.72 V (8.59). Gain 1.81 (1.94). |
| **JF4** | `R503:drift_x2` | R503 value drifted to 2x | F places a second, equal resistor RF4 (2.2 kΩ) in series with R503: 4.4 kΩ. | TP20 11.45 V (9.30), TP21 10.73 V (8.59). Gain halves: 0.969 (1.94). |
| **JF5** | `C502:cap_loss_90` | C502 capacitance loss (−90 %) | F swaps C502 (100 µF) for the degraded part CF5 (10 µF). | DC unchanged. 1 kHz gain 1.93 (1.94). Only the 20 Hz gain drops: 1.65 (1.89). |
| **JF6** | `R505:open` | R505 open circuit | JF6 sits in series with R505's lower lead. F leaves the lead unconnected. | TP18 1.265 V, TP19 0.697 V, TP20 0.665 V, TP21 0.1276 V, TP23 15.31 V (14.86). Gain 0.638. THD 32.5 % (0.165). Supply 0.49 mA. |
| **JF7** | `Q502:be_open` | Q502 base-emitter open | JF7 sits in series with Q502's base lead. | TP21 0.0000 V (8.59), TP20 9.86 V (9.30), TP23 15.26 V (14.86). No output. Supply 1.45 mA. |
| **JF8** | `Q502:ce_short` | Q502 collector-emitter short | F connects RF8 (22 Ω series safety resistor) from Q502's collector (TP23) to its emitter (TP21). | TP21 14.28 V (8.59), TP23 14.59 V (14.86). No output at 1 kHz. 20 Hz gain 0.0110. Supply 15.65 mA. |
| **JF9** | `C503:open` | C503 open circuit | JF9 sits in series with C503's − lead. | All DC normal. TP21 gain normal (1.96). TP22 gain < 0.001 (1.94). |
| **JF10** | `R509:drift_x10` | R509 value drifted to 10x | F swaps R509 (47 Ω) for RF10 (470 Ω). | TP23 11.64 V (14.86), TP18 2.838 V, TP19 2.225 V, TP20 7.51 V, TP21 6.80 V. Gain 1.93. Supply 7.86 mA. |

### Test-point coverage

This table marks each reading whose simulated band, widened by instrument noise and the
engine's variance floor, does not overlap the healthy band (↑ higher, ↓ lower;
`expected_readings.md` section 4). DC is the DMM; gain is 1 kHz unless marked.

| Shunt | Catalog id | TP17 | TP18 | TP19 | TP20 | TP21 | TP22 | TP23 |
|---|---|---|---|---|---|---|---|---|
| JF1 | `C501:open` | · | gain↓ | gain↓ | gain↓ | gain↓ | gain↓, THD↑ | · |
| JF2 | `Q501:be_open` | · | · | DC↓, gain↓ | DC↑, gain↓ | DC↑, gain↓ | gain↓, THD↑ | · |
| JF3 | `Q501:cb_leak` | · | DC↑ | DC↑ | DC↓ | DC↓ | · | · |
| JF4 | `R503:drift_x2` | · | · | · | DC↑, gain↓ | DC↑, gain↓ | gain↓ | · |
| JF5 | `C502:cap_loss_90` | · | · | · | · | · | gain↓ (20 Hz) | · |
| JF6 | `R505:open` | · | DC↓ | DC↓, gain↓ | DC↓, gain↓ | DC↓, gain↓ | gain↓, THD↑ | DC↑ |
| JF7 | `Q502:be_open` | · | · | · | DC↑ | DC↓, gain↓ | gain↓, THD↑ | DC↑ |
| JF8 | `Q502:ce_short` | · | · | · | · | DC↑, gain↓ | gain↓, THD↑ | · |
| JF9 | `C503:open` | · | · | · | · | · | gain↓, THD↑ | · |
| JF10 | `R509:drift_x10` | · | DC↓ | DC↓ | DC↓ | DC↓ | · | DC↓ |

Some DC shifts are real but smaller than that conservative overlap test. A careful
technician still sees them: TP23 drops from 14.86 V to 14.59 V with JF8 and to 14.69 V
with JF2.

**TP17** is the input reference; no board fault moves it beyond instrument tolerance.
In the whole catalog only `C501:short` does (37.0 mV DC at its 5th percentile). It is
left off the board because in that state the TP17 reading depends on the generator's
output impedance and DC behaviour. The model idealises those as a 0 V source behind
RSRC_D.

**Choice of faults.**
* Every test point TP18–TP23 is moved by at least three faults, and each fault has a
  different signature.
* Three faults show nothing on the DMM and need the scope. JF1 needs a gain reading in
  the middle of the chain (TP18–TP21). JF9 shows only at TP22. JF5 needs a 20 Hz
  reading.
* One strongly non-linear state: JF6 (THD 32.5 %).
* One supply fault: JF10.

## 2. Wiring of each header

Pin 2 (centre) is always the circuit node the model names. NC means the pin connects to
nothing; it is only a parking place for the shunt. This is exactly the wiring of the
board netlist in `make_expected.py`. Simulated with 0.05 Ω shunts, it reproduces the
catalog fault models to within 1.40 mV DC and 0.03 % gain in every position
(`expected_readings.md` section 5).

| Header | Pin 1 (H side) | Pin 2 (node) | Pin 3 (F side) | Shunt on H | Shunt on F |
|---|---|---|---|---|---|
| JF1 | C501 − lead | TP17 `drv_in` | NC | C501 in circuit | C501 disconnected: `C501:open` |
| JF2 | Q501 base leg | TP18 `q1b` | NC | base connected | base floating: `Q501:be_open` |
| JF3 | NC | TP18 `q1b` | RF3 100 kΩ (other end on TP20 `q1c`) | RF3 parked | RF3 from collector to base: `Q501:cb_leak` |
| JF4 | X: R503 lower end + RF4 | `q1e2` (R504 top) | Y: RF4 other end | R503 alone, 2.2 kΩ | R503 + RF4 = 4.4 kΩ: `R503:drift_x2` |
| JF5 | C502 + (100 µF) | `q1e2` | CF5 + (10 µF) | C502 in circuit | CF5 instead: `C502:cap_loss_90` |
| JF6 | R505 lower lead | TP20 `q1c` | NC | R505 connected | R505 disconnected: `R505:open` |
| JF7 | Q502 base leg | TP20 `q1c` | NC | base connected | base floating: `Q502:be_open` |
| JF8 | NC | TP21 `q2e` | RF8 22 Ω (other end on TP23 `vcc_d`) | RF8 parked | 22 Ω from collector to emitter: `Q502:ce_short` |
| JF9 | C503 − lead | `out_c` (R507 left end) | NC | C503 in circuit | C503 disconnected: `C503:open` |
| JF10 | R509 lower end (upper end on VREG) | TP23 `vcc_d` | RF10 lower end (upper end on VREG) | 47 Ω | 470 Ω: `R509:drift_x10` |

Where the test points sit relative to the headers matters:
* TP18 is the R501/R502 junction and TP20 is Q501's collector, both on pin 2. In the
  base-open faults they must read the model's `q1b` and `q1c` nodes, not the floating
  base legs.
* C503's + lead stays on TP21 permanently. JF9 breaks the − side, so TP21's loading does
  not change when JF9 moves.

## 3. How each fault matches its catalog model

* **Opens (JF1, JF2, JF6, JF7, JF9).** The catalog models an open as 1 GΩ (resistive
  path) or 1 fF (capacitor) (ADR-007). The board opens the lead outright. The board
  netlist uses the same 1 GΩ for an open contact.
* **`R503:drift_x2` (JF4).** The catalog doubles R503's drawn value. The board adds an
  equal 1 % resistor in series (4.4 kΩ nominal).
* **`R509:drift_x10` (JF10).** The catalog multiplies R509 by 10. The board swaps in a
  470 Ω 1 % part.
* **`C502:cap_loss_90` (JF5).** The catalog uses 0.1 × C502 (10 µF ±20 %) and keeps
  C502's ESR (1.86 Ω). CF5 is a real 10 µF ±20 % part from the same series. Its ESR limit
  is 18.6 Ω (same tan-delta), which moves the 1 kHz gain by under 1 % (1.93 against
  1.94). The 20 Hz gain, which carries this fault's signature, does not depend on it.
* **`Q501:cb_leak` (JF3).** The catalog draws the leakage resistance log-uniformly from
  47 kΩ to 470 kΩ. RF3 = 100 kΩ sits at the 33rd percentile of that range, and it is
  also the builder's default for this fault.
* **`Q502:ce_short` (JF8).** The catalog draws the short log-uniformly from 1 Ω to 50 Ω.
  RF8 = 22 Ω sits at the 79th percentile (see section 4 for why a resistor and not a
  wire).

For every jumper position, the board's nominal readings fall inside the engine's own
catalog 5–95 % band (widened by instrument tolerance) on all 16 observables
(`expected_readings.md` section 5).

## 4. Safety at 15.33 V

The operating point of every board state was simulated
(`expected_readings.md` section 7). Limits:
* resistor ratings from driver.yaml, except R506, fitted as 0.6 W;
* 2N3904: VCEO 40 V, IC 200 mA, PD 625 mW, VEBO 6.0 V (onsemi 2N3903/D);
* electrolytics never reverse-biased;
* supply at most the 50 mA current limit.

**Every single fault is within ratings.**

| Quantity | Worst single-fault value | State |
|---|---|---|
| Supply current | 15.65 mA (limit 50 mA) | JF8 |
| R506 dissipation | 204 mW (0.6 W part fitted; 82 % of the 0.25 W in driver.yaml) | JF8 |
| Transistor dissipation | 55.0 mW (Q502) | JF3 |
| Reverse base-emitter voltage | 4.81 V on Q502 (rating 6.0 V) | JF8 |
| Electrolytic polarity | never reversed, in steady state or during power-up and shunt moves | all |

**The C-E short on the emitter follower (JF8).** A collector-emitter short on Q502 puts
TP23 onto TP21. R506 (1 kΩ to ground) and R509 (47 Ω) then set the current, not the
transistor.

| | RF8 = 22 Ω (fitted) | Dead short (1 mΩ) |
|---|---|---|
| Supply current | 15.65 mA | 15.95 mA |
| R506 dissipation | 204 mW | 213 mW: 85 % of the 0.25 W in driver.yaml, 35 % of the fitted 0.6 W part |
| Q502 reverse base-emitter voltage | 4.81 V | 5.12 V |

So no part exceeds a rating even with a dead short. The **series safety resistor RF8 =
22 Ω** is fitted anyway. It keeps the physical fault inside the engine's 1–50 Ω model
range, and it adds margin. R506 is fitted as a **0.6 W** part (same 1 kΩ 1 % value)
because JF8 and JF2 (179 mW) run it above 70 % of a 0.25 W rating. When the JF8 shunt
lands on F, the surge through it peaks at 15.5 mA (simulated transient).

**Shunt and switch currents.**
* In steady state, the largest current through any header is the supply current through
  JF10: at most 15.65 mA, in the JF8 state.
* Moving JF10 briefly disconnects the driver from the supply, so the supply then
  recharges C504 at its 50 mA current limit for about 48 ms.
* Jumper shunts handle this easily. If you replace a header by a switch, choose one
  rated for at least 50 mA, at a voltage above the 15.33 V supply.

**Never set JF6 and JF8 together.** All 45 two-shunt combinations were simulated. One
exceeds a rating: with R505 open and Q502's collector shorted to its emitter, Q502's
base sits near 0.7 V while its emitter is pulled to about 14 V. That is a **13.7 V
reverse base-emitter voltage, against 6.0 V**. Every other pair stays within the limits.
Their highest supply current is 15.83 mA (JF3+JF8) and their highest R506 dissipation
205 mW (JF2+JF8).

**Catalog faults deliberately left off the board.** The simulation screened all 73
catalog faults at the current-hungriest end of their severity range.

| Catalog fault | Why it is left off |
|---|---|
| `R506:short` | Supply 87.6 mA; Q502 would dissipate 957 mW against 625 mW |
| `C504:short` | Supply 325.5 mA; R509 would dissipate 4979 mW against 500 mW |
| `C501:short` | Safe, but its TP17 reading depends on the generator's output impedance (section 1) |

Beyond these, the set was chosen for coverage and distinct signatures. A different set
of catalog faults can be substituted if it passes the same screen.

## 5. Expected ambiguity

Some board faults look like other catalog faults on every reading. In those cases the
engine is expected to name an **ambiguity group**, or to offer a lift test to split it
(`expected_readings.md` section 6).

| Shunt | Board fault | Catalog look-alikes (no single reading separates them) |
|---|---|---|
| JF4 | `R503:drift_x2` | `R505:drift_x0.5`: both halve the first stage's gain and raise TP20/TP21 |
| JF5 | `C502:cap_loss_90` | `C501:cap_loss_90`, `C501:high_esr`, `Q502:beta_low`, `Q502:cb_leak`, `R507:drift_x10` |
| JF9 | `C503:open` | `R507:open`: both break the path to the output with DC unchanged |
| all others | | none |

**Suggested use in the demo.**
* **Crisp**: one DC signature the engine should pin down with a few readings. JF2, JF3,
  JF6, JF7, JF8, JF10.
* **Scope-driven**: JF1 needs gain readings in the middle of the chain.
* **Ambiguity group**: JF4 and JF9.
* **Hard**: JF5, where only the 20 Hz gain moves and several catalog faults look alike.

## 6. Other shunt states

* **No shunt at all** is itself a catalog fault. Keep spare shunts and check the row
  before every demo.

  | Header with no shunt | State |
  |---|---|
  | JF4 | `R503:open` |
  | JF5 | `C502:open` |
  | JF10 | `R509:open`: the driver is unpowered |
  | JF1, JF2, JF6, JF7, JF9 | same as F |
  | JF3, JF8 | same as H |

* **Two shunts on F** is a double fault, outside the single-fault catalog. The engine's
  "unmodeled" hypothesis U should then gain probability. This can be shown deliberately,
  with any pair except JF6+JF8. There are no expected-reading tables for pairs.

## 7. Switches instead of shunts (optional)

For a panel-mounted version, any header can be replaced 1:1 by an SPDT switch whose
common is the centre pin:
* common = pin 2;
* one throw = pin 1 (H);
* other throw = pin 3 (F).

Label the H side of every switch, so that "all levers to H" is the healthy board.

SPST DIP switches are not used. They cannot do the two swaps (JF5, JF10), and mixing
"closed = healthy" (series faults) with "closed = fault" (added parts) would make the
healthy pattern irregular.
