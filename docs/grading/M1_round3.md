# M1 grading round 3 (submission rendered 2026-09-28, commit b7ed8b5)

Same kit as round 2 (`tools/review_kit.py`): anonymised text, page images,
milestone description, derived rubric, syllabus notes. Fresh reviewers; judge
personas as in the brief. A claim-to-source audit and a signed-part audit ran
alongside.

P = Problem definition (5), S = Stakeholders (3), A = AI/ML approach (5),
O = Scope/objectives/criteria (5), E = Ethics/risk/regulation (4), C = Clarity/references (3).

| Reviewer | P | S | A | O | E | C | Total /25 |
|---|---|---|---|---|---|---|---|
| Grader A (preliminary reader) | 4 | 2.5 | 4 | 4 | 3.5 | 2 | 20.0 |
| Grader B (strict instructor) | 3.5 | 2 | 4 | 3.5 | 3 | 2 | 18.0 |
| Grader C (calibrated TA) | 4 | 2.5 | 4.5 | 4.5 | 3.5 | 2.5 | 21.5 |
| Judge: course professor | 3.5 | 2 | 4 | 4 | 3 | 2 | 18.5 |
| Judge: audio-electronics engineer | 3.5 | 2 | 4 | 3.5 | 3 | 2.5 | 18.5 |
| Judge: ML PhD student | 4 | 2.5 | 4 | 3.5 | 3.5 | 2.5 | 20.0 |
| Judge: ethics and policy scholar | 3.5 | 2.5 | 4.5 | 4 | 3 | 2.5 | 20.0 |

**Minimum per line across the three graders: 3.5 + 2 + 4 + 3.5 + 3 + 2 = 18.0 / 25**
(round 2: 18.0). Signed-part audit: all four parts Full (Parts 1 and 2 about 60%
of the length of Parts 3 and 4). Nothing addressed to graders or models.
Source audit: 49 cited statements, 42 supported, 6 partly, 1 overstated, 0
unsupported (round 2: 35/5/3/0 of 43).

The scores did not move because the round-2 fixes removed old findings while
the reviewers, reading a tighter document, went deeper. Every reviewer
converged on the same five themes.

## Themes (reviewers in brackets)

1. **The success criteria test the simulator, not the bench** [all seven].
   Bars sit 1.5 pilot standard errors below the pilot and count as met on the
   point estimate, so an in-simulation primary is close to certain to pass
   (ML PhD: about 0.99 for T2 and T4). The only hardware target (T7) is
   secondary, top-3, one transistor board, at least 20 faults (16/20 has an exact
   interval of about 56-94%). No technician study is locked. The test mix gives
   every catalogued fault equal weight, but the text claimed it matched how often
   faults reach a bench.
2. **Comparisons tilted** [prof, ML PhD, engineer, all graders]. T4 left out
   half-split tracing (the strongest scripted baseline) and compared a system
   that reads the complaint with scripts that do not; the baselines' naming and
   stopping rules were not stated; the LLM-alone baseline did not get the netlist.
3. **Numbers that do not reconcile** [all]. 55% vs 53% flagged; T1 pilot 94.8%
   vs 27 misses in 500 (reweighting to the test mix unstated); T8-T10 ratios not
   reproducible from the channel-strip effort means (unit set unstated); T3's bar
   with a 100% pilot; the "85.3%" wider-tolerance pilot size; 250 faults vs 251
   hypotheses; "51 dimensions"; "rule out the most suspects" vs "expected
   information gain".
4. **Evidence of significance and stakeholder needs is thin** [all]. The premise
   that diagnosis dominates bench time is uncited; the in-scope share of real
   jobs and the cost of building a circuit model are not estimated; the workforce
   "trend" is one snapshot of a broader, growing occupation plus a blog and a
   column; there is no primary evidence from technicians.
5. **Ethics misses the nearest harms** [prof, ethics, engineer, graders B, C].
   No row for damage to the customer's unit; the planned study deceives
   participants without consent, debriefing or IRB review; "shops only" has no
   mechanism; the discharge "lock" trusts one typed voltage at one capacitor; the
   word "guarantees"; "live-chassis" misuses a vintage-repair term; NIST
   functions used as row labels; the driving-automation scale misapplied (six
   SAE levels, not five); U.S. liability gets one clause; the register has no
   owner, residual rating or monitoring after deployment.

## Findings that change the system before the lock

The targets are not yet locked (no `targets-locked` tag), so these go into the
system and the target design now, not into a separately labelled addendum:

1. **Decision rule.** A target is met only when its one-sided 95% confidence
   bound clears the bar; bars keep the 1.5-SE pilot rule, so none is lowered,
   and the M1 states each primary's probability of being met if the test
   behaves like the pilot [ML PhD, prof, engineer].
