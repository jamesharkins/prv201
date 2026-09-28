# Briefing - MEMBER_4: agent, language and vision, safety and security, demo

You lead **Part 4** (AI approach, risks and ethics) and own
`differential/agent/`, `differential/nlp/`, `differential/vision/`,
`differential/safety/` and the demo app.

## What you must be able to explain without notes

- The division of labour: simulation for physics, Bayesian inference for belief
  and measurement choice, the LLM only for reading complaints and photos and for
  explanations. The LLM never produces a reading; the grounding check rejects any
  number that does not trace to a tool result or the technician.
- The safety layer, in code: request screening, the fault-conditioned
  high-voltage map, hands-off and discharge instructions, the unsoldering lock
  (filter capacitor below 2 V), output checks, retrieved text wrapped as data.
- Autonomy levels L0-L4; Differential is L2 (recommends, human measures and
  decides); the SCPI path reaches L3 only on the 24 V fault board.
- Modes: live (Claude), offline (rules and templates), replay (cached responses).
- The red-team situation: the adversarial suite (T16) must be written by the
  team; the build ships the harness, rubric and the exhaustive sweep (T15).

## The eight hardest questions you may get

1. "What if the model ignores your safety prompt?" (Code is the authority; the
   prompt cannot override the output checks or the lock.)
2. "Your offline agent meets the grounding target by construction." (Yes - its
   text is built from tool results; the live pre-check rate shows how often the
   model tried to state an untraceable number.)
3. "How do you stop prompt injection through a service note?" (Wrapped as
   untrusted data, tools are read-only, the model controls no instrument; the
   shipped poisoned note is flagged and its request refused.)
4. "Why read meter photos at all?" (Hands-free logging and an evidence trail; the
   technician confirms every reading; unit and mode must match exactly - T19.)
5. "What leaves the bench in live mode?" (Complaint text and photos to the model
   provider, after removing names and serial numbers; nothing in offline mode.)
6. "Could a technician over-trust it?" (Runner-ups and reasons are always shown;
   tickets need sign-off; a technician study is planned but not a locked target.)
7. "Why not let the LLM do everything with a simulator tool?" (That is one of our
   baselines; it lacks a tolerance model and a measurement plan.)
8. "Zero unsafe outputs in 40 prompts proves little." (Agreed; T15 is exhaustive
   over every possible recommendation, and T16's bound is stated.)
