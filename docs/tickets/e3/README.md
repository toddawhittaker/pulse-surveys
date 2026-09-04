# E3 — Grade passback: build order

Eight tickets decomposing SPEC §14.3's E3 entry. Each is sized for a single
focused session and leaves the repository in a working state: CI green,
Compose stack healthy, nothing half-wired at a boundary. E3 is **not** a ⚠
epic — no line-by-line human review mandate — but every ticket still gets the
independent per-PR security review, and two lanes still govern how tickets
are built (`.claude/heavy-lane-paths.md` is the authority; the header
decides, a missing field means heavy).

Say **"build E3, ticket 5"** and it means E3-05.

Branch names follow `CONTRIBUTING.md`: cut `e3/<slug>` from
`epic/e3-grade-passback`, one ticket per branch, one pull request into the
epic branch.

**Read before building anything here:** `docs/tickets/e3/carried-from-e2.md`
(every entry — this breakdown schedules the E3-owned ones, and the mapping is
below), SPEC §3.1, §3.3, §3.4, §7.3, §9.1, §14.3, and `docs/MISTAKES.md`
whole. One inherited expectation does not survive the formula ruling and is
worth knowing before E3-03 is built: E3 was to be the first reader of
`response.is_valid`, and it is not. The field already has a reader —
`backend/app/api/student.py:231` returns it to the student — and the
item-based formula does not use it, because a per-response verdict cannot
express a week answered four items of five. The formula reads the answer rows
and each comment's most recent classification instead.

Items an E3 ticket defers rather than fixes live in `deferred.md` (created by
the first PR that needs it); a PR that defers something adds it there in the
same PR, and E3-08 runs the cleanup pass over the file.

**Lanes in this breakdown:** every ticket is heavy. The epic's substance lives
in `backend/app/services/`, `backend/app/models/`, `backend/app/lti/`,
`backend/app/api/`, `backend/migrations/`, `mock-lms/`, `tests/fixtures/` and
`backend/app/jobs/` — the first eight are named rows in
`.claude/heavy-lane-paths.md`, and `backend/app/jobs/` matches no row while
sitting under `backend/app/`, so that table's fail-closed rule makes it heavy
too. E3 ships no frontend, so there is no light-lane work in the epic at all.

## Decisions ruled at breakdown

Eleven decisions were settled before the first ticket branch, recorded here
so no ticket re-litigates them. The first three change what the product does
or what it discloses, and are recorded in SPEC §3.3, §3.4 and ADR 0125 by the
same pull request as this file. The other eight are construction decisions
the spec does not make; one of them carries ADR 0124, and the rest are
defaults a ticket may depart from only by saying so.

1. **The participation score counts items, not weeks. Ruled 2026-09-04:** the
   fraction is completed items ÷ total items across the student's elapsed
   weeks, not valid weeks ÷ elapsed weeks. A week carries roughly five items,
   and a student who answers four of them earns four fifths of that week
   rather than nothing. The total is derived from the `question_set` in force
   for the week and is never a constant, because the set is versioned and the
   extension point in §3.2 exists precisely so a week's item count can change.
   §3.4's late-add tiers, its drops rule, and §3.1's no-back-fill rule all
   stand unchanged — they now select the *weeks* whose items form the
   denominator.
2. **Each posted score carries a per-week ledger in its comment. Ruled
   2026-09-04:** the AGS comment on a posted score is one line per elapsed
   week, of the form `Week 1: 4 of 5 items`. The comment is the only place the
   arithmetic is visible to anyone, because E3 ships no student surface and no
   instructor surface.
3. **The ledger's instructor visibility is accepted. Ruled 2026-09-04**, and
   recorded in ADR 0125. An AGS score comment is not private to the student:
   it sits in the gradebook where an instructor reads it, and a per-week
   completion pattern narrows the set of students who could have written a
   given week's comment. This is accepted because the channel is not new — a
   weekly-updated participation score already carries the same fact through
   its deltas, since §3.4's denominator is a public rule and the week count
   is the calendar. The ledger adds convenience, not a channel. The rejected
   alternatives were a totals-only comment and no comment at all, and the
   acceptance holds only while the ledger carries completion counts and
   nothing else.
4. **`grade_sync` is append-only, one row per post. Settled at breakdown,
   2026-09-04**, and recorded in ADR 0124. The latest row for a student and
   section serves the retry identity and the recompute's comparison; the
   rows behind it are the account of what Pulse told a third-party gradebook
   about a student's standing, which a row updated in place would destroy the
   moment a re-classification lowered a score.
