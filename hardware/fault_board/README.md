# Differential fault board: build guide

A breadboard or perfboard build of the project's **Block 5 BJT line driver**
(`circuits/driver/driver.cir`, `circuits/driver/driver.yaml`). Ten jumper headers
inject ten of the engine's catalog faults. The team can then diagnose real hardware on
stage with the same engine, models and fault catalog used in simulation.

| File | What it is |
|---|---|
| `README.md` | This build guide: safety, tools, assembly, test points, power-up, healthy check, use with the demo |
| `BOM.csv` | Bill of materials: driver parts, fixtures, fault-injection parts |
| `faults.md` | The ten jumper faults, how each is wired, and which catalog hypothesis it maps to |
| `expected_readings.md` | Simulated readings for the healthy board and every fault (generated, do not edit) |
| `expected_readings.json` | The same numbers in machine-readable form |
| `make_expected.py` | Regenerates the two files above from the project's simulation code |
| `procedure.md` | On-stage script for diagnosing one hidden fault |

## 1. Purpose

* **Same circuit as the model.** Every part value is identical to the simulated block,
  so the engine's models apply directly. So are the fixtures: the 15.33 V supply
  `VREG_BENCH`, the 100 Ω source resistor `RSRC_D` and the 10 kΩ load `RLOAD_EXT`. The
  only rating change is **R506**, fitted as a 0.6 W part; its value is unchanged.
  Two fault states dissipate up to 204 mW in it (82 % of the 0.25 W in driver.yaml);
  see `expected_readings.md` section 7.
* **Faults by jumper.** Each fault is one 3-pin header with a shunt. Shunt on H (pins
  1–2) = healthy, shunt on F (pins 2–3) = fault. Every fault maps to exactly one catalog
  hypothesis id such as `Q502:ce_short` (see `faults.md`).
* **Low voltage only.** The board runs at 15.33 V and never above 24 V.

## 2. Safety

* **Low voltage only.** Use a current-limited bench supply at **15.33 V (the "15 V"
  rail) with a 50 mA limit**, never more than 24 V. The highest current any board state
  draws is 15.65 mA (JF8, simulated), so the limit trips only on a wiring fault or a
  short. The project's SCPI DMM path refuses readings above 24 V for the same reason.
* **No mains wiring on the board.** The only mains-powered items are the bench
  instruments, in their own cases. Do not add a transformer, a mains lead or a rectifier
  to the board.
* **No tube or high-voltage hardware.** The triode and PSU blocks of the project run at
  250 V and above. They exist in simulation only. Never connect this board, its leads or
  its probes to them.
* **Eye protection when soldering and when cutting leads**; clipped leads fly. Solder in
  a ventilated place or with fume extraction. Wash your hands after handling leaded
  solder.
* **Electrolytic polarity.** Five electrolytics (C501–C504, CF5) must go in the right
  way round (section 4.3). A reversed electrolytic can vent. D1 clamps a reversed
  supply connection to about one diode drop. Together with the 50 mA limit, this
  protects the board.
* **Warm parts.** R506 runs warm in the JF2 and JF8 fault states (179 mW and 204 mW).
  Do not leave a fault set for longer than the demo needs.
* **Transients on TP22.** Moving a shunt makes the output swing by up to 13.68 V for a
  few seconds (JF6, simulated). This is harmless into the fixture load. Do not connect
  anything to TP22 except the probe.

## 3. Tools and instruments

