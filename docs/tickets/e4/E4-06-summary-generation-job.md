# E4-06 — The summary generation job

**ID:** E4-06
**Branch:** `e4/summary-generation-job`
**Depends on:** E4-02, E4-05
**Lane:** heavy — `backend/app/jobs/` is under `backend/app/` and matches no
row; fail-closed.
**Security-relevant:** a worker that reads every comment in the system and
writes instructor-visible text. Log discipline and write-path grants are the
review surface.

## Context

The Monday job: for every section with a course week whose window closed and
no stored summary for it, call E4-05's task per stream and store the row.
Generation is once-and-done (breakdown decision 2): no regeneration on
reclassification or release, because under-threshold comments already fed
the summary at generation time and a summary that changes under its reader
is worse than one that is a week honest.

E3-06 is the pattern to copy deliberately: an idempotent sweep, per-section
transactions so one failure does not poison the walk, a beat entry as the
ordinary trigger rather than the definition of the work, and a re-run that
converges (missing rows filled, existing rows untouched).

If E4-04's ADR rules that the release batches are cut by this job (its
recommendation), that half lands here too, on E4-04's logic — this job then
does two writes per walk: summaries, then any due release batch.

Read first: SPEC §5.1, §3.1; breakdown decisions 2 and 6;
`backend/app/jobs/tasks.py` and `celery_app.py` (the `publish_once` shape
and the beat inventory test it will trip); E3-06's ticket and ADR 0137/0138
for the sweep pattern; E4-05's contract.

## Scope

- The task and its beat entry, Monday morning institution time, after window
  close and before instructors read (§3.1's rhythm; the exact minute is a
  decision below).
- The walk: sections with closed weeks lacking summary rows → per stream,
  gather the week's comments (under-threshold included, moderation-held
  excluded — vacuously today, structurally forever), call the task, store
  text, response count, themes if the contract carries them, prompt version,
  model id.
- Failure handling: a provider failure for one section-week leaves that row
  absent and the walk continuing; the next run retries it. The report
  tolerates an absent summary (E4-11 renders the absence honestly).
- Log discipline: section, outcome, duration — never comment text, never a
  summary, never a user id (E3's decision 10, extended).

## Acceptance criteria

1. Idempotence, driven: two consecutive runs over the same state produce
   identical tables — the second run writes nothing, proven by row identity
   and not by count.
2. A provider failure mid-walk: the failed section-week has no row, every
   other section-week has its row, and the next run fills the gap — one
   test, three assertions.
3. A small-N week gets its summary — §5.1's "generated even in small-N
   weeks" as the asserted state, with a two-response fixture week.
4. The stored row's response count equals the count of responses whose
   comments fed the call — injected from data, per E4-05's contract line.
5. The beat inventory test is updated in its own commit (E3-06's dispute
   E3-06-02 settled how the inventory grows), and the entry follows
   `publish_once`.
6. No log line from a planted failing run contains comment text or an
   identifier — asserted with log capture widened to this module, the
   E3-06 pattern.
7. Zero closed weeks (a term's first Friday) is a clean no-op run.

## Decisions this ticket settles

- **The beat time.** E3's passback runs Monday 02:20; this job must finish
  before instructors read Monday morning and should not contend with the
  passback's provider-free walk. Recommendation: Monday 02:50, recorded in
  the ADR beside the beat inventory update, with the reasoning that summary
  generation is provider-bound and benefits from the passback having already
  warmed nothing it shares.
- **Whether this job cuts release batches** — inherited from E4-04's ADR;
  if yes, the batch cut shares the per-section transaction with that
  section's summaries and the ADR here records the joint failure semantics
  (a batch is never cut on a walk that failed that section's summaries, or
  is, and why).
- **A cap on per-run provider calls** — a first term generates one
  section-week each Monday, but a backfill after downtime could be large.
  Recommendation: no cap, per-section transactions already bound the blast
  of a failure, and a cap invents a starvation mode; the ADR confirms or
  replaces.

## Known traps

- **The dev trigger question comes early.** The beat fires on real time
  while weeks close on the dev clock — E3-07 exists because of exactly this.
  E4 does not need a new `/dev` control if E3-07's precedent is followed
  when the exit drive needs one; building it *here* would be scope. The exit
  ticket (E4-15) owns drivability and may reuse `/dev/passback`'s shape.
- **Worker environment gotchas are real and recorded** — the compose
  DATABASE_URL poisoning memory; nothing here changes worker config without
  re-checking `docker compose exec worker printenv`.
- **An "even in small-N weeks" test that passes because the week was above
  threshold** — fixture weeks proven below threshold by construction.

## Out of scope

- The task's prompt, contract, evals — E4-05, already merged when this cuts.
- Reading summaries — E4-07.
- Regeneration in any form — ruled out by decision 2; a change there is a
  spec conversation.
- The Monday email — E12.