5. **The week axis is the course week.** Elapsed weeks are counted on the
   section's own course-week axis (§2.2), the axis §3.4's late-add tiers
   already speak in, not the term week.
6. **A week is elapsed when its window has closed.** A week counts toward the
   denominator once its `survey_window.closes_at` is past `clock.now`, not
   when the recompute job happens to fire. The job's schedule therefore never
   changes an answer; it only changes when the answer is posted.
7. **Zero elapsed weeks means no post at all.** A section whose first window
   has not yet closed gets no score, not a posted zero. A zero in a gradebook
   is a statement about a student; an absent score is a statement about the
   term, and only the second one is true before the first week closes.
8. **The recompute is an idempotent sweep that re-posts on difference.** It
   posts when the computed value differs from the value in the latest
   `grade_sync` row for that student and section, and posts nothing
   otherwise. A weekly beat entry is the ordinary trigger rather than the
   definition of the work, because a score is not
   final when its week closes: E2-08's asynchronous reclassification can
   change an already-posted week's numerator weeks later.
9. **A student launch never causes a write to the platform's gradebook.**
   Line-item creation follows §7.3's roster-trigger rule exactly — an
   instructor launch triggers it, a leadership launch triggers it only inside
   the launcher's own purview, and a student launch triggers nothing.
10. **A worker log about a passback carries no score, no ledger and no user
    identifier.** The task logs the section, the outcome and the call, and
    nothing that would put a participation figure or an LMS user id in a log
    stream. This answers the question E0-03 left open and dated to E3.
11. **`PlatformProfile` ships as the mechanism plus the mock's profile only.**
    The adapter seam §7.3 describes is built, and exactly one profile is
    written against it. Canvas, Moodle, D2L and Blackboard are in the
    deliberately-not-done list below, because a quirk adapter written against
    a platform nobody has launched from is a guess with a file name.

## Build order

