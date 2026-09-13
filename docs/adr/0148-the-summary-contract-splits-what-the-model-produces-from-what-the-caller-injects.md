# 0148 — The summary contract splits what the model produces from what the caller injects

## Context

SPEC §5.1 requires an AI summary to "state the response count they draw from",
and §7.4 gives the weekly summary a typed contract like every other task. It does
not say **who supplies that number**, and the two readings are a long way apart:
either the model reports how many responses it drew from, or the caller — which
counted the week's rows to select the comments in the first place — states it
beside the model's answer.

The same silence covers three neighbouring questions this ticket had to answer at
the same time, because the contract's shape is where all four land: whether one
call summarizes both of §5.1's comment streams or one each, what an empty week
answers, and how a week of comments is rendered into a prompt whose injection
boundary rests on the student text running to the end of the message
(`backend/app/ai/prompts/README.md`).

E4-05 builds the task. SPEC §5.1, §7.4 and §9.3 are the sections; none of them
settles any of the four.

## Decision

**The contract splits in two.** `WeeklySummaryOutput` carries what a model can
be asked for — the stream, the summary prose, and the themes with their per-theme
comment counts — and `WeeklySummaryRecord` composes around it the two values a
model must not be asked for: `response_count`, injected by the caller from data,
and `held_note_type`, which E6's moderation will populate and which is `None`
throughout E4.

Four consequences of that line, each settled here:

1. **Nothing a model says is trusted as a count of the week.** A response count
   from a model is a number nobody checked, and it is plausible by construction —
   an instructor reading "drawn from 12 responses" under a week of five is the
   only person who could notice, and cannot. §3.2 makes a comment optional above
   the rating threshold, so the count of responses and the count of comments are
   different numbers; `len(comments)` is the wrong one, and the caller has the
   right one already.
2. **One call per stream, and a week is two calls the caller makes.** §5.1 groups
   every comment under "About the instructor" / "About the course". Summarizing
   both in one call would let a course complaint be reported under the instructor
   heading — the instructor reads criticism of the materials as criticism of
   themselves — and no shape check can catch it, because the answer is
   well-formed. Two calls prevent it structurally: neither prompt contains the
   other stream's comments. The task also refuses an answer whose stream is not
   the one asked for, which is the other half of the same guarantee.
3. **An empty week reaches no model at all**, and answers a stated sentence with
   no themes, under `EMPTY_WEEK_PROMPT_VERSION` and the gateway's `NOT_A_MODEL`.
   That is ADR 0054's rule — a record produced without a call names the reason in
   its audit pair — applied to the second place in this codebase where a record
   exists with no call behind it. A *small* week is not this case: two comments in,
   a summary out, because below the n-threshold that summary is the only comment
   signal §4 leaves the instructor.
4. **The task has no fail-open and its timeout is its own.** SPEC §3.3 sanctions
   the floor for the validity check alone, because a student is waiting; nobody
   waits on a Monday report, and no heuristic stands in for a summary. A task that
   answered the empty shape on an outage would produce a record indistinguishable
   from a genuinely empty week's. The budget is sixty seconds rather than §3.3's
   four for the same reason the floor is absent: the caller is a job, and a week of
   comments is a much longer prompt than one comment.
5. **A theme claiming more comments than the week held is refused**, on the same
   terms as the wrong-stream answer and for the same reason it has to happen here:
   the task is the last place that knows how many comments it sent, §4 hides the
   raw comments below the n-threshold, and a count is what an instructor is given
   instead of them. Exactly the week's length is legitimate and is kept, and no
   count is ever adjusted — a clamped figure is one nobody produced. Added by the
   security round on this ticket, which found the bound living only in the offline
   eval checks and the mock's own answers, neither of which is on the path a real
   provider's answer takes.

The comments render as numbered blocks separated by blank lines, substituted into
the last placeholder in the prompt file, so the last comment ends the message and
nothing is appended after it.

## Alternatives rejected

- **One contract with the count on it, filled in by the caller after
  validation.** The cheapest change, and it keeps one class. It loses the
  guarantee: the contract is also §9.3's eval fixture and §7.4's API response
  schema, so a field the model is not asked for still appears in the schema the
  endpoint is shown, and a model that fills it in is then merely overwritten
  rather than refused. A shape the gateway derives from the contract (ADR 0031's
  `_payload_model`) is only honest if the contract says what the model produces.
- **Asking the model for the count and checking it against the caller's.** Two
  numbers, one comparison, and a well-formed answer that fails on arithmetic
  nobody needed. It spends a re-ask on a disagreement that has an authoritative
  answer sitting in the caller's hand.
- **One call for both streams.** It halves the spend, which is real. It also
  makes the cross-stream bleed a matter of the prompt's persuasiveness rather
  than of what was sent, and that failure is invisible in every check a stack
  could run.
- **Calling the model for an empty week anyway, for uniformity.** One code path
  instead of two. It is a request for a summary of nothing — the request most
  likely to come back with something invented — and an empty stream is common
  enough that it is a provider call per empty stream per section per week.
- **A `held_note_type` enum now.** It would make §5.2's threat and self-harm
  exclusion unrepresentable rather than merely required, which is the instinct
  this project holds. It was left as `str | None` because E6 writes the moderation
  states the type would enumerate, and an enum guessed here would be a closed set
  built before the thing it closes over exists. The gap is recorded with an owner
  and a "done when" in `docs/tickets/e4/deferred.md` rather than left in a comment.

## Consequences

- E4-06 stores a `WeeklySummaryRecord` and reads the prompt version and model id
  off `record.summary`, without re-deriving either from a constant — a record of
  the run rather than of the configuration.
- A week costs two provider calls where a stream has comments and none where it
  does not. Whoever budgets the Monday job counts streams with comments, not
  sections.
- The empty week's two markers are load-bearing in the same way ADR 0054's are: a
  reader asking which summaries no model produced selects on them, and renaming
  either breaks that quietly.
- `held_note_type` is a free string, so nothing stops E6 writing `threat` into it.
  §5.2 forbids it and §6.2's suppression depends on it. The deferral names E6 as
  the owner and "the type is a closed set excluding threat and self-harm,
  enforced where the note is written" as the done-when.
- A prompt that renders several comments has a marker line that survives
  rendering, which the in-repo mock provider dispatches on. That is a second copy
  of a string across a package boundary neither side can import across; it is held
  against the real prompt by a test, as the validity marker already is.
