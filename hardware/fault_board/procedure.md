# On-stage demo: diagnosing one hidden fault

A second person hides one fault on the fault board. The presenter then follows the
agent's recommended measurements until the agent names the fault. The whole run is
low voltage: the bench supply is 15.33 V with a 50 mA current limit, and there is no
mains wiring on the board. The numbers below come from `expected_readings.md`, which
is generated from the project's simulation code.

## Roles

| Role | Who | Does |
|---|---|---|
| **Fault setter** | Second team member, off to the side | Sets and hides the fault, answers lift tests, keeps the log |
| **Presenter** | On stage with the board | Places the probes, reads the instruments aloud, narrates |
| **Operator** | At the laptop (may be the presenter) | Runs the demo software, enters or confirms each reading |

## 1. The day before: board acceptance

Complete the healthy check and the fault walk-through in `README.md` section 6. All
ten faults must match their tables in `expected_readings.md` section 4. Record the date
and readings in the team log. A board that has not passed this does not go on stage.

## 2. Pre-flight checklist (30 minutes before)

**Hardware**

- [ ] All ten shunts present and on **H**. Two spare shunts on the bench. The cover
      fits over the header row.
- [ ] Bench supply connected to VREG and GND, current limit **50 mA**. The DMM at the
      VREG post reads **15.33 V**; adjust the supply until it does.
- [ ] Supply current about **9.99 mA** (healthy 5–95 %: 9.94 to 10.14 mA).
- [ ] Generator connected at GEN, ground on a GND post, output **on**. Presets ready,
      with each amplitude checked on the scope **at GEN**:
  - DC 0 V, for DC readings;
  - 1 kHz sine at 0.20 Vpp, for gains;
  - 20 Hz and 20 kHz sines at 0.20 Vpp;
  - 1 kHz sine at 1.38 Vpp, for THD.
- [ ] Scope: CH1 ×10 probe (moves to the test point), CH2 ×10 probe fixed on GEN.
      Both ground clips on GND posts. Both channels measuring Vrms, or both Vpp.
- [ ] DMM on DC volts, autorange. If it is on SCPI, `*IDN?` answers and a test read
      at TP23 gives 14.86 V (accept 14.76 to 14.96 V).
- [ ] **Healthy check** after the generator has been at DC 0 V for 10 s:

  | Reading | Accept window |
  |---|---|
  | TP18 | 3.581 to 3.694 V |
  | TP19 | 2.960 to 3.065 V |
  | TP20 | 9.14 to 9.54 V |
  | TP21 | 8.44 to 8.82 V |
  | TP23 | 14.76 to 14.96 V |
  | Gain at TP22, 1 kHz, 0.20 Vpp | 1.86 to 2.07 |

- [ ] **Rehearsal fault.** Set JF3 to F and wait 10 s. TP18 must read 4.017 to
      4.125 V. Return JF3 to H, wait 10 s, and check TP18 is back inside 3.581 to
      3.694 V.

**Software**

- [ ] Demo app running with circuit `driver` and its fitted engine bundle loaded.
      Budget 40 units, stop threshold 0.90 (ADR-010, ADR-016).
- [ ] Instrument interface chosen:
  - SCPI DMM (`ScpiInstrument(..., role="dmm")`);
  - SCPI scope (`role="scope"`: CH1 = test point, CH2 = GEN);
  - otherwise `ManualEntry`. THD and lift verdicts are always typed.
- [ ] Reading-conventions card (section 5) printed next to the laptop.
- [ ] Fallback ready: if the hardware fails on stage, the same hidden fault can be run on
      the simulated bench with `SimulatedBench.simulate("driver", "<catalog id>")`.

## 3. Choosing the hidden fault

The fault setter picks one row. For a first demo, prefer the crisp ones.

