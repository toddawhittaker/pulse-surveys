# 0137 — The recompute is a weekly sweep that posts on a difference, and the schedule is its only retry

## Context

SPEC §3.4 says a participation score is "Re-posted whenever a recomputation
changes the value, ordinarily after each week closes". Four questions have to be
answered before that sentence can be written as a job, and the spec settles none
of them.

**When it runs, and how far back it reaches.** SPEC §3.1 closes every window on
Sunday at 23:59:59 institution time, so there is an obvious day. There is no
obvious answer to how much of the past a run should walk: a job that visits every
section of every term does work that grows without limit against platforms that
have long since archived the courses, and eventually recomputes terms whose raw
responses SPEC §4's retention has already deleted.

**What "the value changed" is measured against.** `grade_sync` is append-only at
the grain of one row per post (ADR 0124), so there is no stored current value to
compare with — there is a history, and a reader has to choose which row of it
speaks for the present.

**What a re-post carries when it is repeating one that failed.** ADR 0052 has a
platform accept a score whose timestamp equals the one it already holds as a
*retry of the same delivery*, and treat a different timestamp as a new score. So
the difference between a retry and a second grade is one field, and it is decided
by whether the values sent are re-derived or re-read.

**What happens after a post is refused.** ADR 0132 rejected a retry loop inside
the AGS client by name, and left the question of where retrying belongs to the
layer that has memory across runs.

The structural fact behind all four is the one the epic is built around: **a
posted score is not final when its week closes.** E2-08's asynchronous
reclassification can flip a comment that fell to §3.3's fail-open floor from
substantive to `insufficient` weeks after the window shut, which lowers the
numerator of a number already sitting in somebody's gradebook.

## Decision

**A sweep that posts on a difference, with a weekly beat as its ordinary
trigger.** `post_scores_for_all_sections` in `app/services/grading.py` is
idempotent: it computes, compares, and posts only where the two disagree. The beat
entry `post-participation-scores-weekly` runs
`app.jobs.tasks.post_participation_scores` on `crontab(day_of_week="mon",
hour="2", minute="20")` — Monday because it is the first day the week §3.1 closed
on Sunday can be scored, 02:20 because the reclassification passes at 00:45 and
01:45 have by then had two attempts at that week's floored comments, and because
minutes 0, 15, 30 and 45 already belong to jobs that walk every section in the
institution. The schedule is the ordinary trigger and not the definition of the
work: running the sweep twice posts once.

**The walk is bounded by the term, at fourteen days.**
`TERM_SWEEP_GRACE_DAYS = 14`, and a section is walked while `term.end_date +
TERM_SWEEP_GRACE_DAYS >= clock.today` and it carries a gradebook container
address. Fourteen days is two more weekly runs after a term's last day: one for
the final week's post, one corrective pass for a reclassification that lands late.
The bound is measured from the **term** and not from the section, because a
six-week cohort finishing in early November sits well inside its term and a bound
measured from its own end date would stop posting for it six weeks before every
full-term section beside it.

**The comparison is against the latest `grade_sync` row for the pair, ordered by
`created_at`, and it is over the pair `(score_text, ledger_text)`.** Not the
percentage alone: a reclassification, a question set that changed a week's
denominator, or a late add that moved which weeks count can each leave the number
equal and the arithmetic behind it different, and SPEC §3.4 puts that arithmetic
in the comment beside the score (ADR 0125). Three outcomes follow.

  - No row, or a pair that differs from the computed one: a **new delivery**,
    carrying the characters the formula just produced and one instant captured per
    run.
  - A `FAILED` row whose stored pair equals the computed one: a **retry of that
    delivery**, re-sending the stored characters and the stored instant, so ADR
    0052's identity holds byte for byte.
  - A `POSTED` row whose stored pair equals the computed one: **nothing**, and no
    HTTP call at all on that student's account. A section where no student needs a
    post makes no call of any kind — not a token grant, not a line-item read.

**The schedule is the retry, and there is no backoff.** A refused post appends a
`FAILED` row carrying the status the platform answered, or the literal 409 for the
one refusal a retry cannot fix, and the run moves on to the next student. Nothing
is attempted twice inside a run. A 409 heals itself, because the next run's fresh
real-time timestamp is later than whatever the platform holds (ADR 0138).

