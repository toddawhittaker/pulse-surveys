# E4 — Instructor Monday report: build order

Nineteen tickets decomposing SPEC §14.3's E4 entry. Each is sized for a single
focused session and leaves the repository in a working state: CI green,
Compose stack healthy, nothing half-wired at a boundary. E4 is **not** a ⚠
epic, but its entry marks one path for line-by-line human review anyway: the
small-N suppression queries (E4-04, and the release machinery it builds).
Every ticket still gets the independent per-PR security review, and two lanes
still govern how tickets are built (`.claude/heavy-lane-paths.md` is the
authority; the header decides, a missing field means heavy).

Say **"build E4, ticket 8"** and it means E4-08.

Branch names follow `CONTRIBUTING.md`: cut `e4/<slug>` from
`epic/e4-instructor-monday-report`, one ticket per branch, one pull request
into the epic branch.

**Read before building anything here:** `docs/tickets/e4/carried-from-e3.md`
(every entry — this breakdown schedules the E4-owned ones, and the mapping is
below), SPEC §2.2, §3.1–§3.3, §4, §4.1, §5.1, §5.2, §7.4, §7.6, §14.3, and
`docs/MISTAKES.md` whole. UI tickets additionally read `docs/DESIGN_BRIEF.md`
and `design/tokens.css` before any component is written.

Items an E4 ticket defers rather than fixes live in `deferred.md` (created by
the first PR that needs it); a PR that defers something adds it there in the
same PR, and E4-15 runs the cleanup pass over the file.

**Lanes in this breakdown:** four tickets are light — E4-08, E4-09, E4-10 and
E4-11, the frontend work. Light lanes have precedent (E1-02, E1-03, E1-07 and
E2-10 all rode light), and E2-10 — the student survey form — is the direct
frontend precedent whose deferrals this breakdown inherits: the week-eyebrow
entry and the frontend-runner entry both trace to it. Everything else is
heavy, and the reasons are structural rather than cautious:
the epic's substance is read paths (`backend/app/views_sql/`), services,
routes, jobs, a migration chain and an AI task, and every one of those sits in
a named heavy row or under `backend/app/`'s fail-closed default. Two lane
calls worth naming out loud. `backend/app/ai/` matches no row and is under
`backend/app/`, so the fail-closed rule makes E4-05 heavy. And E4-13, which
E3's own record predicted would be a light ticket, is heavy after all: the
lane table makes *any path matching `*care*`* heavy wherever it lives, and
`frontend/src/routes/care/` matches it literally. Doubt means heavy; the
ticket is one docstring, so the cost is small.

**Reviewer addition declared at breakdown:** **`prompt-eval` runs per-PR on
E4-05**, the ticket that adds the epic's model task and settles the floor
question — a floor decision that waited for the boundary pass would be
exactly the deferral the reviewer exists to catch. Named honestly: this is
not `review-pr`'s own exception, whose condition is an epic whose *declared
subject* is the moved reviewer's specialty — E4's subject is the report, and
one ticket touches `backend/app/ai/`. It is a breakdown decision to run
*more* review than the skill's default on one PR, which the skill's
gate-weakening rules do not restrict. The other boundary-only reviewers stay
at the boundary (E4-15).

## Decisions ruled at breakdown

Ten decisions settled before the first ticket branch, recorded here so no
ticket re-litigates them. None changes what the product does — SPEC §5.1 and
§4 already say what the report shows and hides — so none carries a spec edit.
Each is a construction decision the spec does not make; the contestable ones
get their ADR in the ticket that builds them, and the rest are defaults a
ticket may depart from only by saying so.

1. **Aggregates are computed at read time in identity-separated views;
   nothing aggregate is stored.** Distributions, workload mean and median,
   response rate and validity rate are views over tables E2 shipped, in
   `backend/app/views_sql/`, keyed by section and course week and carrying no
   identity column. The boring alternative — a materialized report row written
   at window close — buys freshness problems (a late reclassification changes
   validity rate) and a second writer for no measured cost. If the E13 load
   test finds these views slow at 500 sections, materializing is the recorded
   fallback; it is not built now.
2. **AI summaries are stored, one row per section, course week and stream,
   generated once by the Monday job at window close.** They are the epic's
   only generated artifact: a summary is a model output with a prompt version
   and model id, not a recomputable number, so it is written down. There is no
   regeneration in v1 — a later reclassification or a cumulative release does
   not rewrite an already-generated summary, because under-threshold comments
   already fed it at generation time (§5.1) and a summary that silently
   changes under a reader is worse than one that is a week honest. E4-06
   records this in its ADR.
