# E5 — Benchmarks & comparison sets: build order

Fourteen tickets decomposing SPEC §14.3's E5 entry. Each is sized for a single
focused session and leaves the repository in a working state: CI green, Compose
stack healthy, nothing half-wired at a boundary. E5 is **not** a ⚠ epic and its
entry marks no path for line-by-line human review, but the epic's substance is
comparison figures — the exact class §4.1 item 7 exists to police — so the
suppression chokepoint E4 built (`comparison_after_suppression` in
`app.services.reporting`) is load-bearing in every backend ticket here. Every
ticket gets the independent per-PR security review, and two lanes govern how
tickets are built (`.claude/heavy-lane-paths.md` is the authority; the header
decides, a missing field means heavy).

Say **"build E5, ticket 4"** and it means E5-04.

Branch names follow `CONTRIBUTING.md`: cut `e5/<slug>` from
`epic/e5-benchmarks-comparison-sets`, one ticket per branch, one pull request
into the epic branch.

**Read before building anything here:** `docs/tickets/e5/carried-from-e4.md`
(every entry — this breakdown schedules the E5-owned one, and the mapping is
below), SPEC §2.2, §4.1, §5.1 (the whole comparison-sets paragraph), §8 (the
level bands), §13, §14.3, and `docs/MISTAKES.md` whole. UI tickets additionally
read `docs/DESIGN_BRIEF.md` and `design/tokens.css` before any component is
written.

Items an E5 ticket defers rather than fixes live in `deferred.md` (created by
the first PR that needs it); a PR that defers something adds it there in the
same PR, and E5-14 runs the cleanup pass over the file.

**Lanes in this breakdown:** four tickets are light — E5-07, E5-08, E5-09 and
E5-10, the frontend work, the same shape E4's light set had (E4-08 through
E4-11 are the precedent, and the component-test runner they needed already
exists since E4-16). Everything else is heavy, for structural reasons: the
epic's substance is read views (`backend/app/views_sql/`), a new service, a
new model, routes, and a seed script, and every one of those sits in a named
heavy row or under `backend/app/`'s fail-closed default. One lane call named
out loud: E5-12 touches `mock-lms/` and `scripts/`, both named heavy rows,
so seed work is heavy even though it ships no production behavior.

## Decisions ruled at breakdown

Ten decisions settled before the first ticket branch, recorded here so no
ticket re-litigates them. None changes what the product does — SPEC §5.1 and
§4.1 already say what a benchmark shows and hides — so none carries a spec
edit. Each is a construction decision the spec does not make; the contestable
ones get their ADR in the ticket that builds them, and the rest are defaults a
ticket may depart from only by saying so.