| # | Ticket | Branch | Depends on | Summary | Merged |
|---|---|---|---|---|---|
| 01 | [A deployment can supply and rotate the tool's signing key](E3-01-signing-key-custody.md) | `e3/signing-key-custody` | none | The carried custody item: a non-development deployment gets a way to hold the key, and rotation gets the two-key overlap the one-row rule forbids today. Free-standing. | |
| 02 | [The passback schema, and the address the launch supplies](E3-02-passback-schema-and-address.md) | `e3/passback-schema-and-address` | none | Everything the epic writes to, before anything writes it: the AGS container address captured from the launch claim, the line item's own id, `grade_sync`, and `ags_call`. | |
| 03 | [The participation formula](E3-03-participation-formula.md) | `e3/participation-formula` | none | `services/grading.py` as a pure computation: elapsed weeks under §3.4's tiers, the item numerator and denominator, the percentage, the ledger string, and the Hypothesis properties §9.1 asks for. | |
| 04 | [The AGS client, and the mock's AGS routes start asking for a token](E3-04-ags-client-and-mock-enforcement.md) | `e3/ags-client-and-mock-enforcement` | 02 | `lti/ags.py` on the roster sync's conformance shape, line-item find-or-create against querified ids, and ADR 0099's pairing made structural rather than promised. | |
| 05 | [The line item is created on the first staff launch](E3-05-line-item-on-first-launch.md) | `e3/line-item-on-first-launch` | 02, 04 | §3.4's "created by the tool on first launch" wired to the launch door on the bounded enqueue shape, with a student launch writing nothing. | |
| 06 | [The weekly recompute posts a score when it has changed](E3-06-weekly-recompute-and-post.md) | `e3/weekly-recompute-and-post` | 03, 04, 05 | The beat entry and the thin task: walk the sections, compute, compare against last sent, post, record, retry. Drops stop posting. | |
| 07 | [A development trigger for passback, and the CSRF route sweep](E3-07-dev-trigger-and-csrf-sweep.md) | `e3/dev-trigger-and-csrf-sweep` | 06 | The `/dev` control that makes the epic drivable in a browser on the dev clock, and the carried CSRF item whose red case this epic's first mutating route finally makes honest. | |
| 08 | [E3 exit](E3-08-e3-exit.md) | `e3/e3-exit` | all | §14.3's exit clause driven end to end across every enrollment edge case; boundary reviews; `../e4/carried-from-e3.md`. | |

## Dependency graph

```
01 ─────────────────────────── (free-standing, any time)

02 ── 04 ── 05 ─┬─ 06 ── 07 ── 08
03 ─────────────┘
```

(04 needs 02; 05 needs 02 and 04; 06 needs 03, 04 and 05; 07 needs 06; 08
needs everything, 01 included. 04's edge into 06 runs through 05 and is not
drawn twice. **03 is not an input to 04** — the formula and the client share
nothing, which is what lets the epic's hardest reasoning run beside its
plumbing rather than behind it.)

Three starts run in parallel on day one. **01** is unrelated to grades
entirely and can land at any point in the epic. **02** builds the tables and
the stored address. **03** is the formula, which reads only tables E2 shipped
and needs nothing E3 builds — so the epic's hardest reasoning starts
immediately rather than queuing behind its plumbing. **04** is the pinch
point: everything downstream waits on the client, and the mock's token
enforcement rides with it rather than beside it. **05** and **06** are
strictly ordered, because a score cannot be posted to a line item that does
not exist. **07** and **08** close.

## Exit criterion → the tickets that prove it

§14.3 E3's exit line is one clause — the mock-LMS gradebook shows correct
percentages across enrollment edge cases — and E3-08 drives each case against
the running stack.

| Case | Rests on |
|---|---|
| a day-one student with every week answered in full | 03, 04, 05, 06 |
| a week answered four items of five | 03, 06 |
| a missed week, scored zero of that week's items | 03, 06 |
| a platform-dated late add | 03, 06 |
| an undated late add the section's first roster sync already contained | 03, 06 |
| a late add first seen after the section's first sync | 03, 06 |
| a dropped student, whose score stops updating | 03, 06 |
| the gradebook read back through the conformant Result container | 02, 04, 08 |

## Where the carried work landed

Every E3-owned entry of `carried-from-e2.md`, with the ticket that schedules
it. The entries' own done-whens govern; the tickets point at them.

| Item | Lands in |
|---|---|
| A non-development deployment has no way to supply the tool's signing key | E3-01 |
| AGS still answers without a token (deadline: paired with the first AGS client) | E3-04 |
| The mock's scope check is only provably a membership check while no advertised scope is a superstring | E3-04. The pair already exists — `mock-lms/app/ags.py:92` advertises both the line-item scope and the line-item read-only scope, and the read-only string contains the line-item string as a prefix — and it becomes *provable* only once the AGS routes require a credential, which is E3-04's other half. |
| Nothing structurally forces the next mutating route onto the CSRF dependency | E3-07 |
| The launch-path roster enqueue still waits six seconds on a broker that is down | E3-05 — **taken at breakdown**, because the entry's owner is whichever epic next touches the launch door's suites and E3-05 is that ticket |
| `PERSON_TABLES` standing review question, asked of the tables E3 adds | E3-02 (answered in its PR body), re-asked of the whole epic in E3-08 |
| Grade passback reading validity state (spec-owned to E3) | **Superseded by the formula ruling of 2026-09-04.** The entry rests on E2-08 writing `response.is_valid` for E3 to read, and the item-based score does not read it — it reads the answer rows and each comment's most recent classification, a finer grain than a per-response verdict carries. E3-03 consumes the validity *machinery* (§3.3's refused set, the append-only classification rows) without consuming that column. The column is not orphaned: `backend/app/api/student.py:231` returns it to the student. E3-03 corrects the records that justified the column by naming E3 as its reader. |
| The session-read sweep's two disclosed limits | E3-08 re-affirms the sweep still reaches `services/grading.py` |
| The TypeScript 7 pair's floating owner | E3-08 checks at exit whether `typescript-eslint` admitted 7.x on E3's watch |
| A rewound development clock can wedge a section's roster sync | **To-know for E3-06 and E3-07**, whose timestamp and dev-trigger decisions touch the same interaction; not closed here, and re-carried by E3-08 |

Every other `carried-from-e2.md` entry passes through by being re-listed in
`carried-from-e3.md` at E3-08 — the completeness rule is *every entry not
closed inside E3, whoever owns it*, so the enumeration below is the coverage
proof and is meant to be complete rather than representative:

- **E4's**: the reveal-subject guard with its deadline, the copy-collector's
  symlinked-directory gap, and the rendered student surface's string
  convention that nothing sweeps.
- **E6's and E10's**: the bounced comment refused before any harm screening
  exists.
- **E9's**: logout and back-channel logout, the generative purview coverage
  note, and the web-login linkage.
- **E10's**: the floor-headroom variance point.
- **E11's**: the squatted section binding, the CSP-breaking authorization
  endpoint stored verbatim, the verdict-row aggregation half of the bounced
  attempts entry, and the two registration-write blind spots a console has to
  know about.
- **E13's**: the structural `PERSON_TABLES` source, the local-account
  fallback, and the self-hosted font licences.
- **Owned by nobody, carried as notes to a later reader**: the unproven
  structural battery rows, and the denial-module closure sweep's inventory —
  the latter settled at E2's breakdown and carried only if a boundary
  re-affirmation reports its two disclosed limits no longer hold.
- **Owned by a candidate ticket rather than an epic**: the bounce that names
  no offending position, the week eyebrow that cannot say how long a course
  runs, the resubmission answering 500 under a rewound clock, the model
  identifier living in three untied places, and the stale Care-landing
  docstring.

That last one is the only candidate E3 cannot take even in principle: it
needs a light-lane ticket touching `frontend/src/routes/care/`, and E3 has no
light-lane work.

## What E3 deliberately does not do

Named so scope creep has something to push against. Each item has an owner.

- **`PlatformProfile` adapters for Canvas, Moodle, D2L and Blackboard** —
  §7.3 names four, and E3 ships the seam plus the mock's profile. Ruled at
  breakdown, 2026-09-04. The cost is stated rather than hidden: the first real
  platform certification will find quirks the mock does not have, and will
  write its adapter then. Per-platform certification is already outside the v1
  count (§14.4).
- **Deep Linking** — post-v1 by the ruling of 2026-08-28 (§7.3), and E3 owns
  it only *if* a real platform demands it before then. No real platform is in
  scope for this epic, so nothing here builds it.
- **Any student-facing or instructor-facing explanation of the credit rule** —
  E8's results view and E4's report surfaces. The item denominator makes a
  blank optional comment cost real credit and nothing E3 ships says so to
  anybody; the score comment's ledger is the whole disclosure. This is carried
  forward explicitly by E3-08 rather than left to be discovered.
- **The job dashboard, the AGS call-log view, and the LTI health surface** —
  E11's, per §6.1. E3 writes the `ags_call` rows those views will read and
  renders none of them.
- **Window-rhythm and threshold configuration surfaces** — §6.3, E11,
  unchanged from E2.
- **An instructor override of a posted score** — §3.4 says the passback is
  fully automatic with no instructor action or override, so this is not
  deferred work but a stated non-feature. The LMS owns the column after a
  drop, which is the only place a human changes a Pulse-posted number.
- **Reconciling a line item a human renamed or deleted in the LMS beyond the
  re-find rule E3-04 settles** — the rule is scoped to not producing a second
  column; a repair surface for a section whose posts are failing is E11's.

## Notes on the decomposition

- **02 and 03 split the plumbing from the arithmetic.** The formula is the
  only part of this epic where a wrong answer is invisible — a schema mistake
  fails a migration and a client mistake fails a call, while a denominator
  mistake posts a plausible number. It gets its own ticket, its own reviewer
  pass, and the Hypothesis properties §9.1 names, with no network anywhere in
  the diff.
- **04 merges the client with the mock's enforcement on purpose.** ADR 0099
  records that E1-06 promised AGS enforcement would pair with E1-11's client,
  and E1-11 shipped the client without it. A promise in a ticket did not hold;
  one ticket makes the pairing structural. If the diff proves too large to
  review as one, the enforcement half is re-scheduled as an explicit
  dependency of E3-06 so that the build order, and not a sentence, carries the
  deadline.
- **05 before 06 is not a preference.** Posting to a line item that does not
  exist is the failure mode the ordering removes, and it is worth having the
  creation path tested on its own before the job depends on it.
- **07 exists because the epic is otherwise not drivable.** The beat fires on
  real time while the formula counts weeks off the development clock (ADR
  0109), so without a trigger there is no way to see a passback happen in a
  browser — exactly the gap E2-04 and E2-13 hit with survey windows. It also
  carries the CSRF sweep, whose red case needs a mutating route to be honest
  about, and the development trigger is the epic's first one.
- **Every ticket that touches the seed or the mock stays behind the
  development-environment guard** (ADR 0063, 0064), unchanged from E2.
- **§14.3's E3 entry is corrected in this same pull request.** It still
  describes the formula as valid weeks ÷ elapsed weeks, which the ruling of
  2026-09-04 supersedes; correcting the spec beside the breakdown is what
  stops a record going on asserting something the change made false
  (`docs/MISTAKES.md` entry 1).
