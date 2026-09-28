# Milestone descriptions

The milestone descriptions the team works to, as given in the project brief (a stand-in until the official assignment sheets are added to `course/`).

Due dates follow the syllabus: work listed in a week is due by the start of the following class. Each milestone gets a folder `submissions/M#/` containing:
- the rendered PDF, built via Typst or pandoc from version-controlled source;
- the source;
- `SUBMIT.md`, listing exactly what to upload and who signs which part.

Where feedback exists in `feedback/M#/` from an earlier milestone, the next milestone includes a "Response to feedback" table: item, change made, and where it now appears.

**Part titles and cross-references.** Label each part with a descriptive title (e.g., "Part 1 — Problem, stakeholders and industry context"). Cross-reference parts by that title, never by member.

### M1 — Problem statement (25 pts)

**Length.** At most 5 pages plus references.

**Contents.** An executive summary paragraph and one concept figure, then four parts:
1. **Problem, stakeholders and industry context.** Who repairs this gear, what diagnosis costs, and the workforce trend. Also the current AI-for-maintenance landscape and relevant 2025–2026 developments, researched and cited.
2. **How diagnosis is done today, and the data landscape.** Troubleshooting practice, available information (service manuals, schematics), why real labeled fault data is scarce, and why simulation fills the gap.
3. **Objectives and measurable success criteria.** The locked targets (§2.10), scope and non-goals, and how success will be measured.
4. **Preliminary AI approach, risks and ethics.** Why a hybrid system and not an LLM alone, candidate AI families, an initial risk register, and a first pass on safety, bias, accountability and regulation.

### M2 — Design / approach (45 pts)

**Length.** At most 10 pages plus appendix.

**Contents:**
1. **Requirements and architecture.** Requirements traceability matrix; architecture and data-flow diagrams; project plan and risk register; industry and regulatory constraints on the design.
2. **Circuits, simulation and data design.** Circuit library, fault catalog, Monte Carlo design, observables, measurement model, data splits, and a data-quality plan.
3. **Diagnosis engine and evaluation plan.** Likelihood models and alternatives considered; active selection; calibration; metrics, baselines, ablations and statistics, all tied back to the M1 criteria.
4. **Agent, safety, security and UX design.** Tools, grounding checks, the safety layer, the prompt-injection defense, human-in-the-loop design, UI wireframes, and ethics-by-design decisions.

Every major choice gets an alternatives-and-trade-offs table.

### M3 — Prototype / draft (64 pts)

**Length.** At most 12 pages plus appendix. Also deliver the repo link (with a tag) and a zip for Canvas.

**Contents.** Four parts following standing ownership:
1. System overview and results against targets. This part holds the ethics audit and model/system-card summaries.
2. Simulation and data, including hand-calc validation.
3. Engine results, ablations and failure analysis. Explain observed behavior in terms of mechanisms: why the LLM-only baseline fails, and where ambiguity groups arise.
4. Agent, safety and red-team results; meter-photo results; UI screenshots.

Also required: a README demo GIF and a 90-second demo capture.

### M4 — Peer review (22 pts)

**Build now:**
- `peer_review/TEMPLATE.md`.
- A pipeline that runs when another team's submission is placed in `peer_review/inbox/<team_id>/`.

**What the pipeline produces.** It applies every criterion of the shared rubric to each reviewed team, with the criteria split into as many subsets as the team has members. Each member's subset covers both reviewed teams, and that member signs it. For each criterion, the review gives:
- a calibrated score;
- evidence with exact locations (page/section, or file:line);
- strengths;
- prioritized, actionable recommendations.

The tone is specific, professional and constructive.

**Dry run now.** Run the pipeline on this project's own M3 and store the result as `peer_review/dry_run_self.md`. It is not for submission; it validates the tooling.

**Feedback log.** Set up `feedback/FEEDBACK_LOG.md` to record feedback received, triage decisions, changes made and commit hashes. This is the evidence for "incorporates feedback".

### M5 — Demo Day / capstone (84 pts)

**Deliverables:**
- **Final report:** at most 15 pages plus appendices.
- **Slide deck:** `.pptx`, 12–16 slides with speaker notes, built with python-pptx.
  - Custom, clean design with charts drawn from `results/`.
  - Render every slide to an image and inspect it for overflow and legibility.
- **Talk:** a 5–10 minute talk; target 8–9 minutes at about 140 words per minute. Four slices, one per member, each about 2 minutes:
  1. Member 1: problem, impact, industry and ethics.
  2. Member 2: how it works, simulation and data.
  3. Member 3: results and evidence.
  4. Member 4: live demo and safety.
- **Demo runbook:**
  - Live mode, with Replay mode as a fallback on one keystroke.
  - Fault-board instructions, if the team builds it.
  - A pre-flight checklist.
- **Recorded-presentation package**, for teams outside the top 20:
  - a per-slice script and shot list;
  - a silent Playwright screen capture of the demo, for voice-over.
- **Q&A bank:** at least 30 likely judge questions with answers, each tagged with the member who answers it.
- **One-page project profile** for portfolios.
