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
  units; neither touched the test set.
- The baselines: random, fixed-order chart, half-split tracing, LLM alone, LLM
  with simulator access - and what each one is allowed to see.

## The eight hardest questions you may get

1. "Your effort units are made up." (They are estimates, not timings; results are
   repeated with the scope and lift weights halved and doubled; M2 times them.)
2. "The fixed-order chart is a straw man." (Hence the half-split baseline, T9.)
3. "Why group-aware accuracy - isn't that grading on a curve?" (Some faults give
   identical readings at every test point; naming the group is the honest answer
   and a lift test separates it. We report the mean group size.)
4. "Is 95% top-1 meaningful when the test comes from your own simulator?" (See
   T6/T7; the claim is scoped to simulation.)
5. "Why is T5 only +10 points when you first proposed +30?" (Frontier models now
   score 95.5% on textbook analog questions; we set the bar conservatively before
   seeing any LLM result. ADR-024.)
6. "How do you know the probabilities are calibrated?" (T12: calibration error
   after every step, not just at the stop.)
7. "What stops you from tuning on the test set?" (Targets locked by git tag
   before any test run; test seeds disjoint; the pilot uses validation units.)
8. "What happens with two faults at once?" (The unmodeled hypothesis; T13 gives
   AUROC and the share flagged at a fixed false-alarm rate.)
