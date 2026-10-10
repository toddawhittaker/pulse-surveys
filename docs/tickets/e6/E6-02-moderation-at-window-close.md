# E6-02 — Moderation runs when a window closes

**ID:** E6-02
**Branch:** `e6/moderation-at-window-close`
**Depends on:** E6-01 (the task member, the routing definer and its Python
call)
**Lane:** light
**Size:** M
**Security-relevant:** moderately. The sweep is what makes 01's rules fire in
the running system, and the empty-week sentence must not become a trace of a
withheld comment.

## Context

After E6-01, a comment appears only once it holds a verdict, but nothing asks a
model for one. This ticket adds the moderation call and an hourly sweep that
moderates every comment in a closed window that has no verdict yet, and routes
each verdict through 01's definer.

SPEC §7.4 says moderation runs asynchronously at window close; §5.2 says Care
routing is immediate. The breakdown settles it as at close, swept hourly
(README contradiction 7). This ticket edits §5.2's word and records the timing
in ADR 0188. Only harmful and privacy flag a comment for the instructor;
nonsense and clear do not.

The summary walk runs weekly at Monday 02:50 today. Under 01, a section-week
is not summarized until every comment has a verdict, so a weekly walk that
meets one missing verdict leaves the week with no summary for a week. The walk
becomes hourly.

Two carried items land here too. Summaries stored before E5.1 may keep
ordinary-mode text for a stream that is now held, and the small-N prompt says
"fewer students answered this week", which is false for a thin stream in a
full week (`carried-from-e5.md`, "Summaries written before the per-stream
rule"). And a developer's local `.env` may still hold
`BENCHMARK_MIN_RESPONDENTS_DEFAULT=15` (the E5 ledger row assigned to "E6's
first ticket").

`EMPTY_WEEK_SUMMARY` (`backend/app/ai/tasks.py:204`) says "No comments were
submitted this week." Once a Care-class comment is withheld, that can be
false. The new sentence must be the same in a week with no comments and in a
week whose only comment was withheld, or the sentence becomes the trace the
exit forbids.

Read first: SPEC §5.1, §5.2, §6.2, §7.4 and §9.3; ADRs 0148, 0153 and 0162;
`backend/app/ai/prompts/README.md`; `tests/evals/README.md`.

## Owns

- `backend/app/ai/prompts/moderation.v1.md` (new) and
  `classify_comment_moderation` in `backend/app/ai/tasks.py`.
- `EMPTY_WEEK_SUMMARY` in `backend/app/ai/tasks.py`, replaced by a true,
  neutral sentence (a new token).
- The sweep in `backend/app/services/moderation.py`, after 01's routing call.
- `backend/app/jobs/tasks.py` and `backend/app/jobs/schedules.py`: an hourly
  moderation sweep, and the summary walk made hourly.
- `mock-ai/app/rules.py`: a marker for each of the six verdicts.
- `tests/evals/moderation/` (`cases.py`, `floors.py`) registered in
  `tests/evals/registry.py`; threat and self-harm cases in
  `tests/evals/threat/`. Floors stay deferred to E10, as
  `tests/evals/threat/floors.py` already is.
- The small-N summary prompt under a bumped version (`summary.v3.md`, or the
  next free name), with an eval case for a thin stream in a full week.
- `_stored_summaries` in `backend/app/services/reporting.py`: a stored
  ordinary-mode summary for a stream that is now held is withheld.
- `README.md`, "Run it locally": a line telling every developer to set
  `BENCHMARK_MIN_RESPONDENTS_DEFAULT=10` in a local `.env` written before the
  E5 ruling.
- SPEC §5.2 (Care routing happens at window close, §7.4) and §13's
  `services/moderation.py` line if its comment needs the sweep.
- ADR **0188**: moderation at close, swept hourly; which verdicts flag; the
  summary waits and walks hourly.

## Reuse, do not rewrite

`classify_comment_validity` and `record_classification` (the call and record
pattern), `AIGateway` and the `AIGatewayError` classes, `load_prompt`,
`render_prompt`, `process_gateway`, `ModerationOutput` and `ModerationVerdict`.
The sweep copies `reclassify_floored_comments` (`services/validity.py`) and
its anti-join shape. 01's routing call in `services/moderation.py`; never a
second writer of `moderation_state`. `tests/evals/summary/` is the pattern for
typed cases.

## Done when

1. **A closed window is moderated.** After a window closes, the next sweep
   gives every comment in it a verdict through 01's definer. A comment that
   already holds one is not sent again.
2. **A failed call leaves the comment held.** When the provider fails, the
   comment keeps no verdict, stays out of every read, and is retried by the
   next sweep. The test asserts the effect, the missing row and the later row,
   not the sweep's return value (entry 49).
3. **Routing follows the verdict.** With the mock provider, a harmful or a
   privacy marker leaves the comment flagged-collapsed; a threat or a self-harm
   marker opens a `threat_case`; a clear or a nonsense marker publishes it.
4. **The summary walk is hourly and waits.** A section-week whose last verdict
   lands after Monday 02:50 is summarized on the next hourly walk, and a week
   already summarized is not summarized again.
5. **The empty-week sentence holds no trace.** The sentence is the same in a
   week with no comments and in a week whose only comment carries a self-harm
   verdict. A test asserts both, side by side.
6. **The small-N premise is per stream.** The bumped prompt speaks of the
   stream, not the week; its eval case is a thin stream in a full week; the
   stored summary row names the new version.
7. **Old ordinary-mode summaries are withheld.** A stored ordinary-mode
   summary whose stream is now held is not served, and a test plants one.
8. **Typed eval cases exist.** Moderation cases cover all six verdicts, built
   from `ModerationOutput`; threat and self-harm cases sit under
   `tests/evals/threat/`. No floor is set or moved.
9. **The records match.** SPEC §5.2 says Care routing happens at window close;
   ADR 0188 records the timing, the flagging rule and the summary wait; the
   README line names the value 10.

## Shares files with

- `services/moderation.py`: 03 adds the decision service in parallel. Keep
  both functions on merge.
- `services/reporting.py`: 03 edits `_payload` in parallel; this ticket edits
  `_stored_summaries`.
- `ai/contracts.py`: 03 adds `HeldNoteType` in parallel, if this ticket
  touches the file at all.
- `docs/adr/README.md` and `docs/SPEC.md` (§5.2, §13): 03 in parallel.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 30, 41, 48, 49 and 52.

## Known traps

- **Entry 49.** The sweep fails open. Assert the row, never the return value.
- **Entry 52.** A job module that binds an engine or a client at import is
  bound by whichever test imports it first. Take the import under the test's
  own environment.
- **Entry 30.** A fixture that plants the verdict cannot test the sweep that
  writes it. Drive the sweep through the mock provider.
- **The 06:00 Monday opening (ADR 0184).** An hourly walk must still summarize
  a normal week before 06:00. Test a week whose verdicts all land before 02:50,
  and one whose last verdict lands after.
- **A light ticket can re-lane.** If the new empty-week sentence or the
  withholding reds an invariant-marked test, the ticket becomes heavy and the
  PR says so.

## Out of scope

- The Care queue, and moderating on each submit (E10).
- Setting the moderation and threat eval floors (E10's live run).
- Who decides after a flag (03, 05).