| Type | Shunt → catalog id | What the audience will see |
|---|---|---|
| Crisp DC signature | JF2 → `Q501:be_open` | TP19 at 0 V while TP18 is normal |
| | JF3 → `Q501:cb_leak` | Base up to 4.048 V, collector down to 8.43 V |
| | JF6 → `R505:open` | Whole first stage collapses, TP20 0.665 V, heavy distortion |
| | JF7 → `Q502:be_open` | TP21 at 0 V while TP20 is up |
| | JF8 → `Q502:ce_short` | TP21 up at 14.28 V, output dead |
| | JF10 → `R509:drift_x10` | Supply node down to 11.64 V, everything scaled down |
| Needs the scope | JF1 → `C501:open` | All DC normal, signal stops after C501 |
| Ambiguity group | JF4 → `R503:drift_x2` | Group with `R505:drift_x0.5`, or a lift test |
| | JF9 → `C503:open` | Group with `R507:open`, or a lift test |
| Hard | JF5 → `C502:cap_loss_90` | Only the 20 Hz gain drops; several look-alikes |

**Rules for the fault setter**

1. **Exactly one shunt on F.** Never JF6 and JF8 together: that pair reverse-biases
   Q502's base-emitter junction at 13.7 V against its 6.0 V rating.
2. **Never remove a shunt without placing it.** A missing shunt on JF4, JF5 or JF10 is a
   different fault.
3. **Write the catalog id on a card** before the demo starts, and keep it face down.

## 4. The demo, step by step

1. **Introduce.** "This is the line-driver block the engine was trained on: same parts,
   same values, same 15.33 V supply. One of ten fault jumpers has been moved; nobody on
   stage knows which."
2. **Set the fault.** The presenter turns away. The fault setter lifts the cover, moves
   one shunt from H to F, writes the id on the card and replaces the cover. The fault
   setter says "set" and starts a 10 s count. Moving a shunt can swing TP22 by up to
   13.68 V, and the worst simulated settling time is 6.2 s.
3. **Complaint** *(optional)*. The presenter puts CH1 on TP22 with the 1 kHz tone on and
   describes what a customer would report ("no output", "output low", "distorted"). If
   the demo app takes a complaint, the operator enters it.
4. **Measure–update loop.** Repeat until the agent stops:
   1. The agent shows the next measurement as an observable key, for example `dc:TP21`
      (DMM at TP21), `ac:TP18` (1 kHz gain at TP18), `ac20:TP22`, `thd:TP22` or
      `lift:R503`, with its reason.
   2. The presenter sets the generator for that kind of reading (section 5), places the
      probe, and reads the value aloud.
   3. The operator enters or confirms the value, applying the conventions in section 5.
   4. The presenter reads out the agent's new top hypothesis and its probability.
5. **Stop.** The agent stops when one ambiguity group holds at least 0.90 of the
   posterior, when the 40-unit budget cannot pay for another measurement, or when no
   measurement is informative (ADR-010). Costs: DC reading 1, scope reading 3, lift
   test 10.
6. **Lift tests.** On this board each fault is realised outside the named part, so the
   part itself would test good out of circuit. When the agent asks for `lift:<ref>`, the
   fault setter answers as a real lift test of a genuinely faulty part would: **1 (out
   of tolerance)** if `<ref>` is the part in the hidden catalog id, otherwise **0**.
   Say on stage that this stands in for desoldering.
7. **Reveal.** The fault setter turns the card over. Compare it with the agent's answer.
   If the answer is a group, check that the hidden fault is in it; the expected groups
   are in section 3 and in `faults.md` section 5.
8. **Restore.** Shunt back to H, cover on, wait 10 s. Check TP21 is 8.44 to 8.82 V and
   TP23 is 14.76 to 14.96 V. The board is ready for the next round.

## 5. Reading conventions (print this card)

