# Hardware validation protocol (target T7)

T7 asks whether an engine trained only on simulation names the failed part on real
hardware. It is a primary target, locked before any hardware run (ADR-033):

> Top-1 group accuracy on at least 60 faults inserted blind into three copies of the
> 24 V driver board (20 each, one built from used parts); every test point recorded
> once per fault; the engine (trained on simulation only) and the scripted baselines
> replayed on the same readings. Met when the exact one-sided 95% lower bound clears
> 70%, that is, at least 49 of 60 named first.

Everything here is low voltage: the boards run at 15.33 V from a current-limited
bench supply (50 mA) and never above 24 V. No tube or mains hardware is used.

## 1. Boards

Build three copies of the driver block (`circuits/driver/driver.cir`) as a
*validation build*: every resistor, electrolytic capacitor and transistor sits in a
turned-pin socket, so a fault is inserted by substituting a part, not by a jumper.
The jumper board in `README.md` stays the stage-demo board.

* **Board A** and **board B**: new parts from the BOM.
* **Board C**: used parts (pulled from old equipment or old stock), checked only for
  gross failure before fitting. This is the board that tests ageing the simulator
  does not know about.

Before any fault is inserted, each board passes the healthy check (section 5).

## 2. The fault kit

A labelled kit realises every catalogued fault of the block except the two
`beta_low` transistor faults, for which no part with a controlled low gain is at
hand. That leaves 71 of the 73 catalogued faults.

| Catalogue mode | How it is inserted |
|---|---|
| Resistor `open` | Socket left empty |
| Resistor `short` | Wire link in the socket |
| Resistor `drift_x0.5`, `drift_x2`, `drift_x10` | The nearest 1% value to 0.5x, 2x or 10x nominal |
| Electrolytic `open` | Socket left empty |
| Electrolytic `short` | 1 Ω resistor in the socket |
| Electrolytic `cap_loss_50`, `cap_loss_90` | The nearest standard capacitor to half or a tenth of nominal |
| Electrolytic `high_esr` | Nominal capacitor with a series resistor of 20x its nominal ESR |
| Transistor `ce_short` | 22 Ω from collector to emitter (as on the jumper board) |
| Transistor `be_open` | Transistor fitted with its base lead out of the socket |
| Transistor `cb_leak` | 100 kΩ from collector to base |

Each kit part carries only a kit number; the list mapping kit numbers to faults is
kept by the fault setter.

## 3. Sealed draw and roles

* **Fault setter:** a team member who does not record readings. Runs
  `python hardware/fault_board/draw_faults.py --seed <private number>` once. It draws
  20 faults at random, without replacement, for each board (60 units) and writes two
  files: `sealed_key.csv` (unit id, board, fault; kept by the setter, not opened by
  anyone else until every recording is done) and `recording_sheet.csv` (unit id,
  board, one row per measurement key, value column empty).
* **Recorder:** does not know the draw. For each unit in sheet order, the setter
  inserts the fault out of sight and hands the board over; the recorder measures
  every row of that unit and fills in the value.

## 4. Recording

For each unit, record every measurement on the sheet exactly as in `procedure.md`
section 5: DC volts with the DMM (after 10 s at DC 0 V from the generator), gains as
CH1 (test point) ÷ CH2 (GEN) with ×10 probes at 0.20 Vpp, 20 Hz and 20 kHz gains at
TP22, and THD at TP22 at 1.38 Vpp. Record what the instrument shows, in the sheet's
units, including readings that look wrong. Never re-measure a reading because it
looks odd; if a probe slipped, say so in the notes column and take the reading once
more.

No part is unsoldered for testing: every method is replayed without unsoldering
tests, so every reading in T7 is real.

## 5. Healthy check

Before the faults, and again after the last one, record a full sheet on each board
with every part nominal. `eval/fault_board.py` compares each healthy reading with the
simulated healthy distribution and reports how often the engine would say "no single
fault fits" on a healthy board.

## 6. Analysis (fixed now)

After all 60 units are recorded, the setter hands over `sealed_key.csv` and anyone
runs:

```bash
python -m eval.fault_board --sheet recording_sheet.csv --key sealed_key.csv \
    [--healthy healthy_sheets.csv]
```

It replays the engine (Gaussian mixtures), the fixed-order chart, half-split tracing
and random probing on the recorded readings, each with the 40-unit budget and no
unsoldering tests, and reports: top-1 and top-3 group accuracy with exact 95%
intervals (T7 uses the engine's top-1 and the one-sided lower bound); the paired
margin over half-split tracing; results per board (board C separately); the effort
spent; and the healthy-board comparison. It writes `results/metrics.json` section
`fault_board`. Every unit is reported, including any the recorder flagged.
