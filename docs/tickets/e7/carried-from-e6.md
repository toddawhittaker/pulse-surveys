# Carried from E6 into E7

Things E6 decided or deferred that later work has to know, per SPEC §14.1: one
entry per thing, each with an owner and what it looks like to be finished. This
is a hand-off note, not a ticket; the next breakdown schedules the work, and an
entry here is what that breakdown has to have read first. Created by E6-07.
Entries point at the record that owns the detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e6/carried-from-e5.md` not closed inside E6, plus everything an E6 pull
request deferred to a later epic, plus everything the E6 boundary reviews found
and did not fix inside the epic, appears here.** E6 kept no `deferred.md`; its
tickets named their deferrals in their pull request bodies, and those are the
second source. The demonstration is the ledger at the end of this file: every
source entry is named with what happened to it, in the source file's own order.

The boundary reviews run after this file is written (`../e6/boundary-review.md`).
Whatever they find and do not fix is added here, under its own heading, by the
change that records the finding.

## How the sources were dispositioned

**Closed inside E6,** each closure recorded in its source file with the pull
request and the merge commit:

- E6-01 (#292, merged as fd08ef75): the `moderation_state` tie-break, the §6.2
  threat class, the reveal door's harm-class narrowing, a comment with no
  moderation verdict counting as published, the per-stream gate's generated
  property, and the summary gather's copy of the blank-comment class.
- E6-02 (#293, merged as e6b5a56c): the small-N prompt's premise and the stored
  summaries of streams now held, and the local `.env` benchmark minimum.
- E6-03 (#294, merged as f55774c2): the held-note type, and the
  de-anonymization statement for instructor views (ADR 0189).
- E6-04 (#295, merged as 9a400202): the two older accessibility patterns and the
  design mockups' per-stream notices.
- E6-05 (#296, merged as 233d3739): the de-anonymization statement for
  leadership views (ADR 0190).
- E5.1-10 (#269, merged as 413905a): the submit budget measured on one sample,
  which the E5 ledger carried to E6 and E5.1 had already closed.

**Carried through unchanged**, under the owner and done-when of the source
entry: everything `../e6/carried-from-e5.md` passed through from its own
sources except the four E6 pass-throughs closed above, so the forged summary
block boundaries (E7's draft work first), the landing views' sentences (E9),
the serial summary walk (E13), the aggregate-ordering gate (E9), the summary
eval floor (E10), the quiet-week summary a commenter can have refused for ever
(E11), and the E2 and E3 list that file names. Then the E8, E9, E10, E11, E13
and process entries of `carried-from-e5.md` that nothing in E6 touched; the
ledger names each one.

**Re-carried below with a new fact from E6:** the bounced comment that stays
outside the moderation pass, `PERSON_TABLES`, the TypeScript 7 pair, the
session-read sweep's limits, and the denial-module inventory.

**New from E6:** the Care-sweep work and ruling 5 for E10, the note for E8, the
accessibility scan, two LOWs on the leadership drive, released comments on the
instructor page, the review queue's refusal of three leadership roles, the two
older copies of "closed", two behaviours no test covers, two mockups' notice
attributes, and the exit drives' pinned dates.

## No deployment reaches real students until E10's Care queue exists

The owner's ruling 5 (`../e6/README.md`), repeated here as E6-07's ticket asks.
E6 hides every threat and self-harm comment from every instructor and leadership
view and opens a `threat_case` row for each, but nothing reads those rows until
E10's Care queue, which is Phase 2. A student at risk whose comment is held from
every view and read by nobody is the outcome the ruling rules out. SPEC §12's
phase lines and ADR 0187 carry it. **Owner:** E10. **Done when:** the Care queue
reads `threat_case`, and only then may a deployment reach real students.

## The Care sweep owes two kinds of held comment, and old summaries owe a look

Three things E10's Care review has to take into its scope, from E6-02 (#293),
E6-05 (#296) and E6-08:

- **A provider refusal is retried every hour and holds its week.** No HTTP
  status counts toward the moderation attempt cap; only an unusable answer does
  (ADR 0188's amendments). So a comment a provider refuses, which a content
  filter is likeliest to do for a threat or self-harm disclosure, is asked again
  every hour and holds its section-week back from the report and the summary
  until E10's Care review decides it.
- **A capped comment holds its week until a person decides it.** A comment
  that reaches the cap through six unusable answers is not asked about again and
  is left with no verdict. Ruling 8 (E6-08): `section_week_moderated` does not
  count it resolved, so its whole section-week stays out of the report, the
  release cut and the summary. An unusable answer can come back for every
  request (a proxy error page, a model swap), and a week released past it would
  skip the threat and self-harm check. Nothing in E6 decides a capped comment,
  and it never opens a `threat_case` row.
- **Summaries written before a later Care verdict.** A `summary.v1` row above
  the threshold may paraphrase a comment that a later Care verdict removed from
  every view. E6's sweep never re-sends a comment that holds a verdict, so the
  case arises only for rows written before E6.

**Owner:** E10, with the Care queue. **Done when:** E10's Care sweep reviews
every comment that is refused or capped, and a person's decision there writes
the verdict that releases its week, so that neither kind holds its week for
ever, with a test for each; and a record decides whether stored summaries
that predate a Care verdict on a comment they drew from are withheld or
regenerated.

## A note for E8: what a student's comment read uses

Student comment reads use `report_comment` v004 and show published and kept
comments only. The view already leaves out every comment that has no moderation
verdict or that has ever had a threat or self-harm verdict (ADR 0187); a
student read adds the lifecycle filter on top of it, and never a query of its
own over `answer`. **Owner:** E8, with the student results view. **Done when:**
the student results view reads comments through v004, a test shows a flagged,
an excluded and a Care-class comment absent, and a kept one present.

## The bounced comment stays outside the moderation pass

`../e3/carried-from-e2.md`'s entry, with the fact E6 adds. ADR 0114 does not
store bounced comment text, and E6's moderation sweep moderates stored comments
in closed windows (ADR 0188), so a disclosure short or garbled enough to be
bounced is never moderated. That entry asked E6 to name it when its pass was
designed; this is the naming. **Owner:** E10, unchanged. **Done when:**
unchanged from the source entry.

## The accessibility scan is not run on the moderation pages

E6-06 (#297) could not add the axe scan its ticket asked for:
`@axe-core/playwright` is not installed, and `package.json` is a path the merger
refuses on a ticket pull request. No spec in the suite runs axe. **Owner:** a
`process/` pull request that adds the dependency, then the next UI epic, which
adds the scan to the instructor-report and leadership-moderation drives.
**Done when:** both drives run an axe scan on each moderation page they reach and
fail on a violation.

## Two LOWs on the leadership moderation drive

From E6-06's security review (#297). `tests/e2e/leadership-moderation.spec.ts`
writes a test-only `lead_faculty_mapping` row. A killed run leaves it behind on a
long-lived local database, and the cleanup deletes by course and person, so it
could remove a seeded row if the seed ever mapped that person to `BIOL 215`.
**Owner:** the next ticket that touches that spec. **Done when:** `beforeAll`
deletes any stale row first, and `afterAll` deletes only a row this run
inserted.

## Released comments are read-only on the instructor page

E6-04's scope choice (#295): the "Comments from earlier weeks" list offers no
decision. **Owner:** the next epic that touches the instructor report page.
**Done when:** a record decides whether an instructor may exclude a released
comment, and the page follows it.

## Deans, vice presidents and the assistant dean have no review queue

ADR 0190 refuses those three roles the review queue and the exclusion log with a
403 until E9's transitive purview exists, since a dean or vice president is not a
reviewer SPEC §5.2 names and an assistant dean's own grant is empty until then.
**Owner:** E9. **Done when:** E9 decides what each of the three roles reads,
through the purview walk, and the refusal is replaced or restated in a record.

## Two older copies of "closed"

E6-03 defined a closed window once, as `survey_windows.closed_by`
(`closes_at < now`), and moved the moderation path onto it. Two older copies of
the comparison remain, one in `backend/app/services/report_comments.py` and one
in `backend/app/services/reporting.py`; find them by grepping for
`closes_at <`, not by line. **Owner:** the next epic that touches either file.
**Done when:** both use `survey_windows.closed_by`, and no other copy is left
under `backend/app/`.

## Two behaviours no test covers

E6-05's pull request (#296) names them: the exclusion log's excerpt rule for a
released comment, and the error-level log line written when the moderation
sweep's unlock finds no lock. **Owner:** the next ticket that touches the
exclusion log or the moderation sweep; E10's Care sweep is the likely one.
**Done when:** a test covers each.

## Two mockups still pass a count to the small-N notice

E6-04 (#295) made `design/SmallNNotice.dc.html` state no count.
`design/LeadershipRollup.dc.html` and `design/StudentResults.dc.html` still pass
it `responded` and `total`, which it now ignores. **Owner:** the next ticket that
touches either mockup; E8 and E9 are the candidates. **Done when:** neither
passes the two attributes.

## The exit drives read pinned dates in Fall 2026

The report and moderation drives move the clock to fixed dates (the latest,
`tests/e2e/exit-moderation.spec.ts`, to 2026-11-23). The roster sync dates an
enrollment from the real clock, so once the real date passes a drive's pinned
reading date, that drive's reads stand before its own enrollments and the drive
goes red with no change to the product. **Owner:** a `process/` pull request or
the next ticket that touches the e2e world. **Done when:** the drives derive
their dates from the seeded calendar relative to the real date, or the seeded
calendar moves with it, and a drive run after 2026-11-23 is green.

## The `PERSON_TABLES` standing question, re-asked and re-carried

E6's answer is in `../e6/boundary-review.md`: `threat_case` and
`moderation_state` are reached by the person walk and carry no identity, each
with a pinned column tuple, and `decided_by_person_id` is a `person` key whose
identity sits on `user_identity`. `PERSON_TABLES` is unchanged. **Owner:** E13 at
the latest; every epic boundary re-asks it of the tables it adds.

## The TypeScript 7 pair waits on typescript-eslint

Checked 2026-10-10: latest typescript-eslint 8.71.1, peer range still
`>=4.8.4 <6.1.0`. Pinned: TypeScript 6.0.3, typescript-eslint 8.71.1.
**Owner / done when:** unchanged from the source entry.

## The session-read sweep's two disclosed limits

Re-affirmed at the E6 boundary by planting in `api/leadership.py` and
`api/instructor.py`. E6 added no route-serving package outside `backend/app/`.
**Owner:** each boundary re-affirms; the structural close is E13's.

## The denial-module inventory and the collection floor

Unchanged in class. E6 added fourteen invariant-marked modules, and the
isolated pass collects every one (`../e6/boundary-review.md` lists them).
**Owner:** a candidate process ticket, unchanged. **Done when:** unchanged.

## The ledger

Every source entry, in its source file's order, with what happened to it.

### `../e6/carried-from-e5.md`

| Source entry | Disposition |
|---|---|
| How the sources were dispositioned: the held-note type | Closed by E6-03 |
| — the `moderation_state` tie-break | Closed by E6-01 |
| — SPEC §6.2's threat class | Closed by E6-01 |
| — the reveal door's harm-class narrowing | Closed by E6-01 |
| — the forged summary block boundaries | Carried through unchanged (E7's draft work first) |
| — the bounced comment before harm screening (E2 and E3 list) | Re-carried with E6's fact (E10) |
| — every other pass-through | Carried through unchanged, under its source owner |
| E8's first obligation: the literal two-line walk | Carried through unchanged (E8) |
| A named set's figures are read with no reader and no purview | Carried through unchanged (E9) |
| Generative sibling isolation does not cover named sets | Carried through unchanged (E9) |
| The rating term-axis read and three cohort views are unread | Carried through unchanged (E9) |
| Set names that differ only in case are two sets | Carried through unchanged (E9) |
| Two older accessibility patterns | Closed by E6-04 |
| A named-set write leaves no audit record | Carried through unchanged (E10) |
| The instructor gate's 401 sentence is still a literal | Closed before E6, by E5.1-03 |
| The course label is composed in three places, and `_person_of` in two | Closed before E6, by E5.1-03 and E5.1-07 |
| The de-anonymization statement, E6's half | Closed by E6-03 and E6-05 |
| The frontend confidentiality tests have no structural floor | Carried through unchanged (a process ticket) |
| The denial-module inventory and the collection floor | Re-carried with E6's count |
| The `PERSON_TABLES` standing question | Re-asked of E6's tables; re-carried |
| The TypeScript 7 pair | Re-checked 2026-10-10; re-carried |
| The session-read sweep's two disclosed limits | Re-affirmed by planting; re-carried |
| A reader can set a prior term's report against a current one | Carried through unchanged (owner ruling, then E9) |
| A published figure moves if membership changes after publication | Carried through unchanged (owner ruling, then E9) |
| Two readers who pool what they know are out of scope | Carried through unchanged (the owner) |
| A submission racing the close can land on either side of the cutoff | Carried through unchanged (E8) |
| The hero line keeps its scaling stroke | Carried through unchanged (E8) |
| The exit drive does not show a week where only the university line is withheld | Carried through unchanged (E9) |
| The test-edit hook misses its exemption inside a worktree | Carried through unchanged (a `process/` pull request) |
| A comment with no moderation verdict counts as published | Closed by E6-01 |
| Raising the comment threshold re-holds weeks the instructor already saw | Carried through unchanged (E11) |
| Summaries written before the per-stream rule, and the small-N prompt's premise | Closed by E6-02 |
| A week's item total uses today's question set | Carried through unchanged (the ticket that adds a second question set) |
| The cookieless launch is not bound to the browser that started it | Carried through unchanged (E13) |
| `.env.example` ships `ENVIRONMENT=development` | Carried through unchanged (E13) |
| The student's submitted notice says results appear when the week closes | Carried through unchanged (E8) |
| The design mockups show one notice per week and a response count | Closed by E6-04 |
| A teaching grant with a child edge would stop its section's roster sync | Carried through unchanged (E9) |
| `ended_teaching_grant` has no retention rule | Carried through unchanged (E13) |
| The `/dev` controls' origin check trusts the request's own Host header | Carried through unchanged (E13) |
| Six server-required members stay optional in the frontend, and one figure has three names | Carried through unchanged (E9) |
| The per-stream gate has no generated property | Closed by E6-01 |
| The summary gather's blank-comment class is not pinned to the view's | Closed by E6-01 |
| The roster reads full role URIs only | Carried through unchanged (E13) |
| Ledger row: a local `.env` keeps `BENCHMARK_MIN_RESPONDENTS_DEFAULT=15` | Closed by E6-02 |
| Ledger row: the submit budget measured 2.95 s once | Closed by E5.1-10 |

### E6's pull requests, in merge order

| Deferral | Disposition |
|---|---|
| #292: a later Care verdict on a comment already shown | Closed by E6-02 (the sweep never re-sends a verdicted comment) |
| #293: a capped comment is never routed to Care | Carried: "The Care sweep owes two kinds of held comment" (E10) |
| #293: 400 and 422 refusals retry and hold their week | Carried in the same entry, as E6-08 left it (E10) |
| #295: released comments are read-only | Carried (the next report-page epic) |
| #295: two mockups pass a count to the small-N notice | Carried (E8 or E9) |
| #296: the queue refused to deans, vice presidents and the assistant dean | Carried (E9) |
| #296: the excerpt rule and the unlock log line have no test | Carried (the next exclusion log or sweep ticket) |
| #296: the log lists rows from sections the reader teaches; 413 and 422 count toward the cap | Closed by E6-08 |
| #297: the axe scan | Carried (a `process/` pull request, then the next UI epic) |
| #297: two LOWs on the leadership drive's mapping row | Carried (the next ticket touching that spec) |
| #298: an unusable answer that comes back on every request caps every comment, and the week released unchecked | Closed by E6-08 (ruling 8: a capped comment holds its week); the person's decision that releases it is carried to E10 in the Care sweep entry |

### The E6 boundary (`../e6/boundary-review.md`)

Pending: the reviews run after this file is written.