| Item | Requirement | Why |
|---|---|---|
| DMM | DC volts, ±(0.5 % + 2 counts), 6000-count autoranging (600 mV / 6 V / 60 V ranges) | This is the engine's measurement model (ADR-008). A better meter is fine. A worse one makes readings look like faults. |
| Oscilloscope | 2 channels, ×10 probes on both | Gains are CH1 (test point) ÷ CH2 (GEN). ×10 probes keep loading off the high-impedance nodes: TP20 behind R505 (4.7 kΩ) and TP18 behind R501 ∥ R502 (9.75 kΩ). |
| Signal generator | Sine 20 Hz, 1 kHz, 20 kHz; 0.20 Vpp and 1.38 Vpp at GEN; DC 0 V mode (or 0 V offset with minimum amplitude) | Test levels from `expected_readings.md` section 8 |
| Bench supply | 0–30 V, adjustable current limit, set to 15.33 V / 50 mA | Fixture `VREG_BENCH` |
| Distortion analyser *(optional)* | THD at 1 kHz | Only if the agent asks for `thd:TP22` (a scope FFT with at least 60 dB of dynamic range also works) |
| LCR/ESR meter and transistor tester *(optional)* | | Pre-build part check |
| Soldering iron, solder, side cutters, wire strippers, tweezers, safety glasses, fume extraction | | Perfboard build |
| 830-point solderless breadboard, 22 AWG solid wire | | Breadboard build |

## 4. The circuit on the board

### 4.1 Schematic

This is the driver netlist with the ten jumper headers drawn in (`=JFn=` marks where a
header sits). Values are those of `circuits/driver/driver.cir`.

```
 VREG o--+--[R509 47R]--=JF10=--+---------------- vcc_d (TP23) -------+---------------+
 15.33V  |  (F: RF10 470R       |                   |                  |               |
         |   instead of R509)  C504+ 220u        R501 39k          R505 4.7k        Q502 C
        D1 1N4001               |                   |                =JF6=          2N3904
        (cathode to VREG)      GND                  |                  |               |
         |                                          |    q1c (TP20) ---+----=JF7=--- Q502 B
 GND o---+                                          |                  |               |
                                                    |               Q501 C          Q502 E
 GEN o--[RSRC_D 100R]--+--=JF1=--(-) C501 10u (+)---+-- q1b (TP18)     |               |
                       |                            |    |          Q501 2N3904     q2e (TP21)
                  drv_in (TP17)                  R502    +--=JF2=-- Q501 B             |
                                                  13k                  |          +----+-----+
                                                    |               Q501 E        |          |
                                                   GND                 |       R506 1k    (+) C503 100u
                                                                  q1e (TP19)   0.6 W      (-)
                                                                       |          |          |
                                                                   R503 2.2k     GND      =JF9=
                                                                       |                     |
                                                                    =JF4=  (F: RF4 2.2k    out_c
                                                                       |    added in series) |
                                                                     q1e2 ----+       R507 47R
                                                                       |      |              |
                                                                   R504 470R =JF5=     out (TP22)
                                                                       |      |         |      |
                                                                      GND  (+) C502   R508   RLOAD_EXT
                                                                            100u      100k   10k
                                                                           (F: CF5    |      |
                                                                            10u)     GND    GND
                                                                           (-) GND

 Added only in the F position:  JF3: RF3 100k from q1c (TP20) to q1b (TP18)
                                JF8: RF8 22R  from vcc_d (TP23) to q2e (TP21)
```

The node names (`vcc_d`, `q1b`, `q1e`, `q1c`, `q2e`, `out`, `drv_in`, `drv_src`) are the
netlist's. The engine knows the test points by these names.

### 4.2 Header convention

Every fault header is a 3-pin 0.1" header with one shunt:

```
   pin 1   pin 2   pin 3
    (H)   (node)    (F)
     o-------o       o      shunt on 1-2 = healthy
     o       o-------o      shunt on 2-3 = fault
```

* **Pin 2 (centre)** is always the circuit node the model names (for example TP20 for JF6).
* **Pin 1** carries the healthy connection. **Pin 3** carries the fault connection, or
  nothing (NC).
* **All shunts on the H side = healthy board.** Line the headers up in one row with
  pin 1 on the same side, so a healthy board shows a straight row of shunts.
* **A missing shunt is itself a fault:**
  * JF4 with no shunt = `R503:open`.
  * JF5 with no shunt = `C502:open`.
  * JF10 with no shunt = `R509:open`, which unpowers the whole driver.
  * On the series headers (JF1, JF2, JF6, JF7, JF9) no shunt is the same as F.
  * On JF3 and JF8 no shunt is the same as H.

  Keep two spare shunts on the bench.

