# 0138 — The score timestamp is real time, never the development clock

## Context

Every AGS Score carries a `timestamp`, and a platform compares it against the one
it already holds for that student on that column: a strictly earlier instant is
refused with 409, and an equal one is accepted as a retry of the same delivery
(ADR 0052). So the field is not a note about when something happened — it is the
ordering rule the passback is arbitrated by.

ADR 0109 makes this project's development clock an **offset** on real time rather
than a freeze, applied through `app.services.clock` and readable by the tool and
the worker alike. It also accepts a past instant: a demonstration can rewind to
the middle of a term and watch a week close. Everything the participation formula
computes runs off that clock — which weeks have elapsed, which enrollments are
live, which term is still inside the sweep's bound.

The recompute therefore has two instants available where every other service in
this tree has one, and the choice is visible in a way nothing else's is. E3-06's
ticket names the consequence outright:

> **The development clock makes a 409 reachable in a demo.** Elapsed weeks count
> off `clock.now` while the beat fires on real time, and the development override
> accepts a past instant. Rewind it, run a passback, and the score timestamp is
> strictly earlier than the one the platform already holds — which is a 409, which
> E3-04 correctly reads as stop-and-re-read. That is the right behaviour and a
> baffling demonstration.

## Decision

**The score timestamp is `datetime.now(UTC)`, captured once per service call, and
the development clock never reaches it.** `score_timestamp_text(instant)` —
`instant.astimezone(UTC).isoformat()` — is the one place a wire timestamp is
rendered, so a stored `score_timestamp` re-renders to the exact characters
originally sent and ADR 0052's retry is reconstructible from the row.

**Content is effective-clock; delivery is real-clock.** `participation_scores`
goes on counting elapsed weeks off `clock.now`, `clock.today` decides which
enrollments are live and which terms are inside the bound, and none of that
changes. What is stamped from the real clock is the one value the *protocol*
orders on.

This puts the AGS timestamp in the class ADR 0109 already exempts from the
override, beside `ags_call.called_at` and `nrps_call.called_at`: protocol and
observability instants, as against calendar ones.

## Alternatives rejected

**`clock.now`, for consistency with everything else the service reads.** It is the
more natural-looking line of the two, which is exactly why it is written down as a
rejection rather than left to taste: every other instant in this module comes from
the clock service, so the wrong answer is the one a reader will reach for. It also
produces the ticket's named trap — a rewound demonstration in which every post is
refused 409 and the correct client behaviour looks like a bug.

**`clock.now`, with the demo told not to rewind.** A rule nothing enforces, about
a control ADR 0109 deliberately built to accept a past instant. The whole point of
the offset clock is that a person can move it.

**Making the timestamp the instant the *recomputation* used** — the effective now
at which the score was computed. It has a real argument: the timestamp then names
what the number describes rather than when it was sent, which reads well in a
dispute. It fails on the same rewind, and it fails a second way: two runs a week
apart under a clock that has not been moved would still stamp two different
instants, so it buys nothing that real time does not.

**Rendering with `Z` rather than `+00:00`.** The same instant and different
characters. ADR 0052's retry identity is byte equality of a body a platform
already accepted, so the spelling is fixed by whichever one is written first;
`datetime.isoformat`'s own is `+00:00`, and it is what the mock platform's grammar
accepts.

## Consequences

- A demonstration can rewind the clock, watch weeks close, and see scores posted
  in the right order. The 409-in-a-demo trap is removed rather than documented.
- The timestamps in `grade_sync` are real time and the weeks they describe are
  effective time, so under a moved clock the two disagree, deliberately. A reader
  of that table who wants "when was this week" reads the week, not the timestamp.
- A retry re-sends a stored instant, which can be arbitrarily old, and that is
  correct: it is the delivery being repeated. Only a changed value gets a fresh
  instant, which is what makes a correction sort after the thing it corrects.
- `grade_sync.created_at` stays on the column's own `now()` default and is not
  written by the sweep, for the same reason and one more: it is the key the
  latest-row comparison orders on, so a movable value there would let a rewound
  clock make a new row sort before an old one and leave the sweep comparing
  against a stale row for as long as the rewind stood. That is a worse fault than
  the one this record removes, and it is silent.
