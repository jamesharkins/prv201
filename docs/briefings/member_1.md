# Briefing - MEMBER_1: problem, stakeholders, industry, regulation, ethics

You lead **Part 1** of every milestone (problem, stakeholders, industry context)
and the regulation and ethics material wherever it appears. Your numbers come
from `docs/research/sources_*.yaml` (every claim there has its quote and how it
was verified). Know which sources were only seen as search snippets
(`results/citation_check_M1.json`, field `snippet_only`) and re-check them on the
live pages before submitting.

## What you must be able to explain without notes

- Why diagnosis is the target: bench fees of $125-$150 at the three shops we
  sampled (single-shop examples, not averages), a one-hour minimum even when no
  fault is found, queues of months as specialists retire.
- The workforce numbers and their limits: 24,720 audiovisual equipment
  installers and repairers (May 2023); the broader 117,700 group is mostly
  industrial, avionics and vehicle work, so it is the adjacent market, not ours.
- Why the primary user is a qualified technician: OSHA's de-energise rule has an
  exception for testing that can only be done energised, and only qualified
  persons may work on parts that are not de-energised (1910.333(a)(1) Note 2,
  1910.333(c)(2), 1910.334(c)(1)). OSHA is our benchmark, not a claim that OSHA
  governs every repair shop.
- The worst-case high-voltage audit: 6 of the channel strip's 23 test points can
  exceed 50 V, 2 of them only under a fault (TP8 with R204 open, TP10 with C203
  shorted).
- EU AI Act: high-risk only as a safety component of an Annex I product or in an
  Annex III area; diagnostics is neither, but Annex III covers evaluating workers,
  so our intended use excludes grading technicians. Transparency duty since
  2 August 2026. Revised PLD: software is a product only for products placed on
  the market after 9 December 2026; professional-use property damage excluded.

## The eight hardest questions you may get

1. "Most repairs are expensive because of parts and labour, not diagnosis. What
   share of the bill is diagnosis?" (We don't know; it isn't published. We plan
   technician interviews. Show the bench-fee evidence only for "separately
   billed".)
2. "Frontier models score 95.5% on analog textbook questions. Why do you need
   simulation?" (Textbook questions have exact values and no measurement cost or
   tolerance; a bench unit has tolerances, look-alike faults, effort and lethal
   voltages. T5 tests the claim head-on.)
3. "Who pays for this?" (The shop owner; value is technician time and fewer good
   parts replaced. We have no price data yet; say so.)
4. "Isn't live testing above 50 V against OSHA rules?" (No: the energised-testing
   exception plus qualified persons; we support safe practice with hands-off
   measurement and the discharge lock.)
5. "Could a hobbyist use it anyway?" (The tool assumes qualification; it refuses
   mains work and gates unsoldering behind a discharge reading; it cannot verify
   who is typing. That residual risk is in the register.)
6. "Why is the EU AI Act relevant for a U.S. project?" (It is the most developed
   framework and sets the transparency duty; U.S. liability analysis is in M2.)
7. "Why cite Headphonesty and Stereophile?" (They are trade reporting for facts
   no official source counts: queues, retirement, training gaps. They are flagged
   as snippet-verified.)
8. "How does this help the workforce rather than replace it?" (It targets
   trainees and newly qualified technicians - the novice gains in the Brynjolfsson
   study - and keeps the technician deciding; deskilling risk is in the register.)