Pin-by-pin wiring of all ten headers is in `faults.md` (section 2). The board-level
netlist that `make_expected.py` simulates uses exactly this wiring. It reproduces the
engine's fault models to within 1.40 mV DC and 0.03 % gain (`expected_readings.md`
section 5).

### 4.3 Orientation and polarity

| Part | Orientation |
|---|---|
| Q501, Q502 (2N3904, TO-92) | Flat face towards you: **E-B-C from the left** (driver.yaml hint). Check the datasheet of the exact part you buy: some TO-92 variants differ. |
| C501 10 µF | **+ to TP18 (q1b)**, − to JF1 pin 1 |
| C502 100 µF | **+ to JF5 pin 1**, − to GND |
| CF5 10 µF | **+ to JF5 pin 3**, − to GND |
| C503 100 µF | **+ to TP21 (q2e)**, − to JF9 pin 1 |
| C504 220 µF | **+ to TP23 (vcc_d)**, − to GND |
| D1 1N4001 | **Cathode (band) to VREG**, anode to GND. Reverse-biased in normal use. |

Each + lead goes on the node that is more positive in the healthy board. The simulated
transients confirm that no electrolytic is reverse-biased during power-up or during any
shunt move (`expected_readings.md` section 10).

### 4.4 Test points

| Post | Node | driver.yaml name | Where | Healthy DC (nominal) |
|---|---|---|---|---|
| GEN | `drv_src` | (generator side of RSRC_D) | Generator signal and scope CH2 | 0 V (generator at DC 0 V) |
| TP17 | `drv_in` | Line-driver input | Right end of RSRC_D, JF1 pin 2 | 0.0000 V |
| TP18 | `q1b` | Q501 base | R501/R502/C501+ junction, JF2 pin 2. Not the base leg itself: that sits behind JF2 | 3.624 V |
| TP19 | `q1e` | Q501 emitter | Q501 emitter leg, top of R503 | 2.999 V |
| TP20 | `q1c` | Q501 collector / Q502 base | Q501 collector leg, JF6 and JF7 pin 2. R505 and Q502's base reach it through JF6 and JF7 | 9.30 V |
| TP21 | `q2e` | Q502 emitter | Q502 emitter leg, top of R506, C503+ | 8.59 V |
| TP22 | `out` | Line output | Right end of R507, top of R508 and RLOAD_EXT | 0.0000 V |
| TP23 | `vcc_d` | Driver supply | JF10 pin 2, C504+, Q502 collector | 14.86 V |
| VREG | `vreg` | (bench supply +) | Supply input | 15.33 V |
| GND ×2 | `0` | | One at the input end, one at the output end, for probe and generator grounds | |

**Marking and exposing the test points.**
* **Perfboard.** Use turret posts or PCB test loops in one row along the top edge, in
  the order above. Suggested colours: yellow for TP17–TP23, white for GEN, red for VREG,
  black for GND.
* **Breadboard.** Push a single male header pin into the net's column (row a) as the
  probe point.
* **Labels.** Put a printed label next to each post with the TP id and the node name,
  for example `TP20 q1c`. The agent asks for test points by id, and the node name lets
  you check against the schematic.
* **Wire lengths.** Keep the TP wire short; a post should hang off its node, not sit
  between two parts. Take TP18 and TP20 from the circuit-node side of the headers, as
  in the table. That way, in the base-open faults they read what the model's `q1b` and
  `q1c` read.

## 5. Assembly

### 5.1 Before you start

1. Check every part against `BOM.csv`.
2. Measure each resistor with the DMM. It must be inside its tolerance (1 % metal film,
   5 % for R508). The engine's Monte Carlo assumes exactly these tolerances. If you have
   a transistor tester, check both 2N3904s read hFE between 100 and 300, the datasheet
   window the draws cover (ADR-006).
3. Print the test-point labels and a header label strip. The strip shows JF1…JF10 with
   H on the pin-1 side and F on the pin-3 side.

### 5.2 Solderless breadboard (830 points, columns 1–63)

**Rails.** Tie the two − rails together at both ends so that GND is continuous. On a
board with split rails, also bridge the rail halves at the middle.

