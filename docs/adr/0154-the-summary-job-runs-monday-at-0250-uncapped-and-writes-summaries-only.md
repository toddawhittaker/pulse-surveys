# 0154 — The summary job runs Monday at 02:50, uncapped, and writes summaries only

## Context

E4-06 adds the Monday walk that generates SPEC §5.1's per-stream AI summaries.
Its ticket leaves three questions open, and none of them is answered by the spec.

**When it runs.** SPEC §3.1 closes every survey window on Sunday at 23:59:59 in
the institution's timezone and makes the instructor's report available "Monday
morning". That fixes the day and says nothing about the hour, and the hour is not
free: E3-06's participation sweep already holds Monday 02:20 and walks every
section in the institution, and E2-08's reclassification passes run at 00:45 and
01:45 over the comments SPEC §3.3's fail-open floor stood in for.

**Whether one run may be bounded.** A first term generates one section-week per
section each Monday, which is nothing. A backfill after downtime, or the first
Monday after a term of windows was derived, is a walk of unknown size making up
to two provider calls per closed section-week — and SPEC §10 budgets "Monday
report generation for 500 sections < 30 min".

**Whether this job also cuts E4-04's release batches.** E4-06's ticket was written
expecting to inherit that: "if E4-04's ADR rules that the release batches are cut
by this job (its recommendation), that half lands here too … this job then does
two writes per walk". Both tickets were then scheduled into the same wave, in
parallel worktrees, and the question had to be answered before either could be
built.

## Decision

**Monday 02:50, no cap on a run, and summaries only.**

**The beat entry is `crontab(day_of_week="mon", hour="2", minute="50")`.** Monday
is forced from both sides: it is the first day the week that just ended can be
summarized at all, and the last day it can be summarized before the reader of the
report it leads arrives. Nothing regenerates a summary (the E4 breakdown's
decision 2), so a summary that arrives late never arrives for that week's reader.
02:50 puts thirty minutes between this walk and E3-06's, which is not politeness:
the two walk the same sections, one of them makes model calls and the other makes
none, and a shared tick has them contending for the same rows and the same worker
pool for no reason. It also puts both of E2-08's reclassification passes in front
of it, so the comments the character floor stood in for have had two chances at a
real verdict before the week they belong to is summarized — the same ordering
argument E3-06's own 02:20 rests on, and it matters more here, because a score is
re-posted when a verdict lands and a summary is not.

**No cap on the model calls one run may make.** The unit of failure is already
bounded: each section-week is its own transaction, so a provider failure costs
that week's two summaries and the walk continues. A cap adds nothing to that and
takes something away — it decides that some section's week goes unsummarized, with
nothing choosing which, and with no mechanism that ever comes back for it. That is
a starvation mode in a job whose only retry policy is that it runs again next
Monday, and a section at the wrong end of an arbitrary ordering would wait a week
at a time.

**This job writes summaries and nothing else.** E4-04's cumulative release batches
are cut by a scheduled task of E4-04's own, recorded in ADR 0152 and landing in
that ticket's pull request. E4-06's inherited "if yes, that half lands here too"
is resolved to no, and its ticket file is corrected in the same change as this
record.

## Alternatives rejected

**02:20, sharing E3-06's tick** — one Monday slot to reason about instead of two.
Rejected: the two walks visit the same sections, and putting a provider-bound job
on the same tick as a provider-free one makes each one's runtime a function of the
other's. The cost of the split is a second minute to remember, which the schedule
file's comment block carries.

**Later in the morning — 05:00, say, with more room before an instructor reads.**
Rejected: it buys nothing this job needs and spends the margin SPEC §10's
thirty-minute budget leaves. The window closed six hours earlier and the work is
the same work; the only thing a later slot changes is how much of Monday morning
is left if the run has to be repeated by hand.

**A `timedelta` schedule** — "weekly", written as an interval. Rejected for the
reason E1-11's roster entry gives: an interval drifts with every restart, so which
hour a week's summaries were generated in would depend on when beat last came up.
This is the one job whose output somebody is waiting on at a fixed hour.

