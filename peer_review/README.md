# Peer review (M4)

1. Put each reviewed team's submission in `peer_review/inbox/<team_id>/`: the
   report PDF, and a `repo.txt` with the repository URL and tag if they shared one.
2. Run `python tools/peer_review.py <team_a> <team_b>`. Offline, each
   `peer_review/outbox/<team_id>/review.md` lists, per criterion of
   `rubric.yaml`, the passages found as evidence (page and verbatim quote) and the
   mechanical checks (length, figures, references, signed parts, unsourced
   percentages). With `DIFFERENTIAL_API_KEY` set, add `--live` to draft a score,
   strengths and prioritised recommendations per criterion; every quoted piece of
   evidence is checked against the cited page and dropped if it is not there.
3. Each member edits and confirms the criteria assigned to them, following
   `TEMPLATE.md`, then `python tools/peer_review.py --combine <team_a> <team_b>`
   writes one review signed per member, each member covering both teams.
4. Replace `rubric.yaml` with the course's shared rubric when it is published.
5. Record feedback we receive in `feedback/FEEDBACK_LOG.md` (triage decision,
   change, commit).

`dry_run_self.md` is the pipeline run on this project's own M3; it validates the
tooling and is not for submission.
