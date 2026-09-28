# Briefing - MEMBER_3: diagnosis engine and evaluation

You lead **Part 3** (objectives and success criteria) and own
`differential/engine/`, `eval/` and `results/`.

## What you must be able to explain without notes

- The engine: a probability for every fault hypothesis plus an explicit
  "unmodeled" hypothesis; Gaussian-mixture likelihoods (1-3 components per fault,
  measurement noise added analytically) or a masked, calibrated boosted-tree
  classifier; ambiguity groups from validation confusion.
- Measurement choice: expected information gain over ambiguity groups divided by
  effort cost; stop at 90% on one group or when the budget runs out.
- The targets (T1-T21), which are primary, and which are pending (API key, team
  red-team suite, hardware). The pass rule: point estimate meets the bar, with a
  bootstrap 95% CI reported.
- The pilots: first on held-out training draws, second on symptomatic validation
  units; neither touched the test set. The second one found an engine bug (the
  "no single fault fits" hypothesis was left out of the information-gain
  calculation, so some sessions stopped early) and a calibration flaw (one
  threshold for sessions with and without a complaint). Both were fixed before
  the bars were set (ADR-029).
- How the bars were set: every bar the pilot can estimate is the pilot estimate
  moved 1.5 standard errors against the system, rounded (`eval/set_bars.py`);
  `results/targets.json` keeps each drafted value and a one-line derivation.
- The main trade-off: almost every pilot miss of the full system was a false
  "no single fault fits". The 5% false-alarm budget costs up to 5 points of
  top-1 accuracy and buys detection of double faults and modified units.
- The baselines: random, fixed-order chart, half-split tracing, LLM alone, LLM
  with simulator access - and what each one is allowed to see.

## The nine hardest questions you may get

1. "Your effort units are made up." (They are estimates, not timings; results are
   repeated with the scope and lift weights halved and doubled; M2 times them.)
2. "The fixed-order chart is a straw man." (Hence the half-split baseline, T9.)
3. "Why group-aware accuracy - isn't that grading on a curve?" (Some faults give
   identical readings at every test point; naming the group is the honest answer
   and a lift test separates it. We report the mean group size.)
4. "Is 93% top-1 meaningful when the test comes from your own simulator?" (See
   T6/T7; the claim is scoped to simulation.)
5. "Why is T5 only +10 points when you first proposed +30?" (Frontier models now
   score 95.5% on textbook analog questions; we set the bar conservatively before
   seeing any LLM result. ADR-024.)
6. "How do you know the probabilities are calibrated?" (T12: calibration error
   after every step, not just at the stop.)
7. "What stops you from tuning on the test set?" (Targets locked by git tag
   before any test run; test seeds disjoint; the pilot uses validation units;
   bars follow a fixed rule. One disclosure: a CI smoke check may have run 8 test
   units per circuit once before the lock; nobody read it and it now uses pilot
   units - ADR-029.)
8. "What happens with two faults at once?" (The unmodeled hypothesis; T13 gives
   AUROC, the share flagged at a 5% false-alarm rate, and the share of
   misleading outcomes - pointing only at healthy parts. Most double faults look
   like one of their two faults, so naming one of the bad parts is also useful.)
9. "Why did the first pilot say 99% and the second 95%?" (The first ran with the
   "no single fault fits" threshold uncalibrated at zero, so it never fired; with
   the threshold set to flag at most 5% of genuine single faults, those false
   flags are nearly all of the misses.)