1. **Benchmark figures are computed at read time; only named sets are
   stored.** SPEC §8 settles the storage half ("the default per section …
   is computed, not stored"), and read-time computation extends E4's decision
   1 to the comparison views: a benchmark is a view over responses that
   already exist, keyed by length, level, term and week, carrying no identity
   column. If the E13 load test finds these views slow at 500 sections,
   materializing is the recorded fallback; it is not built now.
2. **Every comparison figure crosses the wire through
   `comparison_after_suppression`, under both configured minimums.** E4's
   decision 4 built the chokepoint precisely so E5 could not route around it;
   this breakdown honors it. Two halves stated out loud because each is a
   recorded mistake shape: the helper enforces `benchmark_min_sections_default`
   **and** `benchmark_min_respondents_default` (a guard built against one of
   two thresholds is the closed-set defeat), and the respondent minimum counts
   **distinct students**, never responses or answers — a threshold that
   protects people is crossed by a count of people (`docs/MISTAKES.md` entry
   50). The university-wide line is a figure computed from a comparison set in
   item 7's sense and is subject to the same minimums; E5-04's ADR records
   that reading and its alternative.
3. **A named set is a stored list of member courses plus one declared
   length+level pair.** Level derives from the course number (§8) and length
   from the section code (§2.2), so "invalid combinations impossible" means
   the set declares its length and level once, membership is constrained to
   courses of that level, and resolution selects member courses' sections of
   that length. The alternatives (section-level membership, which ages out
   every term under past-referencing; filter-defined sets, which cannot name
   a deliberate cohort) are recorded in E5-01's ADR.
4. **E5 ships named-set management and resolution; nothing in E5 attaches a
   named set to a viewing context.** The instructor report uses the default
   set only. The spec puts cohort selection on the aggregate pages (§2.2),
   which are E9's roll-ups, so the surface that lets a viewer choose a named
   set is E9's. The cost, named: until E9, a named set can be created,
   edited and resolved but no report renders it — the management UI and the
   resolution service are proven by their own tests and by the set preview's
   two counts (member courses and resolved sections) in E5-06/E5-09.
5. **The hero section is excluded from its own comparison-set line;
   the university line includes every matching section.** A section compared
   against a set containing itself dampens exactly the divergence the chart
   exists to show, and in a thin set the effect is largest. The university
   line is a population figure and keeps the whole population. E5-04's ADR
   records the alternative (include self everywhere, simpler and defensible).
6. **Past-referencing reaches every term retention still holds.** §5.1 says
   "current and prior terms" without a cap, and §4's retention rule already
   bounds what exists to compute over; inventing a second horizon would be a
   silent policy. E5-04's ADR states this beside decision 5's reasoning.
7. **Cohort-mode term-axis aggregates land as views and service reads, with
   no E5 surface rendering them.** §2.2's aggregate pages — one line per
   start cohort with a cohort selector — are E9's dashboards. E5 builds the
   computation (E5-03's term-axis views, E5-04's reads) and proves it by
   test, so E9 consumes a proven read rather than building one inside a ⚠
   epic. The cost, named: term-axis output is test-proven only until E9
   draws it.
   **Amended at the exit (E5-14):** only half of this landed. The term-axis
   views exist, and `named_set_term_axis` reads `benchmark_cohort_term_axis`,
   but nothing calls it, and the rating term axis
   (`benchmark_cohort_rating_term_axis`) has no service read at all. E9 owns
   that read, together with the three cohort views nothing reads
   (`../e6/carried-from-e5.md`).
8. **The report payload contract for benchmarks is sketched in this file and
   frozen enough to build against.** The frontend tickets (E5-07 through
   E5-10) build against fixtures shaped like the sketch below and never wait
   on the backend; E5-05's Pydantic schema is the authority the moment it
   merges, and any divergence is resolved in E5-10, the ticket that joins the
   two. E4's decision 5 is the precedent, and its one lesson is inherited:
   reconciliation is a named job, not a surprise.
9. **The exit's "two lines" waits on E8 if E8 has not landed.** The only
   student trend surface in the spec is TrendDuo on the student results view
   (§7.6, §5.4), which is E8's. E5's provable half is therefore structural:
   the student schemas admit no benchmark member, the student routes carry
   none, and the student surfaces that exist render no benchmark trace —
   E5-11, with positive controls. If E8's view has merged by the exit
   (E5–E8 interleave, §14.4), E5-14 walks it and shows the two lines
   literally; if not, the exit records the structural proof and names the
   literal walk as the first E8 obligation. The alternative — E5 building a
   throwaway student chart to satisfy the sentence — is scope nobody asked
   for.
10. **§11 question 1 is settled at the exit, by the owner, on evidence.** The
   whole mechanism runs on the existing configuration defaults
   (`benchmark_min_sections_default` = 3, `benchmark_min_respondents_default`
   = 15 — `backend/app/config.py` has carried them since E0) so that
   answering §11 stays a configuration change. E5-14 presents the real cohort
   sizes the seeded worlds produce, records the ruling, and updates SPEC §11
   and §5.1 in the same PR. No ticket before E5-14 treats the defaults as
   settled.
   **Settled 2026-09-22 (E5-14):** 3 sections and 10 distinct respondents,
   both still configuration. SPEC §11 question 1 and §5.1 record it, and
   `backend/app/config.py` and `.env.example` default to 10.

## Build order

| # | Ticket | Branch | Lane | Depends on | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [The comparison-set schema](E5-01-comparison-set-schema.md) | `e5/comparison-set-schema` | heavy | none | The `comparison_set` model (decision 3): named sets as member courses plus one declared length+level pair, constraints making invalid combinations unstorable, migration; grants follow their spenders (E5-04, E5-06). | #225 as 35bddd8, 2026-09-13 |
| 02 | [The report payload carries the question texts and the close instant](E5-02-report-payload-questions-close.md) | `e5/report-payload-questions-close` | heavy | none | The carried E4-21 follow-up: the payload gains the two served question texts and the week's window-close instant; the histogram titles quote the questions and the eyebrow renders its close note, proven against the mockup. | #228 as b2b1e8a, 2026-09-14 |
| 03 | [The benchmark read views](E5-03-benchmark-read-views.md) | `e5/benchmark-read-views` | heavy | none | Identity-free views for cohort figures: per length+level+term+week rating means, workload statistics, distinct-respondent counts and section counts, on both the course-week and term axes (decision 7). | #226 as d5a73b6, 2026-09-13 |
| 04 | [The benchmark resolution service](E5-04-benchmark-service.md) | `e5/benchmark-service` | heavy | 01, 03 | `services/benchmarks.py`: default-set resolution (same lead's courses, matched length+level), past-referencing week alignment, the university cohort, named-set resolution, and every figure sealed by `comparison_after_suppression` under both minimums (decision 2). | #229 as 5b9ef5c, 2026-09-14 |
| 05 | [The report serves three lines per panel](E5-05-report-benchmark-lines.md) | `e5/report-benchmark-lines` | heavy | 02, 04 | `schemas/report.py` and `api/instructor.py`: per-stream comparison and university trend series plus workload comparison figures, all through the chokepoint; §4.1 item 7's invariant re-proven with real figures on both sides of each minimum. | #237 as b166ca4, 2026-09-14 |
| 06 | [The named-set management API](E5-06-named-set-api.md) | `e5/named-set-api` | heavy | 01 | `api/leadership.py`: create, edit, delete and list named sets at leadership scope, with the set-preview read (member count, resolved section count) the UI renders. | #238 as 28a489f, 2026-09-14 |
| 07 | [The TrendPair overlays](E5-07-trend-overlays.md) | `e5/trend-overlays` | light | none | PulseTrendChart and TrendPair gain the comparison and university series against fixture data: three lines per panel, one legend, suppressed-line states, distinguishable without color alone. | #224 as 6c68748, 2026-09-13 |
| 08 | [The workload comparison stats](E5-08-workload-comparison-stats.md) | `e5/workload-comparison-stats` | light | none | StatPair grows the §5.1 comparison columns against fixture data: section beside comparison-set beside university, mean and median, each column independently suppressible. | #227 as df85e37, 2026-09-14 |
| 09 | [The named-set management UI](E5-09-named-set-ui.md) | `e5/named-set-ui` | light | 06 (merge order only) | The leadership route: list, create, edit, delete; the form offers only valid choices (decision 3) so an invalid length/level combination cannot be expressed, not merely erroring. | #236 as 661462d, 2026-09-14 |
| 10 | [The report page joins the benchmark payload](E5-10-report-benchmark-join.md) | `e5/report-benchmark-join` | light | 05, 07, 08 | InstructorMondayReport wires E5-05's real payload into the overlay and stat components, reconciles fixtures with the shipped schema (decision 8), and extends the in-slice e2e. | #240 as bfa5f61, 2026-09-14 |
| 11 | [Students never see a benchmark, asserted](E5-11-student-benchmark-exclusion.md) | `e5/student-benchmark-exclusion` | heavy | 05 | §4.1 item 1 grows its benchmark-era teeth: the student payload structurally carries no comparison member, student routes are swept, and the exclusion is proven non-vacuous — the same world that shows an instructor three lines shows every student surface clean (decision 9 governs the literal two-line walk). | #239 as 31c076c, 2026-09-14 |
| 12 | [The prior-term benchmark world](E5-12-prior-term-world.md) | `e5/prior-term-world` | heavy | none | Mock-LMS sections in one or more prior terms with seeded responses, so past-referencing has real data behind it: cohorts thick enough to pass both minimums and one deliberately thin cohort that must suppress. | #230 as d252db6, 2026-09-14 |
| 13 | [The copy inventory grows over the benchmark surfaces](E5-13-benchmark-copy-inventory.md) | `e5/benchmark-copy-inventory` | heavy | 09, 10 | §4.1 items 4 and 5 over everything E5 ships: legends, suppression notices, set-management copy — comparison language that counts sections and never ranks. | #242 as d1eaeff, 2026-09-22 |
| 14 | [E5 exit](E5-14-e5-exit.md) | `e5/e5-exit` | heavy | all | §14.3's exit clause driven against the running stack: three lines per panel benchmarked against prior terms, a student provably seeing two; §11 question 1 settled and recorded (decision 10); boundary reviews; `../e6/carried-from-e5.md`. | #249 |

**Not a ticket, and merged all the same:** `e5/seed-hero-lead`, #241 as
fae58fa, 2026-09-14. Found while driving E5-10's e2e: `scripts/seed.py` gave
`BIOL 310` no lead, so the hero section's default comparison set resolved
empty however many prior-term sections were filled. It seeds `BIOL 215` and
`BIOL 310` and maps a lead to `BIOL 310` only (`docs/MISTAKES.md` entry 58).
It merged before E5-10 and E5-11.

## Dependency graph

```
01 ─┬─ 04 ── 05 ─┬─ 10 ── 13 ── 14
03 ─┘    ┌───────┤              │
02 ──────┘  07 ──┤              │
            08 ──┘              │
01 ── 06 ── 09 ────── 13        │
05 ── 11 ──────────────────────┤
12 ──────────────────────────── 14
```

(04 needs 01 and 03. 05 needs 04, and needs 02 first because both tickets
edit `schemas/report.py` and `api/instructor.py` — a file-partition edge as
much as a contract one. 07 and 08 build day one against the sketch and feed
10, where the join happens. 09 builds day one against fixtures and merges
after 06. 11 needs 05's payload to prove exclusion non-vacuously. 12 feeds
nothing in code — its edge into 14 is the exit drive's data. 13 reads the
strings 09 and 10 ship.)

**Seven tickets cut on day one:** 01, 02, 03, 07, 08, 09 and 12 — three
heavy backend starts, three light frontend starts against fixtures, and the
seed world beside them. The standing rules for parallel builds govern:
partition sequential identifiers up front, no two tickets touching the same
file, migration chains re-pointed at merge. The migration-adding tickets are
**01 and 03**; they take chain slots in that order off head `e5a2b81c47d3`,
and whichever merges later re-points, as E4 did. ADR numbers are assigned
per wave at cut time, next free **0164**; two branches proposing the same
number is a conflict to resolve, never a number to share. MISTAKES next
entry is **54**.

## The payload sketch the frontend builds against

Frozen enough to build fixtures from; E5-05's Pydantic schema is the authority
once it merges (decision 8), and E5-02's schema is the authority for the
question-text and close-instant members. Additions to E4's report payload —
everything E4 shipped is unchanged:

```json
{
  "week": {"course_week": 4, "term_week": 7, "closes_at": "2026-10-18T23:59:00-04:00"},
  "streams": {
    "instructor": {
      "question_text": "My instructor supported my learning",
      "benchmark": {
        "comparison": {"suppressed": false, "reason": null,
                       "points": [{"course_week": 1, "mean": 3.9}]},
        "university": {"suppressed": true, "reason": "below-minimum", "points": []}
      }
    },
    "course": {"…": "same shape"}
  },
  "workload_benchmark": {
    "comparison": {"suppressed": false, "mean": 8.9, "median": 8.0},
    "university": {"suppressed": false, "mean": 9.1, "median": 8.5}
  }
}
```

Three rules the sketch carries on purpose. A suppressed member says
`suppressed` and a one-word reason and **nothing else** — no counts, no
points, no set size, because "2 sections" under a suppression is itself the
inference item 7 exists to prevent. Every benchmark member at every depth is
produced by the chokepoint, never assembled in a route. And the student
payload gains **none of this** — not a suppressed member, not an empty one;
the members are structurally absent from the student schema, which is what
E5-11 asserts.

## Exit criterion → the tickets that prove it

§14.3 E5's exit line — an instructor sees three lines per panel benchmarked
against prior terms; a student provably sees two lines and no benchmarks —
and E5-14 drives it against the running stack.

| Piece of the exit | Rests on |
|---|---|
| three lines per panel in both TrendPair panels | 03, 04, 05, 07, 10 |
| the lines reach into prior terms (past-referencing) | 04, 12 |
| workload figures sit beside comparison and university figures | 03, 04, 05, 08, 10 |
| a thin cohort suppresses every figure, line and statistic alike | 04, 05, 12 |
| a student sees two lines and no benchmark anywhere | 11 |
| a named set with an invalid combination cannot be created | 01, 06, 09 |
| the min-N values are settled, not defaulted | 14 |

## Where the carried work landed

`carried-from-e4.md` names exactly one E5-owned entry, and this breakdown
schedules it:

| Item | Lands in |
|---|---|
| The two report-payload fields the design mockup needs (question texts, close instant) | E5-02 |

Everything else in `carried-from-e4.md` — the moderation and §6.2 family
(E6), the summary-prompt block boundaries (E7's first candidate), the
landing strings (E9), the serial summary walk and the load budget (E13), the
reveal door's harm-class narrowing (E6), the aggregate-ordering gate (E9),
the refused-summary observability (E11), `PERSON_TABLES` (every boundary,
E13 at the latest), the TypeScript 7 pair, the session-read sweep's limits,
the denial-inventory class, the summary eval floor (E10 at the latest), and
the whole carried-through-unchanged ledger — is owned by later epics or by
paths E5 does not touch, and passes through to `../e6/carried-from-e5.md`
at E5-14 under the same completeness rule E4 used. Two get re-checked at
exit rather than merely re-listed: the session-read sweep (does it reach
`services/benchmarks.py` and `api/leadership.py`) and `PERSON_TABLES`
(asked of the table E5-01 adds).

## What E5 deliberately does not do

Named so scope creep has something to push against. Each item has an owner.

- **Roll-up dashboards, cohort selectors, and any surface that renders the
  term axis** — E9. E5 proves the term-axis reads by test (decision 7).
- **Attaching a named set to a report or dashboard** — E9 (decision 4). E5
  manages and resolves sets; nothing selects one for viewing yet.
- **The min-N configuration surface** — E11's console (§6.3). E5 reads the
  configuration values; nobody edits them in a UI yet.
- **Purview over the full supervision DAG** — E9. E5-06 scopes a set's writes
  to the leader who defined it and leaves reads open to every leadership
  session (ADR 0173); it computes no purview.
- **The student results view** — E8. E5-11 asserts the student's existing
  surfaces; it builds no new one.
- **Benchmark performance work** — E13's load test (decision 1 names
  materialization as the recorded fallback).

## Notes on the decomposition

- **01, 03 and 04 split the schema, the arithmetic and the policy.** The
  views expose cohort numbers with no thresholds applied; the service is the
  only place minimums, self-exclusion and past-referencing live. A reviewer
  of 04 reads policy against §5.1's paragraph; a reviewer of 03 reads SQL
  against the identity-separation rules. The alternative — views that
  pre-apply suppression — hides the policy in SQL where the chokepoint
  cannot see it and item 7's invariant cannot plant both sides.
- **05 is the only ticket that touches the report schema for benchmarks,
  and it follows 02 by construction** — the two tickets that edit
  `schemas/report.py` are ordered rather than partitioned, because a
  same-file merge of two schema diffs is the conflict class the parallel
  rules exist to avoid.
- **07, 08 and 09 are three tickets, not one frontend batch.** Three
  builders run against the sketch without touching the same files: 07 owns
  the trend components, 08 the stat components, 09 a new leadership route.
  10 is the one place the report pieces join, E4-11's pattern exactly.
- **11 is heavy and separate, not a criterion inside 05.** Item 1's
  benchmark-era assertion is a student-facing confidentiality guarantee —
  the exit's "provably" — and it belongs to the invariant suite with a
  positive control (the same world shows an instructor three lines), not to
  a backend ticket's test list where emptiness could satisfy it.
- **12 exists so the exit does not seed under pressure.** E4-20's lesson:
  representative data is its own deliverable. The prior-term world also
  gives 14's §11 evidence real cohort sizes to point at, and its thin
  cohort is the standing proof that suppression fires outside a unit test.
- **Every ticket that touches the seed or a mock stays behind the
  development-environment guard** (ADR 0063, 0064), unchanged from E4.