2. **Meter loading.** DC readings are simulated with the meter's 10 MΩ input
   resistance across the measured node, one operating point per reading; the
   hazard audit and hand checks stay on the unloaded circuit [engineer, ML PhD].
3. **Mains variation and ageing.** Every simulated unit gets a mains level; a
   directional aged-unit set (electrolytics lose capacitance and gain ESR,
   resistors drift up, tubes lose emission) replaces the symmetric
   wider-tolerance stress target, and a 1x-3x tolerance curve is reported
   [engineer, ML PhD].
4. **Fair comparisons.** T4 runs the engine alone (the same inputs as the
   scripts) against the chart, random probing and half-split tracing; a
   comparator table states each baseline's policy, naming and stopping rule; the
   LLM baselines get the netlist [prof, ML PhD, graders].
5. **Hardware primary.** T7 becomes primary: at least 60 faults inserted blind
   into three driver boards, every test point recorded once per fault, all
   methods replayed on the same readings, top-1 with an exact interval [all].
6. **Out-of-model units.** The set grows to 500 units with a stated mix; the
   misleading rate becomes primary; coverage and accuracy-when-committing are
   reported separately [ML PhD].
7. **Calibration.** T12 moves to the probabilities shown for the top three
   groups at the stopping step (equal-mass bins), with Brier score and log loss
   reported [ML PhD, prof].
8. **Fault mix.** Results are also reported under a capacitor- and tube-heavy
   mix; T14 tests a wrong prior in both directions [all].
9. **Complaints.** Test complaints carry stated rates of missing and spurious
   symptoms, from templates never used in rule development [ML PhD].
10. **Safety as release gates.** T15-T17 are checks against our own
    specification, so they become release gates with independent checks: a
    red-team suite of at least 300 prompts crossing team-written unsafe intents
    with outside attack styles, and an independent grounding checker [ML PhD,
    ethics, prof].
11. **Safety controls.** Discharge readings at every node that can hold high
    voltage, re-entered after any power cycle and logged as an attestation;
    "high voltage inside chassis" notice; an unvalidated circuit model makes
    every point in a high-voltage chassis hands-off; a trainee mode (own
    hypothesis first, supervisor named before high-voltage steps); owner consent
    before a part is removed [engineer, ethics, prof].

## Text issues (grouped)

- Executive summary: plain-language rewrite; say every number so far comes from
  simulation; scope each target (channel strip, subset) [prof, graders].
- Part 1: cite or hedge the premise; state the broad occupation's median age and
  projection honestly; drop "near retirement" and the two-year-college claim or
  attribute them; say what each AI product draws on; setup cost and where it
  pays (consoles with many identical strips) [all].
- Part 2: cite practice where possible; correct the repair-law sentence (laws
  cover products first sold after 2015 or 2021; some only digital); substitute
  a known-good part is the usual last step, not only unsoldering; add tube
  testers, ESR meters, service bulletins [engineer, graders, sources].
- Part 3: define terms on first use; reconcile every number; state pilot n and
  the test-mix weighting; comparator table; bench meaning of each primary.
- Part 4: one selection criterion (expected information gain per unit of
  effort); autonomy in plain words (no driving scale); "checks", not
  "guarantees"; U.S. liability paragraph; human-subjects plan; equipment damage,
  worker monitoring, blame shifting and project risks in the register, with
  owners and residual ratings; NIST used as lifecycle functions; OSHA condition;
  PLD covers damage to a consumer's own unit; AI-literacy duty; Annex III
  education point [all].
- Layout: nothing but references after page 5 (industry watch and coverage map
  move to a separate supplement); no sentence split by a table; shorter
  captions.
- References: authors for [18]; one version of [9] with its figures; OJ dates for
  [39] and [42]; IEEE article number for [26]; access dates everywhere; weaker
  sources replaced where a recorded primary source exists [sources, graders].

## Not adopted, with reasons

- **Technician interviews, a ticket survey, timing at a partner shop, a
  technician study, outside red-team prompts, IRB determination.** Only people
  can supply these; they are listed with protocols in `SUBMISSION_GUIDE.md` and
  the M1 states them as planned, with the analyses fixed in advance. Nothing is
  fabricated.
- **Paired healthy-channel readings** [engineer]. A strong idea that needs a
  two-channel simulation; recorded for the design milestone.
- **A low-voltage tube board for hardware validation** [engineer]. Recorded for
  the design milestone as a secondary hardware target; the primary hardware
  target stays on the driver block the team can build first.
- **Legal citations the team could not open** (case law on software as a product,
  the sophisticated-user doctrine, NFPA 70E, IEC 62368-1, Illinois HB 3773). The
  network here reaches none of them and the search budget is spent; the U.S.
  paragraph uses the recorded sources (OSHA, the AI LEAD and RISE bills) and
  flags the open question without citing cases we have not read.
