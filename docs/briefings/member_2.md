# Briefing - MEMBER_2: circuits, simulation and data

You lead **Part 2** (today's practice and the data landscape) and own
`circuits/`, `differential/sim/`, `tools/hand_calcs.py` and the data sets.

## What you must be able to explain without notes

- The five blocks (supply with zener regulator and 250 V B+ chain, 12AX7 stage,
  passive Baxandall tone control, op-amp stage, two-transistor line driver) and
  the composite channel strip (59 parts, 250 catalog faults, 23 test points).
- How a simulated unit is made: datasheet tolerances drawn per part, one catalog
  fault applied with a random severity, ngspice run for DC, 1 kHz gain, 120 Hz
  hum, 20 Hz/20 kHz response and distortion; seeds recorded per draw.
- The numbers: 253,000 simulated units with 0 convergence failures; hand
  calculations agree with every simulated bias point and gain (22 of 22 checks,
  `docs/hand_calcs.md`).
- Why the hum model is quasi-static (rectifier B-source plus injected ripple,
  validated against a full transient within a few percent).
- Why 120 of 250 faults are "latent" and why the test set leaves them out
  (a unit with no symptom does not reach a bench).
- What a real unit needs: a netlist from its schematic, a map from test points
  to physical locations, and operating conditions; M2 times one transcription.
- The stress set: all tolerance spreads 1.5x wider, bit-identical to training at
  scale 1.0.

## The eight hardest questions you may get

1. "Your test data comes from the same simulator as the training data. What does
   93% accuracy prove?" (That the engine inverts its own physics under noise and
   tolerances; T6 widens the tolerances, T7 uses real hardware. Name the gap.)
2. "Are the tube and transistor models realistic?" (Koren 12AX7 equations and
   onsemi / Diodes Inc. device cards; the BD139 card was rejected because its
   Vbe was unphysical - ADR-019.)
3. "Why no power amplifier stage?" (Scope: preamp and line-level; power stages
   bring cascades and mains-side faults we exclude.)
4. "How do you know the fault severities are realistic?" (Ranges per mode are
   documented in `differential/sim/draws.py`; they are assumptions, not field
   data - say so.)
5. "What if the unit was modified?" (The unmodeled route; T13 tests it on
   modified and double-fault units.)
6. "Why original circuits instead of a real product?" (No copying of service
   documents; full ground truth; standard topologies. M2 transcribes one real
   product.)
7. "Did any simulation fail?" (0 failures after the retry ladder; failures are
   logged in `data/sim/failures__*.jsonl`.)
8. "Could meter loading change the readings?" (A 10 MOhm DMM barely loads our
   test points; high-impedance nodes are a known limitation for real gear.)
