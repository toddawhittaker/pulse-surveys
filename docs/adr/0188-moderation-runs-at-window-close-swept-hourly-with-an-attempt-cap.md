# 0188 — Moderation runs at window close, swept hourly, with an attempt cap

**Status:** Accepted
**Date:** 2026-10-10
**Ticket:** [E6-02](../tickets/e6/E6-02-moderation-at-window-close.md)

## Context

[ADR 0187](0187-moderation-verdicts-govern-the-read-path.md) shows a comment only
once it holds a moderation verdict and holds a whole section-week back until every
comment in it does, but nothing asked a model for a verdict. SPEC §7.4 runs
moderation "async at window close" while §5.2 said Care routing was "immediate";
a verdict also cannot be written before the close, because an answer is revised in
place until then (ADR 0187). The spec does not say how often moderation runs, what
happens when it keeps failing, or when the summary walk, which waits for it, runs.

## Decision

- **An hourly sweep at minute 10** (`moderate_closed_windows`,
  `app.services.moderation.sweep_unmoderated_comments`) asks the model about every
  non-blank comment whose window has closed by the app clock and which holds no
  `MODERATION` verdict, and routes each answer through `route_verdict`. A comment
  that holds a verdict is never sent again, so a later verdict can never pull a
  comment out of a report already read. SPEC §5.2 now says Care routing happens at
  window close. Only harmful and privacy flag a comment for the instructor;
  nonsense and clear publish it (ADR 0187's definer).
- **Closed means `closes_at < now`** by the app clock, the product's definition of
  a closed window; a window closing at exactly the sweep's instant waits for the
  next sweep. `route_verdict` (E6-01) still accepts `now == closes_at`, and E6-03
  aligns it to the same rule.
- **Two sweeps never overlap.** The sweep holds a Postgres session-level advisory
  lock (`SWEEP_LOCK_KEY`) for its whole run and releases it in `finally`; a run
  that finds the lock held does nothing. Without it, a long pass and the next
  hour's could each ask about the same comment, and one could give a verdict to a
  comment the other had just capped, after its week was read without it.
- **The sweep commits after each comment**, so a verdict and its Care route are
  stored before the next comment is asked about, and a later error cannot roll
  them back.
- **The attempt cap is six.** Only an unusable answer counts: the provider
  answered and the answer was not the contract even after the gateway's re-ask
  (`AIResponseInvalidError`). Each appends one `moderation_attempt` row. A refusal
  (`AIProviderRefusedError`: HTTP 401, 429, 500 and the like) and an outage
  (`AIProviderUnavailableError`, including a timeout, or
  `AIProviderUnreachableError`) write nothing and are logged at error level by
  answer id and class name; the comment is retried every hour for as long as the
  condition lasts. At six the sweep stops asking, logs the
  answer id once at error level, and the comment stays held: never given a verdict,
  never "clear", never accepted on timeout (the validity fail-open of SPEC §3.3 and
  ADR 0056 does not apply here). `section_week_moderated` counts a capped comment
  as resolved, so its week's other comments show, the release cut proceeds, and
  the summary is written without it. A capped comment is never routed to Care;
  E6-07 carries that to E10.
- **The summary walk runs hourly at minute 50.** A section-week is summarized on
  the first walk after its last verdict lands, and never again (the walk selects on
  "has no summary rows"). An ordinary week closed Sunday at 23:59:59 is moderated
  at 00:10 and summarized at 00:50, before the report opens at 06:00 Monday
  ([ADR 0184](0184-a-weeks-report-opens-at-six-on-the-monday-after-it-closes.md)).
  The release cut stays Monday 02:40; a section-week not yet moderated then is
  skipped whole and joins the next cut.
- **The empty-week sentence is "There are no comments to show for this week."**,
  the same for a week with no comments and a week whose only comment is withheld,
  so the sentence carries no trace of a withheld comment.
- **The small-N summary prompt is `summary.v3`**, which speaks of the stream
  rather than the week ([ADR 0182](0182-raw-comments-are-held-per-stream-by-distinct-commenters.md)).
  A stored ordinary-mode (`summary.v1`) summary of a stream that is now held is
  not served.

## Alternatives rejected

- **Moderating on each submit.** The verdict would vouch for text the student
  can still replace (ADR 0187); it is E10's, with the Care queue.
- **Counting outages or refusals toward the cap.** A long outage, an expired key
  or six hours of rate limiting would park every comment swept during it for
  good, Care-class disclosures among them.
- **Selecting `closes_at <= now`.** It matches `route_verdict` today, but the
  product treats a window as open at its closing instant; the sweep follows the
  product, and E6-03 brings `route_verdict` to it.
- **One commit at the end of the pass.** Every Care route would wait on the
  whole pass, and one unexpected error would roll them all back.
- **No cap.** One comment no model can answer would hold its week's summary back
  for ever.
- **Accepting a capped comment as clear.** That shows text no model has checked
  for a threat or a self-harm disclosure.
- **A weekly summary walk.** One missing verdict at the Monday walk would leave
  the week unsummarized for a week.

## Consequences

- An unusable answer that persists for six hours withholds a comment for good,
  and nobody but the error log hears of it until E10 routes such comments to Care.
- Ruling 5 holds: no deployment reaches real students before E10's Care queue.
- An old `summary.v1` row for a stream above the threshold is still served, and
  it may paraphrase a comment later found Care-class. That is development data
  only under ruling 5; E6-07 carries it to E10.
- Because refusals are retried rather than counted, the comments that do reach
  the cap are the ones whose text breaks the model's answer, and those may lean
  toward Care-class disclosures. E6-07 carries that skew to E10 with the capped
  comments themselves.
- The threat and self-harm recall floor and the moderation floor stay deferred to
  E10's live run; the typed cases ship now.