| Rail | Net |
|---|---|
| Top + | vcc_d (TP23) |
| Top − | GND |
| Bottom + | VREG (bench supply +) |
| Bottom − | GND (bench supply −) |

**Step 1: circuit nets in the upper half (rows a–e).** One net per column. Columns not
listed stay empty.

| Col | Net | Parts and wires in this column |
|---|---|---|
| 1 | GEN `drv_src` | GEN pin; RSRC_D lead |
| 4 | TP17 `drv_in` | RSRC_D other lead; TP17 pin; wire to JF1 pin 2 |
| 6 | `jf1_1` | C501 − lead; wire to JF1 pin 1 |
| 8 | TP18 `q1b` | C501 + lead; R501 (other lead in top + rail); R502 (other lead in top − rail); TP18 pin; wire to JF2 pin 2 |
| 10 | TP19 `q1e` | Q501 E; R503 lead; TP19 pin |
| 11 | `jf2_1` | Q501 B; wire to JF2 pin 1 |
| 12 | TP20 `q1c` | Q501 C; RF3 lead; TP20 pin; wire to JF6 pin 2 |
| 14 | `jf3_3` | RF3 other lead; wire to JF3 pin 3 |
| 16 | `jf6_1` | R505 lead (other lead in top + rail); wire to JF6 pin 1 |
| 18 | `jf4_1` (X) | R503 other lead; RF4 lead; wire to JF4 pin 1 |
| 21 | `jf4_3` (Y) | RF4 other lead; wire to JF4 pin 3 |
| 23 | `q1e2` | R504 (other lead in top − rail); wires to JF4 pin 2 and JF5 pin 2 |
| 25 | `jf5_1` | C502 + lead (− lead in top − rail); wire to JF5 pin 1 |
| 27 | `jf5_3` | CF5 + lead (− lead in top − rail); wire to JF5 pin 3 |
| 29 | `jf9_1` | C503 − lead; wire to JF9 pin 1 |
| 30 | TP21 `q2e` | C503 + lead; Q502 E; R506 (other lead in top − rail); TP21 pin; wire to JF8 pin 2 |
| 31 | `jf7_1` | Q502 B; wire to JF7 pin 1 |
| 32 | vcc_d (local) | Q502 C; RF8 lead; wire to top + rail |
| 34 | `jf8_3` | RF8 other lead; wire to JF8 pin 3 |
| 36 | `out_c` | R507 lead; wire to JF9 pin 2 |
| 38 | TP22 `out` | R507 other lead; R508 (other lead in top − rail); RLOAD_EXT (other lead in top − rail); TP22 pin |

Q501 sits in columns 10-11-12 and Q502 in 30-31-32, flat face towards you (E-B-C).

**Step 2: rail parts.**

| Part | Placement |
|---|---|
| C504 | + in the top + rail, − in the top − rail (around column 40) |
| D1 | Cathode in the bottom + rail, anode in the bottom − rail (around column 50) |
| TP23 pin | Top + rail |
| VREG pin | Bottom + rail |
| GND pins | Top − rail, near columns 1 and 40 |

**Step 3: header bank in the lower half (row f).** Pin 1 is always the left pin. Pins
marked NC go in columns with nothing else in them. Plain column numbers in the last
column are upper-half columns from step 1. JF3 and JF7 take their pin 2 from the
neighbouring header's pin 2 in the lower half, because a breadboard column has only
five holes.

| Header | Pin 1 col | Pin 2 col | Pin 3 col | Wires from the lower half |
|---|---|---|---|---|
| JF1 | 2 | 3 | 4 (NC) | 2→col 6, 3→col 4 |
| JF2 | 6 | 7 | 8 (NC) | 6→col 11, 7→col 8 |
| JF3 | 10 (NC) | 11 | 12 | 11→lower col 7 (JF2 pin 2), 12→col 14 |
| JF4 | 14 | 15 | 16 | 14→col 18, 15→col 23, 16→col 21 |
| JF5 | 18 | 19 | 20 | 18→col 25, 19→col 23, 20→col 27 |
| JF6 | 22 | 23 | 24 (NC) | 22→col 16, 23→col 12 |
| JF7 | 26 | 27 | 28 (NC) | 26→col 31, 27→lower col 23 (JF6 pin 2) |
| JF8 | 30 (NC) | 31 | 32 | 31→col 30, 32→col 34 |
| JF9 | 34 | 35 | 36 (NC) | 34→col 29, 35→col 36 |
| JF10 | 38 | 39 | 40 | R509 from the bottom + rail into col 38 (lower); RF10 from the bottom + rail into col 40 (lower); col 39 (lower) → top + rail |