| Reading | Instrument and setting | Enter |
|---|---|---|
| `dc:TPxx` | DMM, DC volts. Generator connected, output on, at **DC 0 V**. | Volts, as displayed (e.g. `9.30`) |
| `dc:TP17` | As above | **0** if within ±10 mV (generator offset is not in the model) |
| `dc:TP22` | As above | **0** if within ±100 mV (capacitor leakage is not in the model; 100 mV is the project's output-DC threshold, ADR-012) |
| `ac:TPxx` | 1 kHz sine, **0.20 Vpp at GEN**. CH1 on TPxx, CH2 on GEN, same measurement on both. | Ratio CH1/CH2 (e.g. `1.94`); not dB, not volts |
| `ac20:TP22`, `ac20k:TP22` | As `ac`, at 20 Hz or 20 kHz, 0.20 Vpp | Ratio CH1/CH2 |
| No visible sine at the test point | Flat trace, noise only | **0**. The model floors gains at 0.001; do not accept an automatic RMS ratio of noise. |
| Gain below 0.1 at 0.20 Vpp | Repeat at 1.38 Vpp. The small outputs on this board are linear at that level (`expected_readings.md` section 8). | Ratio at 1.38 Vpp; 0 only if still no sine |
| `thd:TP22` | 1 kHz sine, **1.38 Vpp at GEN**. Distortion analyser, or scope FFT with at least 60 dB of range. | Percent. **100** if the output has no fundamental above 10 mV peak. |
| `lift:<ref>` | Fault setter (section 4, step 6) | 1 or 0 |

**Why 0.20 Vpp for gains.** The engine's gains are small-signal. At 0.20 Vpp every
board state reads within 1.3 % of the small-signal gain. At 1.38 Vpp the R505-open
state would read 25.2 % low (`expected_readings.md` section 8).

**Settling.** Wait 10 s after power-up and after any shunt move before reading.

## 6. When a reading disagrees with the simulation

"Disagrees" means the reading is outside the accept window of the hidden fault's table
in `expected_readings.md` section 4. Only the fault setter can check this during the
demo; the presenter does not know the fault.

1. **Re-measure before entering.** Check:
   * the probe is on the right post;
   * the ground clip is on GND;
   * the DMM is on DC volts;
   * the scope probe is set ×10 on both channels, and CH2 is on GEN.
2. **Check the conditions.**
   * VREG reads 15.33 V at the post. A supply error moves TP23 by 0.097 V per 0.1 V,
     and every other DC point too (`expected_readings.md` section 9).
   * The generator is connected, on, and at the right setting for this kind of
     reading.
   * At least 10 s have passed since the last shunt move.
   * Nothing but the probe is connected to TP22.
3. **Apply the conventions** in section 5: the zero rules at TP17 and TP22, "no sine
   means 0", and the 1.38 Vpp repeat for small gains. These are declared model
   limitations. **They are the only transformations allowed.**
4. **The fault setter checks the board discreetly**:
   * the shunt is fully seated on the correct pins;
   * no other shunt is on F or missing;
   * the fault part is present (RF3, RF4, RF8, RF10, CF5).

   If a fix is quick, make it, wait 10 s and measure again.
5. **Otherwise, enter the true reading.** Never adjust a reading to help the engine.
   The engine carries an explicit "unmodeled" hypothesis. A reading that no single-fault
   model explains should raise it, and the agent should say so rather than force the
   nearest fault. On stage this is a result, not a failure: explain that the tool
   noticed the hardware no longer matches any model it knows.
6. **If the agent names the wrong fault,** check first whether its answer is a
   documented look-alike of the hidden fault (`faults.md` section 5). For example,
   JF4 is expected to group with `R505:drift_x0.5`. If so, the agent is right about
   the ambiguity, and a lift test splits the group.
7. **After the demo, log it.** Record the hidden fault, the key, the reading, the
   expected window, the instrument and the conditions. These entries are the
   sim-to-real evidence the project reports. A repeated disagreement at the same test
   point points to a board problem or a model gap; repeat the walk-through in
   `README.md` section 6 before the next show.

## 7. Optional: showing the "unmodeled" hypothesis

After a successful single-fault round, the fault setter can deliberately put two
shunts on F, for example JF3 + JF10. **Never JF6 + JF8.** All other pairs were simulated
and stay within ratings: highest supply current 15.83 mA, highest R506 dissipation
205 mW (`expected_readings.md` section 7). A double fault is outside the single-fault
catalog, so the engine's "unmodeled" probability should rise instead of the agent
confidently naming one part. There are no expected-reading tables for pairs. Treat the
outcome as a demonstration of the stopping rule and the U hypothesis, not as a scored
diagnosis.

## 8. Shutdown

1. All shunts on H, cover off.
2. Generator output off, then supply output off.
3. Disconnect the leads.
4. Count the shunts, ten on the board and two spare, and store the board.