3. **The moderation-status column lands in E4's schema, with exactly one
   value ever written during E4.** §5.1 says comments carry their moderation
   status and §5.2's small-N concealment must hide flags, so E4's suppression
   queries are built and proven against the real column — a planted flagged
   row, concealed below threshold — rather than against a column that arrives
   with E6. E6 writes the lifecycle; E4 writes only the initial state. The
   alternative (defer the column, assert concealment vacuously) makes the ⚠
   queries untestable in exactly the epic that must prove them. ADR in E4-02.
4. **§4.1 item 7 is asserted here as a chokepoint, and E5 flows through it.**
   E4 builds no comparison set — that is E5 — but the report payload carries
   the comparison fields from day one, populated only through one suppression
   helper that enforces **both** configured minimums —
   `benchmark_min_sections_default` and `benchmark_min_respondents_default`
   (`backend/app/config.py`, both already exist; §11 question 1 names the
   pair) — because a guard built against one of two thresholds is the
   closed-set defeat `docs/MISTAKES.md` records: E5 routes a mean over three
   sections and four respondents through it and ships a figure §5.1 means to
   suppress. The invariant test plants figures on both sides of each minimum
   and proves suppression *and* passage at the payload boundary — the
   positive control is what makes the absence mean suppression rather than
   emptiness. E5's benchmarks route through the same helper or their own
   invariant fails. This is what "asserted from E4" can honestly mean in an
   epic with no benchmark data: the rule is enforced where the figures will
   pass, not vacuously claimed. E4-07 owns it.
5. **The report payload contract is sketched in this file and frozen enough
   to build against.** The frontend tickets (E4-08 through E4-11) build
   against fixtures shaped like the sketch below and never wait on the
   backend; E4-07's Pydantic schema is the authority the moment it merges,
   and any divergence is resolved in E4-11, the ticket that joins the two.
6. **A published week is a course week whose survey window has closed**, per
   the clock service — the same currency E3's decision 6 used. Week
   navigation lists exactly those weeks. Nothing is stored to make a week
   published.
7. **The cumulative release is a stored batch, not a computed threshold
   crossing.** §4 requires under-threshold comments to surface "batched so
   that timing cannot identify an author"; a release computed at read time
   re-derives differently as data changes and leaks through its own timing.
   E4-02 stores the batch state, E4-04 builds the crossing-and-release logic
   and its ADR, and timestamps are never exposed anywhere in the path.
8. **The reveal-subject guard takes its subject from the record Care is acting
   on.** The carried done-when offers "or an equivalent guard"; the
   record-derived subject is the shape that removes the caller-supplied id
   entirely rather than validating it, and E4-01 settled the details in
   [ADR 0144](../../adr/0144-the-reveal-derives-its-subject-from-the-record-care-is-acting-on.md).
   The record is a **comment**, not a Care case: there is no case model until
   E10, so the reveal names one comment and derives its author, and E10's case
   model wraps that without another signature change. It merges
   before E4-11, the epic's first instructor-facing surface — the inherited
   deadline, enforced by build order rather than by a sentence.
9. **E4 takes two candidate tickets no epic owned:** the stale Care-landing
   docstring (E4-13), and the launch nonce purge's missing `SELECT` grant
   (E4-14 — taken because the carried entry's owner is whichever epic next
   touches the runtime grants, and E4-02 does). The week eyebrow's
   course-length entry is deliberately **not** taken: its done-when puts the
   wire half on a heavy path (`app.services.survey_read` and a schema field),
   and its FIX-01 note says the rendering half now waits on an owner ruling
   about where the total sits in the ruled `COURSE WK NN, TERM WK NN` string.
   It passes through with that fact; the ruling would let a later ticket take
   it whole. **Superseded in part, 2026-09-07:** the ruling arrived. The
   payload gains the course length, the eyebrow renders the brief's "/ N" form
   on the course-week half with the term-week label unchanged, and frontend
   derivation is rejected. The entry is taken after all, as **E4-17** — a
   heavy ticket, as this decision predicted its wire half would be.