**Step 4: shunts and checks.** Put every shunt on pins 1–2 (H). Then work through the
continuity checklist (section 5.4) with the DMM in continuity mode, power off.

### 5.3 Perfboard (0.1" pitch, about 100 × 80 mm)

**Layout.** Signal flows left to right. The supply parts sit along the top, a GND bus
runs along the bottom, the headers form one row at the bottom edge so one cover hides
them all, and the test posts form one row at the top edge.

```
  GND   GEN  TP17 TP18 TP19 TP20 TP21 TP22 TP23 VREG  GND        <- test posts (top edge)
   o     o    o    o    o    o    o    o    o    o     o
 +--------------------------------------------------------------------+
 | J1(+ -)  D1   R509  RF10     ===== vcc_d bus ===== (C504+)          |
 |                                                                    |
 | RSRC_D  C501(-  +)  R501    R505     RF3        Q502   RF8          |
 |                     R502    Q501(E B C)         (E B C)             |
 |                             R503   RF4          R506   C503(+  -)   |
 |                             R504   C502(+)  CF5(+)      R507        |
 |                                                         R508 RLOAD  |
 | ======================== GND bus =================================  |
 |  JF1  JF2  JF3  JF4  JF5  JF6  JF7  JF8  JF9  JF10                  |
 |  [H]  [H]  [H]  [H]  [H]  [H]  [H]  [H]  [H]  [H]   <- pin 1 row    |
 |  [.]  [.]  [.]  [.]  [.]  [.]  [.]  [.]  [.]  [.]   <- pin 2 row    |
 |  [F]  [F]  [F]  [F]  [F]  [F]  [F]  [F]  [F]  [F]   <- pin 3 row    |
 +--------------------------------------------------------------------+
   headers mounted with pins in a vertical line: shunt up = H, shunt down = F
```

**Build order.** Work from low parts to tall parts, and test as you go.

1. **Buses.** Lay the vcc_d bus and the GND bus (tinned copper wire), and the supply
   input J1 and D1 (band to VREG).
2. **Header row.** Solder the ten 3-pin headers in one straight row, pin 1 towards the
   circuit. Label the row above the headers H and the row below F.
3. **Resistors.** Fit R501–R509, then RSRC_D and RLOAD_EXT, keeping every lead short.
   Fit R506 (the 0.6 W part) 2–3 mm off the board so it can shed heat.
4. **Fault parts.** Fit RF3, RF4, RF8 and RF10 next to their headers:
   * RF3 from the q1c node to JF3 pin 3;
   * RF4 between JF4 pins 1 and 3;
   * RF8 from the vcc_d bus to JF8 pin 3;
   * RF10 from VREG to JF10 pin 3.
5. **Transistors.** Fit Q501 and Q502 (E-B-C, flat face towards you). Keep about 5 mm
   of lead so the header links to the base legs stay short.
6. **Electrolytics.** Fit C501–C504 and CF5, checking polarity against section 4.3.
7. **Header links.** Wire each header pin as in `faults.md` section 2. Keep each link
   under 5 cm, and twist the two wires of each series header (JF1, JF2, JF6, JF7, JF9)
   together.
8. **Test posts.** Fit the posts and labels (section 4.4).
9. **Checks.** Inspect every joint with a loupe, then run the continuity checklist
   (section 5.4).

### 5.4 Continuity checklist (power off, all shunts on H)

Each line is one net of the simulated board netlist. Everything listed must beep
together, and nothing else may.

