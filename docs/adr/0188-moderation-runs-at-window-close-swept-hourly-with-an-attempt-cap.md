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
- **The attempt cap is six.** Only an unusable answer counts: the provider
  answered and the answer was not the contract (`AIResponseInvalidError`) or was an
  error status (`AIProviderRefusedError`). Each appends one `moderation_attempt`
  row. An outage (`AIProviderUnavailableError`, including a timeout, or
  `AIProviderUnreachableError`) writes nothing, and the comment is retried every
  hour however long the outage lasts. At six the sweep stops asking, logs the
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
- **Counting outages toward the cap.** A long outage would park every comment
  written during it for good, Care-class disclosures among them.
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
- The threat and self-harm recall floor and the moderation floor stay deferred to
  E10's live run; the typed cases ship now.