**A cap on provider calls per run**, the ticket's own open question, with an
uncapped run left to a manual trigger. Rejected: it converts a bounded cost into
an unbounded delay. The failure a cap protects against — a backfill spending more
than expected at a provider — is visible in the run's own log line and is a
one-time cost after downtime, while the section it silently skips is invisible and
recurs.

**A per-run deadline instead of a call count**, stopping the walk when the clock
runs out. Rejected for the same reason and one more: it makes which sections get
summarized depend on how slow the provider was that morning, so the same
institution gets a different answer each week with nothing recording why.

**Cutting E4-04's release batches inside this walk's transaction**, which is what
E4-06's ticket was written expecting. Rejected: it makes a release depend on a
summary having succeeded, which is a coupling neither SPEC §4 nor §5.1 asks for —
a provider outage on Monday morning would then also hold back the comments a
section's cumulative threshold had already released, and the two writes have
nothing else in common. Keeping them apart also keeps two parallel branches out of
each other's files.

## Consequences

- **The schedule now runs seven entries**, and Monday morning holds three passes
  over every section: E3-06's participation sweep at 02:20, E4-04's release cut at
  02:40 (ADR 0152, merged before this one) and this walk at 02:50. Only two of
  them touch a provider — E3-06's sweep and this one — and the thirty minutes
  between those two is the gap this decision argues for; the release cut sits
  between them and calls no model at all. An institution large enough for E3-06's
  sweep to overrun 02:50 would have the two overlap again; nothing detects that,
  and the first symptom would be a slow Monday rather than a wrong one.
- **A large backfill is unbounded by design.** The first run after a long outage,
  or the first Monday of a stack whose windows were derived for a whole term at
  once, walks every closed section-week it finds and makes up to two provider
  calls for each. What that costs is recorded in the run's own log line — the
  count found, the rows stored, the seconds taken — and nothing stops it. SPEC
  §10's thirty-minute budget is about the ordinary Monday, and this record does
  not claim it covers a backfill.

  > **Amended 2026-09-08 by E4-15's boundary round: the *ordinary* Monday does not
  > fit inside that budget either, on the numbers the spec itself supplies.** The
  > walk is serial — one section-week at a time, two provider calls each, in one
  > worker — and SPEC §10 budgets "Monday report generation for 500 sections
  > < 30 min" while §7.4 and §3.3 budget a model call at p95 < 2s. Five hundred
  > sections with one closed week each is 1,000 calls; at 2s apiece, executed one
  > after another, that is 2,000 seconds — **about 33 minutes**, over §10's line
  > before a single database read, commit or retry is counted, and before the
  > release cut at 02:40 or the participation sweep at 02:20 have taken any of the
  > same half hour. The margin this record says an uncapped run spends is not
  > there to spend.
  >
  > Nothing is changed here on that basis, and the reason is that the arithmetic
  > is a bound rather than a measurement: it assumes the p95 for every call, which
  > no run has, and it says nothing about what the mean actually is against a real
  > provider. What it does say is that the two spec figures are close enough that
  > the ordinary Monday is a capacity question rather than a comfortable one, and
  > that the answer — a concurrency, a per-section fan-out, a longer window, or a
  > revised §10 figure — is a design decision that needs a measurement first.
  >
  > **E13's load test is the owner of that revisit.** It is the ticket that
  > measures a Monday at scale, and this paragraph is what it should read before
  > it does. Recorded here rather than in a carried-work file because the number
  > it corrects is this record's own.
- **E4-04 and E4-06 each own one scheduled task**, so the two tickets touch
  `app/jobs/schedules.py` and `app/jobs/tasks.py` in the same wave and their
  appended entries are merged rather than rebased over each other. Neither
  reorders what is already there.
- **E4-06's ticket file carried two sentences that this decision makes false** —
  its context paragraph and its "whether this job cuts release batches" decision —
  and both are corrected in this change rather than left for a reader to
  reconcile against ADR 0152.