| Net | Must connect |
|---|---|
| VREG | J1 +, D1 cathode, R509 (upper end), RF10 (upper end), VREG post |
| GND | J1 −, D1 anode, R502, R504, C502 −, CF5 −, C504 −, R506, R508, RLOAD_EXT, GND posts |
| vcc_d (TP23) | JF10 pin 2, C504 +, R501 (upper), R505 (upper), Q502 C, RF8 (upper end) |
| GEN `drv_src` | RSRC_D (left), GEN post |
| TP17 `drv_in` | RSRC_D (right), JF1 pin 2 |
| `jf1_1` | C501 −, JF1 pin 1 |
| TP18 `q1b` | C501 +, R501, R502, JF2 pin 2, JF3 pin 2 |
| `jf2_1` | Q501 B, JF2 pin 1 |
| TP19 `q1e` | Q501 E, R503 (upper) |
| X `jf4_1` | R503 (lower), RF4 (one end), JF4 pin 1 |
| Y `jf4_3` | RF4 (other end), JF4 pin 3 |
| `q1e2` | R504, JF4 pin 2, JF5 pin 2 |
| `jf5_1` | C502 +, JF5 pin 1 |
| `jf5_3` | CF5 +, JF5 pin 3 |
| TP20 `q1c` | Q501 C, JF6 pin 2, JF7 pin 2, RF3 (one end) |
| `jf3_3` | RF3 (other end), JF3 pin 3 |
| `jf6_1` | R505 (lower), JF6 pin 1 |
| `jf7_1` | Q502 B, JF7 pin 1 |
| TP21 `q2e` | Q502 E, R506, C503 +, JF8 pin 2 |
| `jf8_3` | RF8 (lower end), JF8 pin 3 |
| `jf9_1` | C503 −, JF9 pin 1 |
| `out_c` | JF9 pin 2, R507 (left) |
| TP22 `out` | R507 (right), R508, RLOAD_EXT |
| `jf10_1` | R509 (lower), JF10 pin 1 |
| `jf10_3` | RF10 (lower), JF10 pin 3 |
| NC pins | JF1 pin 3, JF2 pin 3, JF3 pin 1, JF6 pin 3, JF7 pin 3, JF8 pin 1, JF9 pin 3: connected to nothing |

## 6. Power-up and healthy-unit verification

All expected values below are in `expected_readings.md` section 2, which is the
reference.

**Power-up**

1. Put all shunts on H. Connect nothing to the board yet.
2. Set the bench supply to **15.33 V** with its **current limit at 50 mA**, then switch
   its output off.
3. Connect the supply to VREG and GND. Switch the output on while watching the current.
   The CC indicator may flash while C504 charges; the simulation puts this at 65 ms.
   The current then settles near **9.99 mA** (5–95 %: 9.94 to 10.14 mA). If CC stays on,
   or the current is far from 10 mA, switch off and recheck the wiring.
4. Adjust the supply until the **DMM at the VREG post reads 15.33 V**. Every DC reading
   moves with the supply; TP23, for example, moves 0.097 V per 0.1 V
   (`expected_readings.md` section 9). Use the DMM reading, not the supply's own
   display.
5. Connect the generator to GEN (its ground to a GND post) and set it to **DC 0 V**,
   output on. The model always has the generator in circuit; with the output off, TP17
   floats.
6. **Wait 10 s.** The slowest test point settles 6.2 s after power-up (simulated).

**Healthy check**

7. **DC readings.** Measure TP17…TP23 with the DMM and compare each with the accept
   window:

   | Test point | Nominal | Accept window |
   |---|---|---|
   | TP17 | 0.0000 V | within ±0.010 V |
   | TP18 | 3.624 V | 3.581 to 3.694 V |
   | TP19 | 2.999 V | 2.960 to 3.065 V |
   | TP20 | 9.30 V | 9.14 to 9.54 V |
   | TP21 | 8.59 V | 8.44 to 8.82 V |
   | TP22 | 0.0000 V | within ±0.100 V |
   | TP23 | 14.86 V | 14.76 to 14.96 V |

   TP17 and TP22 read a few millivolts on real hardware (generator offset, C503
   leakage). The model has neither, so small readings there are entered as 0
   (`expected_readings.md` section 1).