**Posting stops at a drop, and this is the only place that stop exists.** A
student posts while `started_on <= clock.today AND (ended_on IS NULL OR ended_on
>= clock.today)` holds of any of their enrollment rows — `app/services/authz.py`'s
own predicate, so a drop-and-re-add has two rows and the live one wins. Nothing is
posted on the way out: no final zero, no blanking. SPEC §3.4 gives the LMS the
column.

**A section inside the bound with no line item asks for one and posts nothing**,
through E3-05's own bounded publish (ADR 0135), once per section rather than once
per student. That closes the window ADR 0135 named.

## Alternatives rejected

**A literal reading of "after each week closes" — recompute Monday, post what you
computed.** It is what the sentence says and it is wrong some of the time,
silently: a reclassification that lands in week nine changes week three's
numerator, and a schedule-driven post has no reason to look at week three again.
The cost of the sweep is that a difference is noticed up to a week late; the cost
of the literal reading is that it is never noticed at all.

**Comparing against a stored current value on `section` or `enrollment`.** One
row, one read, no ordering question. It also destroys the number a student was
previously shown, which is the whole of ADR 0124's argument: the question asked
when a grade is disputed is *what did we send, and when*.

**Posting unconditionally every week.** Idempotent in a gradebook, because an
identical body changes nothing there. It is also tens of thousands of requests
every Monday morning against every platform at once, and it makes the call log
useless for the thing §6.1 built it for — telling a section whose posts are
failing from one that had nothing to send.

**A retry loop with backoff inside the run.** It is what "retries under the stated
policy" sounds like it should mean. ADR 0132 already rejected it one layer down
and the argument carries: a client retrying per section is every section retrying
at once against a platform that is already struggling, and a loop inside one run
has no memory of the run before it. The weekly schedule has that memory in
`grade_sync`, which is what makes it a policy rather than a delay.

**No bound on the walk, or a bound expressed as "sections with a live term".**
The first is unbounded work; the second has no definition that survives a term
whose end date has passed but whose grades are still being adjusted. A grace in
days is a number a reader can check against §4's retention rule.

**A larger grace — thirty days, a term, forever.** Every extra week is another
week in which the sweep can recompute against data §4 is about to delete and post
the result into a gradebook years later. Fourteen days is the smallest number that
covers the final week's post plus one corrective pass.

## Consequences

- **A reclassification that lands more than fourteen days after a term ends never
  re-posts.** That is the named residue of the bound: the score the platform holds
  is the last one this sweep sent, and it is the one an appeal is answered from.
  It is a deliberate trade against recomputing a finished term from data that is no
  longer there, and it is stated here so a later ticket that wants the other
  behaviour argues for it rather than discovering it.
- A difference is noticed up to a week late. A student whose score changes on
  Tuesday sees it on Monday. E3-07's development trigger runs the same sweep on
  demand for a demonstration; nothing in E3 shortens the production cadence.
- What an operator sees for a section whose posts are failing is the `ags_call`
  row (the URL, the status, the instant, the section) and the `grade_sync` row (the
  outcome, the response code, and what was sent). Both are per attempt, so a
  section stuck for a month shows four rows rather than a counter. E11 builds the
  screen; this is what it will read.
- The run answers `{"posted": p, "failed": f}` and the task returns it unchanged,
  which is the only number about a run that reaches a log line. Nothing the job
  logs carries a score, a ledger line or an LMS user id, and the section-level
  catch withholds its traceback for that reason: a refused insert renders its own
  parameters, and those parameters are a student's score and their ledger.
- **The sweep names its student through a definer function rather than by reading
  a column.** An AGS Score is keyed by the LTI `sub`, which lives only in
  `user.lms_user_id`, and `pulse_app` was refused `SELECT` on that column by
  E1-10's round-3 security review. The sweep therefore resolves each subject
  through `app.services.identity.subject_for_user`, one row at a time, and
  `app/services/grading.py` reads no column of `user` by any route. ADR 0139
  records that decision, what it gives back and what it does not; it arrived as
  this ticket's blocker and was settled before it merged.