10. **The frontend test runner lands as E4-16, first.** E2 deliberately
   deferred a frontend unit-test runner, with the revisit trigger "when a
   screen's logic outgrows what the end-to-end suite pins cheaply" — and E4's
   four component tickets are that moment: their acceptance criteria are
   component tests, and a repository with no runner cannot execute them. The
   runner is heavy work (root `package.json`, and a CI gate in
   `.github/workflows/`), so it gets its own small ticket rather than
   arriving inside a light diff as an undeclared dependency choice. E4-08,
   E4-09 and E4-10 may cut and build on day one, but their PRs merge after
   E4-16's.
11. **The client learns its sections from a route, not from the launch
   door.** Found starting E4-11, ruled 2026-09-07: every E4-07 route takes a
   `section_id`, and nothing the client holds supplies one — the launch
   redirect carries only the role and the session. The fix is the student
   pattern (`GET /student/survey` takes no parameter and answers the
   reader's own sections) applied to the instructor surface: a third route
   in `app.api.instructor` listing the session's own taught sections, as
   **E4-18**, which E4-11 now depends on. The rejected alternative — the
   door forwarding its launch context's section — would serve only the
   launched course, give the web door nothing, and widen the doors' surface;
   the ADR in E4-18's pull request records it.
12. **The trend's term-week sub-label comes from the wire, and the client
   derives nothing.** Found while E4-11 reconciled the component contracts
   with the shipped schema (decision 5 makes E4-11 the reconciliation
   point), ruled 2026-09-07: §2.2 puts both axes on the chart,
   `PulseTrendChart` takes both numbers per point, and E4-07's `TrendPoint`
   carried only the course week — so the point gains `term_week`, populated
   from the window rows the report read already holds, as **E4-19**, which
   E4-11 now also depends on. The rejected alternative — the page deriving
   the term week from the report week's own pair as an offset — matches
   today's backend arithmetic exactly and was rejected anyway, for the
   reason E4-08's copy file already records: a section pausing over a break
   week makes a derived number disagree with the report. The ADR in E4-19's
   pull request records it.

## Build order

| # | Ticket | Branch | Lane | Depends on | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [The reveal refuses a subject reached through a reporting scope](E4-01-reveal-subject-guard.md) | `e4/reveal-subject-guard` | heavy | none | The inherited deadline: `reveal_identity` takes its subject from the comment Care is acting on rather than from its caller (ADR 0144 — there is no case model until E10), and the two-hat composition is refused, before any instructor surface ships. | #186 as 472f5c5, 2026-09-06 |
| 02 | [The report schema](E4-02-report-schema.md) | `e4/report-schema` | heavy | none | Everything the epic writes, before anything writes it: the summary table, the moderation-status column, the release-batch state, and their grants. | #188 as 2d0d38e, 2026-09-06 |
| 03 | [The aggregate read views](E4-03-aggregate-read-views.md) | `e4/aggregate-read-views` | heavy | none | Distributions, workload mean and median, response rate and validity rate as identity-separated views over E2's tables, per section and course week. | #189 as a21e62c, 2026-09-06 |
| 04 | [Comment visibility under small-N](E4-04-comment-visibility.md) | `e4/comment-visibility` | heavy ⚠ | 02 | The suppression heart: below-threshold hiding, the cumulative batched release, flag concealment, randomized order, no timestamps. Line-by-line human review. | #194 as 8f76790, 2026-09-07 |
| 05 | [The weekly summary task](E4-05-weekly-summary-task.md) | `e4/weekly-summary-task` | heavy | none | The gateway's third task under §5.1's contracts: prompt, typed contract, eval cases, and the floors question settled with the gate that enforces it. | #187 as 41250d4, 2026-09-06 |
| 06 | [The summary generation job](E4-06-summary-generation-job.md) | `e4/summary-generation-job` | heavy | 02, 05 | The Monday beat entry: per section, per closed week, per stream, generate once and store, small-N weeks included. | #195 as 790b0ee, 2026-09-07 |
| 07 | [The report API](E4-07-report-api.md) | `e4/report-api` | heavy | 02, 03, 04 | `api/instructor.py`: the report payload, the published-week list, and §4.1 item 7's chokepoint and invariant assertion. | #206 as a516ad1, 2026-09-07 |
| 08 | [The trend components](E4-08-trend-components.md) | `e4/trend-components` | light | 16 (merge order only) | PulseTrendChart and TrendPair against fixture data: stacked pair, shared 1–5 scale, one legend, course-week axis with the term-week sub-label. | #193 as 51c07b3, 2026-09-07 |
| 09 | [The stat components](E4-09-stat-components.md) | `e4/stat-components` | light | 16 (merge order only) | RatingHistogram, StatPair and ResponseRateBar against fixture data: this-week distributions, workload mean and median, response and validity rates. | #192 as e78f276, 2026-09-07 |
| 10 | [The comment components](E4-10-comment-components.md) | `e4/comment-components` | light | 16 (merge order only) | CommentCard, AiPanel and the instructor SmallNNotice against fixture data: grouped lists led by their summaries, empty-group notice, status chips. | #191 as 666133d, 2026-09-07 |
| 11 | [The report page](E4-11-report-page.md) | `e4/report-page` | light | 01, 07, 08, 09, 10, 18, 19 | InstructorMondayReport assembled: route, data fetch, week navigation, loading and error and small-N states, and the in-slice e2e path. | #209 as 97bee1f, 2026-09-08 |
| 12 | [The report's copy, and the inventory grows over it](E4-12-report-copy-and-inventory.md) | `e4/report-copy-and-inventory` | heavy | 08, 09, 10, 11 | Aggregate-language growth over the report surface, the two gradebook strings, the credit-rule instructor half, the string convention, and the collector's symlink gap. | #210 as eaa9ab0, 2026-09-08 |
| 13 | [The Care landing docstring](E4-13-care-landing-docstring.md) | `e4/care-landing-docstring` | heavy | none | The carried one-liner: the stale docstring in `frontend/src/routes/care/` says what the landing actually is. | #190 as e3641b1, 2026-09-07 |
| 14 | [The nonce purge can run](E4-14-nonce-purge-grant.md) | `e4/nonce-purge-grant` | heavy | none | The carried grant defect: `pulse_app` gets what a `DELETE ... WHERE` needs, the purge is driven to completion, and the privilege record says why `SELECT` was withheld. | #185 as 22598ea, 2026-09-06 |
| 15 | [E4 exit](E4-15-e4-exit.md) | `e4/e4-exit` | heavy | all | §14.3's exit clause driven against a seeded diverging two-stream story; boundary reviews; the de-anonymization statement verified; `../e5/carried-from-e4.md`. | |
| 16 | [The frontend test runner](E4-16-frontend-test-runner.md) | `e4/frontend-test-runner` | heavy | none | The carried E2 deferral, whose revisit trigger this epic trips: a component-test runner, one proof test, and the CI gate that makes red mean stop. | #184 as 38bbdcc, 2026-09-06 |
| 17 | [The week eyebrow says how long the course runs](E4-17-eyebrow-course-length.md) | `e4/eyebrow-course-length` | heavy | none | The carried E2 entry, unblocked by the owner's ruling of 2026-09-07: `OpenSurvey` gains the section's week count, `survey_read` reads it off the section row, and the eyebrow renders `COURSE WK 04 / 12, TERM WK 07`. | #205 as 8360f3a, 2026-09-07 |
| 18 | [The instructor's section list](E4-18-instructor-section-list.md) | `e4/instructor-sections` | heavy | 07 | The contract gap found starting 11, ruled 2026-09-07 (decision 11): `GET /instructor/sections` answers the session's own taught sections — id, code, governed label — the student pattern applied to the instructor surface. | #207 as 932b231, 2026-09-08 |
| 19 | [The trend points carry both week axes](E4-19-trend-term-weeks.md) | `e4/trend-term-weeks` | heavy | 07 | The contract gap found reconciling 08 with 07's schema, ruled 2026-09-07 (decision 12): `TrendPoint` gains `term_week` so the chart's §2.2 sub-label has a wire source, populated from the window rows the report read already holds. | #208 as aface05, 2026-09-08 |

## Dependency graph

```
01 ──────────────────────────┐
02 ─┬─ 04 ─┬─ 07 ─┬─ 18 ─┐   │
03 ─┼──────┘      ├─ 19 ─┤   │
05 ─┴─ 06         ├──────┴── 11 ── 12 ── 15
16 ─┬─ 08 ────────┤
    ├─ 09 ────────┤
    └─ 10 ────────┘
13 ─────────────────────────────── (free-standing, any time)
14 ─────────────────────────────── (free-standing, any time)
17 ─────────────────────────────── (free-standing, any time)
```

(07 needs 02, 03 and 04; 06 needs 02 and 05 and feeds nothing but the data
E4-11 renders — the page tolerates an absent summary row, so 06 is not on
11's critical path, but 15's exit drive needs it. 01's edge into 11 is the
inherited deadline, not a code dependency. 16's edges into 08, 09 and 10 are
merge order only — they build in parallel and their PRs wait. 12 reads the
strings 08–11 ship. 18 needs 07 and feeds 11 — the section-discovery route
of decision 11, added 2026-09-07. 19 needs 07 and feeds 11 the same way —
the trend axis pair of decision 12, added 2026-09-07.)

**Ten tickets cut on day one:** 01, 02, 03, 05, 13, 14 and 16 are
free-standing, and 08, 09 and 10 build beside them against fixtures, merging
after 16. (17 joined later, when its owner ruling arrived; it is
free-standing too and may be cut whenever there is a session for it.) The standing rules for parallel builds govern: partition
sequential identifiers up front, no two tickets touching the same file,
migration chains re-pointed at merge. The migration-adding tickets are 02, 03,
14 and — found while building it, because its guard needs a third `SECURITY
DEFINER` function rather than a grant (ADR 0144) — **01**. They take chain slots
in that order off head `c4a8e51db9f3`, and whichever merges later re-points, as
E3-01 did. ADR numbers are assigned per wave at cut time, next free 0152 (0144–0147
went to the first wave's 01/02/03; 0148–0151 are assigned to 05/14/16) —
**E4-01 took 0144**, so two branches proposing 0145 is a conflict to resolve
rather than a number to share; MISTAKES next entry is 50.

## The payload sketch the frontend builds against

Frozen enough to build fixtures from; E4-07's Pydantic schema is the
authority once it merges (decision 5). **It has merged: read
`backend/app/schemas/report.py` where this sketch and the schema disagree.**
One report, one section, one course week:

```json
{
  "section": {"code": "R3WW", "course_label": "ITEC 400", "length_weeks": 12},
  "week": {"course_week": 4, "term_week": 7, "published_weeks": [1, 2, 3, 4]},
  "rates": {"response_rate": 0.62, "validity_rate": 0.91, "responses": 13, "enrolled": 21},
  "streams": {
    "instructor": {
      "trend": [{"course_week": 1, "term_week": 4, "mean": 4.1}],
      "distribution": {"1": 0, "2": 1, "3": 4, "4": 5, "5": 3},
      "summary": {"text": "…", "response_count": 13, "held_note": null},
      "comments": [{"text": "…", "status": "published"}]
    },
    "course": {"…": "same shape"}
  },
  "workload": {"mean": 9.5, "median": 8.0},
  "comparison": {"suppressed": true, "reason": "below-minimum"},
  "small_n": {"suppressed": false, "threshold": 5}
}
```

Two rules the sketch carries on purpose: comments have no timestamp field and
no author field at any depth, and the `comparison` member exists from day one
so item 7's chokepoint has a place to stand before E5 fills it.

Three deliberate divergences, in `backend/app/schemas/report.py` and listed in
E4-07's pull request: `rates` gains `valid_responses`, because E4-09's
components render the count beside the ratio; a top-level
`released_from_earlier_weeks` list carries the release ADR 0152 places in this
payload; and `section.course_label` is the governed label the student's own
page carries ("MATH 140 E1FF — College Algebra, Fall 2026", FIX-01 item 2)
rather than the bare `"ITEC 400"` sketched above.

## Exit criterion → the tickets that prove it

§14.3 E4's exit line — an instructor opens a real Monday report for a seeded
section with a diverging two-stream story — and E4-15 drives it against the
running stack.

| Piece of the exit | Rests on |
|---|---|
| the instructor lands on the report from an LTI launch | 07, 11 |
| a diverging two-stream story is visible in the stacked pair | 03, 06, 08, seed work in 15 |
| distributions, workload figures and both rates are right | 03, 09 |
| each comment group is led by its stream's summary | 06, 10, 11 |
| a small-N week shows the summary and no raw comments | 04, 06, 10, 11 |
| a section crossing the cumulative threshold releases batched comments | 02, 04 |
| week navigation pages across published weeks only | 07, 11 |
| no comparison figure appears anywhere (E5 has not run) | 07 |

## Where the carried work landed

Every E4-owned entry of `carried-from-e3.md`, with the ticket that schedules
it. The entries' own done-whens govern; the tickets point at them.

| Item | Lands in |
|---|---|
| The reveal-subject guard, with its before-any-instructor-surface deadline | E4-01, ordered before E4-11 |
| Comment de-anonymization by completion pattern — E4's written statement | E4-04 states it in its ADR; E4-15 verifies the statement against what shipped |
| The gradebook's two instructor-visible strings sit outside the copy inventory | E4-12 |
| The credit-rule explanation, instructor half | E4-12, scoped to what the report actually shows |
| The copy collector's symlinked-directory gap | E4-12 |
| The rendered student surface's string convention | E4-12 |
| The week eyebrow's course length | E4-17, once the owner's ruling of 2026-09-07 settled where the total sits in the eyebrow (decision 9 records the change) |
| The frontend unit-test runner (E2's deferral, revisit trigger now tripped) | E4-16 |
| The stale Care-landing docstring | E4-13 |
| The daily purge of the launch replay ledger cannot run | E4-14 |

Everything else in `carried-from-e3.md` — the roster token dial, the
`azp`/`aud` launch validation, the JWKS cache, the flaky fail-closed framing
test, `post_score`'s return, the provisioning docstring, the rehoming
proposal, the clock-route origin check, the runbook, `PERSON_TABLES`, the
TypeScript 7 wait, the session-read sweep's limits, the rewound-clock family,
the ruff target version and the denial-module collection floor — is owned by
later epics, by paths E4 does not touch, or by a ruling not yet made, and
passes through to
`../e5/carried-from-e4.md` at E4-15 under the same completeness rule E3 used.
Two get re-checked at exit rather than merely re-listed: the session-read
sweep (does it reach the new report modules) and `PERSON_TABLES` (asked of
the tables E4-02 adds).

## What E4 deliberately does not do

Named so scope creep has something to push against. Each item has an owner.

- **Comparison sets, benchmarks, named sets, the university line** — E5. E4
  ships the suppressed `comparison` member and the item-7 chokepoint with
  nothing flowing through it; E5 fills it. The cost: until E5, every report
  shows the section's own lines only, and the TrendPair renders one line per
  panel.
- **The moderation lifecycle** — E6. E4 ships the status column, the
  concealment reads, and CommentCard's flagged and excluded variants driven
  by fixtures; no E4 path writes any status but the initial one.
- **The instructor response editor, draft, and draft check** — E7. The report
  page ships without the response section entirely, not with a stub.
- **The student results view** — E8, including the student half of the
  credit-rule explanation.
- **Leadership drill-down into this report** — E9 renders it read-only inside
  its shell; nothing in E4 anticipates that shell.
- **Attention rules and roll-ups** — E9 (§5.6).
- **The Monday email** — E12. Report generation and its notification are
  different things, and only the first is E4's.
- **Report performance work** — E13's load test measures the read-time views
  (decision 1 names materialization as the recorded fallback).
- **Summary regeneration on reclassification or release** — ruled out for v1
  by decision 2; revisiting it is a spec question, not a ticket.

## Notes on the decomposition

- **02, 03 and 04 split the schema, the arithmetic and the suppression.**
  The suppression queries are the epic's ⚠ path and the one place a wrong
  answer harms a student rather than a number — a leaked under-threshold
  comment cannot be un-shown. They get their own ticket, the smallest
  reviewable diff, and line-by-line human review, with the aggregate views
  kept apart so a reviewer of 04 reads nothing but visibility logic.
- **05 and 06 split the task from the job** for E3's reason: the prompt and
  contract are where a wrong answer is invisible (a fluent summary that
  sands off criticism passes every shape check), so the task gets its own
  reviewer pass and its eval cases, while the job is plumbing on the
  already-proven publish shape.
- **08, 09 and 10 are three tickets, not one component library.** Three
  builders run in parallel against the same payload sketch without touching
  the same files; 11 is the one place they join. The alternative — one big
  frontend ticket — serializes the epic's only light-lane work behind itself.
- **07 before 11 is the contract, not the data.** The page needs the schema
  and the routes; it tolerates empty summary rows and a seeded week of zero
  responses, so nothing in 11 waits on 06.
- **The exit seed is 15's, not 03's or 06's.** The diverging two-stream story
  is exit machinery, and E3's precedent (the NURS prefix arriving in E3-08)
  held up well: seed work lands beside the drive that consumes it.
- **Every ticket that touches the seed or a mock stays behind the
  development-environment guard** (ADR 0063, 0064), unchanged from E3.