8. **Gain.** Set the generator to a 1 kHz sine, **0.20 Vpp measured at GEN**. Put CH1
   on TP22 and CH2 on GEN (×10 probes). The gain CH1/CH2 must be **1.86 to 2.07**
   (nominal 1.94). If you like, repeat at 20 Hz (1.82 to 2.02) and 20 kHz (1.86 to
   2.07).
9. **THD** *(optional)*: at 1 kHz and 1.38 Vpp at GEN, THD at TP22 should be 0.103 to
   0.193 %.
10. **Fault walk-through.** Move one shunt to F, wait 10 s (the worst simulated case is
    6.2 s), and check the rows marked **higher**/**lower** in that fault's table in
    `expected_readings.md` section 4. Return the shunt to H, wait 10 s, and check TP20,
    TP21 and TP23 are back inside the healthy windows. Repeat for all ten headers, then
    record the date and readings in the team log. The board is then accepted for the
    demo.

**Why a reading can be outside a window without a fault.**
* The windows are the 5–95 % band of the Monte Carlo draws widened by the meter
  tolerance, so about one reading in ten of a good board can fall just outside.
* The *nominal* column uses the model card's hFE of about 119, at the low end of the
  real 100–300 spread.

If one reading is outside its window:
1. Re-measure it.
2. Check VREG is 15.33 V at the post, the generator is connected at DC 0 V, and all
   shunts sit fully on H.
3. Then compare the whole pattern with the per-fault tables. A wrong-value part or a
   swapped pair of leads shows a pattern, not a single outlier.

## 7. Using the board with the demo

The engine treats the board as circuit `driver`. Its observables are:
* `dc:TP17`…`dc:TP23`: DMM, cost 1 each;
* `ac:TP17`…`ac:TP22`: 1 kHz gain from GEN, cost 3;
* `ac20:TP22` and `ac20k:TP22`: 20 Hz and 20 kHz gain, cost 3;
* `thd:TP22`, cost 3;
* `lift:<ref>`: out-of-circuit part check, cost 10.

Each reading ends up in the diagnosis session as `session.record(key, value)`, through
the instrument interface in `differential/instruments/`:

* **DMM over SCPI.** `ScpiInstrument(<VISA resource>, role="dmm")` sends `MEAS:VOLT:DC?`
  and returns volts. It refuses anything above 24 V (×1.1), because the hardware path
  serves only this low-voltage board. You place the probe on the requested test point;
  the software only triggers and reads.
* **Scope over SCPI.** `ScpiInstrument(<VISA resource>, role="scope")` reads VRMS on
  CH1 (probe on the test point) and CH2 (GEN), and returns CH1/CH2 as the gain. Its
  default commands are for the Rigol DS1000Z family and can be overridden.
* **Typed readings.** Use `ManualEntry` for THD, for lift-test verdicts, and whenever
  the SCPI path is not available. Type DC in volts (for example `9.30`), gains as a
  plain ratio (`1.94`, not dB and not volts), and THD in percent.

**Reading conventions.** The SCPI path returns raw values; apply these conventions
yourself:
* TP17 DC within ±10 mV, or TP22 DC within ±100 mV: enter **0**.
* A test point with no visible sine: enter a gain of **0**. Do not accept an automatic
  RMS ratio of noise.
* A gain below 0.1 at 0.20 Vpp: repeat at 1.38 Vpp before entering it.
* THD with no output: enter **100**.

`expected_readings.md` section 1 explains each convention and gives the simulation
evidence behind it. The on-stage script, including what to do when a reading disagrees
with the simulation, is `procedure.md`.

## 8. Regenerating the expected readings

```
source .venv/bin/activate
python hardware/fault_board/make_expected.py     # about 30 s on 4 cores
```

The script calls the project's own simulation code:
* `differential.sim.builder.fault_netlist`;
* `differential.sim.runner.simulate_draws`;
* `differential.sim.montecarlo.make_draw`.

Re-run it whenever any of these change: `circuits/driver/`, `circuits/lib/devices.lib`,
`differential/sim/`. It exits non-zero if any simulation fails. Provenance, including
netlist hashes and seeds, is at the end of `expected_readings.md`.
