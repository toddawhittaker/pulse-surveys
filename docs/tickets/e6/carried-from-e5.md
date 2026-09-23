# Carried from E5 into E6

Things E5 decided or deferred that later work has to know, per SPEC §14.1:
one entry per thing, each with an owner and what it looks like to be
finished. This is a hand-off note, not a ticket; the next breakdown
schedules the work, and an entry here is what that breakdown has to have
read first. Created by E5-14. Entries point at the record that owns the
detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e5/carried-from-e4.md` not closed inside E5, plus every entry of
`../e5/deferred.md` still open after E5-14's cleanup pass, plus everything
the E5 boundary reviews found and did not fix inside the epic, appears
here.** The demonstration is the ledger at the end of this file: every
source entry is named with what happened to it, in the source file's own
order. Nothing was dropped silently.

## How the sources were dispositioned

**Closed inside E5, from `carried-from-e4.md`:** the two report-payload fields
the design mockup needs (E5-02, closed in the source file on 2026-09-13).
That was the only E5-owned entry.

**Carried through unchanged** — the source entry's owner and done-when
govern, and nothing about them moved in E5. From `carried-from-e4.md`'s own
pass-through list: the roster sync's unbounded token-acquisition dial; the
`azp`/multi-valued-`aud` launch handling and the per-launch JWKS fetch (both
re-affirmed untouched by the E5 boundary's `lti-oidc` review); the
rewound-clock family; the flaky fail-closed framing test; `post_score`
returning nothing; provisioning's docstring-only separation; the rehoming of
the pinned-resolution adapter and Link parser; the clock routes' missing
origin check; the signing-key runbook (E13); ruff's `py313` target (ruff is
still 0.6.9, so the next ruff bump still owns it); and everything that file's
ledger carried through from E2 and E3 — the registration chokepoint's CSP
endpoint, the squatted section binding, the web-login linkage provisioning,
logout and back-channel logout, the local-account fallback, the two
registration-write blind spots, the generative purview note, the
bounced-verdict cap and aggregation halves, the unproven structural battery
rows, the bounce that names no position, the self-hosted font licences, the
rewound-clock resubmission 500, the model identifier in three untied places,
the floor-headroom variance point, and the bounced-comment-before-harm-screening
hook. Their detail lives in `../e4/carried-from-e3.md` and the files it points
back to. From `carried-from-e4.md`'s own sections, also unchanged: the held-note
type (E6), the forged summary block boundaries (E7's draft work first), the
`moderation_state` tie-break (E6), the §6.2 threat class (E6), the landing
views' sentences (E9), the serial summary walk (E13), the reveal door's
harm-class narrowing (E6), the aggregate-ordering gate (E9), the summary eval
floor (E10 at the latest), and the quiet-week summary a commenter can have
refused for ever (E11). None of them is restated below; `carried-from-e4.md`
holds each one.

**Re-carried below with a new fact from E5:** the de-anonymization statement's
E6 half; the course label's composers (now three); the frontend
confidentiality tests' structural floor; the denial-inventory and
collection-floor class; `PERSON_TABLES`; the TypeScript 7 pair; and the
session-read sweep's limits.

**From `../e5/deferred.md`:** ten entries closed inside E5, each with its
closing note in the file. Five are still open and re-listed below: the three
unread cohort views (with E5-06's correction to its owner line folded in),
the instructor gate's 401 literal, the untraced set delete, and the student
sweep over one week.

**From the E5 boundary** (`../e5/boundary-review.md`), including the passes
over E5-14's own fix rounds: every finding not fixed inside the epic is an
entry below. The process findings about `main` are not: PR #248 closed them
(merged as 0a9f81a).

## E8's first obligation: the literal two-line walk, across consecutive weeks

SPEC §14.3's E5 exit says a student provably sees two lines. The only student
trend surface the spec names is TrendDuo on the student results view (§5.4,
§7.6), which is E8's, and it had not merged when E5 closed. So E5-14 recorded
the structural proof (breakdown decision 9): the student schemas refuse an
undeclared member (ADR 0175), the student routes are swept, and a student
seat walked over two consecutive weeks carries no benchmark key on the wire
and no comparison element on the page, with the instructor's page in the same
world as the canary. `../e5/deferred.md`'s "the student benchmark sweep runs
over one week" entry is the other half of the same obligation: there is no
page a student can use to move between published weeks until E8 builds one.
**Owner:** E8, as its first obligation. **Done when:** the results view is
walked on a student seat across consecutive published weeks, each week shows
exactly two lines, the benchmark key sweep runs over every one of those
responses, and the instructor's own page in the same world still reads three
lines as the canary.

## A named set's figures are read with no reader and no purview

From the boundary's `privacy-authz` review, which disputes the decision rather
than calling it an oversight. `named_set_trend` and `named_set_workload` take a
set and cutoffs and nothing about who is reading, and ADR 0173 lets every
leadership session read every set. Nothing renders a named set's figures yet
(breakdown decision 4), so nothing is exposed. But the first surface that does
render one to a Lead Faculty member can hand her a set made of a sibling lead's
courses — a sibling's course report by another road, which §4.1 item 2
forbids. The same question decides which cutoffs a leadership reader gets,
since the freeze (ADR 0178) takes its cutoff from a section's term, length
and level, and a named set can span terms and has no reported section.
**Owner:** E9, with the purview computation. **Done when:** a named-set figure
is served only for sets inside the reader's purview (or a spec sentence rules
that a named set's figures are institution-level and says why §4.1 item 2 does
not reach them), the cutoffs a leadership reader gets are decided in a record,
and a test plants a sibling lead's set and shows it refused.

## Generative sibling isolation does not cover named sets

From the boundary's `invariant-coverage` review. The generative tests that
prove a lead never sees a sibling lead's course walk reports; they do not
generate named sets. **Owner:** E9, together with the entry above.
**Done when:** the generative sibling-isolation test draws named sets over
random course lists and leads, and asserts no figure reaches a reader outside
her purview.

## The rating term-axis read and three cohort views are unread

Breakdown decision 7 said the cohort-mode term-axis aggregates land "as views
and service reads". The boundary's `spec-conformance` review found that only
half true: `benchmark_cohort_rating_term_axis` has no service read at all, and
`named_set_term_axis`, the one term-axis read that exists, is called by
nothing. `data-model` added that `benchmark_cohort_week`,
`benchmark_cohort_rating_week` and `benchmark_cohort_rating_term_axis` are
granted to `pulse_app` and read by nothing under `backend/app/`, and they still
pair whole-week counts with subset figures (`../e5/deferred.md`'s "three cohort
views" entry, whose owner line E5-06's correction moved away from E5-06).
Decision 7 is amended in the E5 README to say so. Since E5-14, a marked sweep
allows only `app/services/benchmarks.py` to name any of these relations, so the
first reader has one place to be.
**Owner:** E9, whose aggregate pages draw the term axis. **Done when:** the
rating term axis has a service read proven by test and sealed against its own
contributors' counts (a `_v002` per view, the established shape); every cohort
view a surface reads carries contributor counts; and any view still unread when
E9 closes is retired, with its grant.

## Set names that differ only in case are two sets

From the boundary's `data-model` review. E5-14 made a blank name unstorable
(`CHECK (btrim(name) <> '')`) and refused at the route (the schema strips
whitespace and requires a character, so a blank name is a 422). Names that
differ only in case or spacing ("Nursing core" and "nursing  core") are still
two sets. **Owner:** the next ticket that touches named-set management; E9
first, since it attaches sets to views. **Done when:** a unique index on the
normalized name refuses the near-duplicate with a governed refusal sentence,
proven by a route test — or a record rules near-duplicates acceptable and says
why.

## Two older accessibility patterns

From the boundary's `a11y-copy` review, which rated both LOW because they
predate E5. The trend charts' data-table equivalents are visually hidden, so
only a screen reader reaches them; a sighted reader who cannot read the chart
has no table. And text inputs are bordered in `--hairline`, about 1.30:1 on
paper, under WCAG 2.2 SC 1.4.11's 3:1 for the boundary of a control.
**Owner:** E6, the next epic with UI work. **Done when:** the table can be
shown to sighted readers too (or a record argues the hidden table is enough),
and input boundaries measure at least 3:1 against their background, pinned the
way `reportContrastTokens.test.ts` pins the report's colours.

## A named-set write leaves no audit record

`../e5/deferred.md`'s "a deleted comparison set leaves no trace anywhere"
entry, which the boundary's `spec-conformance` review re-raised. ADR 0174 has
the argument. **Owner:** E10's audit review surface. **Done when:** unchanged
from the source entry.

## The instructor gate's 401 sentence is still a literal

`../e5/deferred.md`'s entry of that name, unchanged. **Owner:** whichever ticket
next works on the instructor report's copy or on `app.api.deps`; E9 opens the
report to leadership and is the likely one. **Done when:** unchanged from the
source entry.

## The course label is composed in three places now, and `_person_of` in two

`carried-from-e4.md`'s course-label entry, with a fact from E5. PR #238 (E5-06)
listed two things as "proposed, not done": `_person_of` is now copied in
`api/leadership.py` beside `api/instructor.py`'s, and the named-set API added a
third, course-level label composer beside the two section-level
`_course_label` copies. **Owner:** whichever ticket next changes the label's
form or either `_person_of`; `app/services/enrollment_windows.py` (ADR 0161) is
the worked example of that promotion done under review. **Done when:** one
governed composer names a course and a section, and one helper resolves a
session's person, each with its callers moved and the copies deleted.

## The de-anonymization statement — E6's half still owed

Unchanged from `carried-from-e4.md`, with one fact. E5 added two
freeze-and-seal rules for comparison figures (ADRs 0178 and 0179), both about
a reader subtracting published numbers to isolate a small group. E6's
moderation views should read both before the first view that shows a count
beside a released comment. **Owner:** E6. **Done when:** unchanged.

## The frontend confidentiality tests have no structural floor

Unchanged in class. E5-14 extended the disabled-form sweep to
`tests/e2e/**/*.spec.ts`, so `test.skip`, `test.fixme` and `test.fail` in a
Playwright spec now red a marked test. A deleted or renamed spec still
vanishes silently. **Owner and done when:** unchanged, joined to the entry
below.

## The denial-module inventory and the collection floor

The E5 boundary paid this entry's warning again: two named-set denial tests
sat outside the isolated pass because their module name matched no shape. The
instances are closed (both marked in E5-14); the class stays open.
**Owner:** a candidate process ticket, unchanged. **Done when:** unchanged — a
collection-count floor or an equivalent the guarded set cannot shrink, watched
failing.

## The `PERSON_TABLES` standing question, re-asked and re-carried

E5's answer is in `../e5/boundary-review.md`: `comparison_set` and
`comparison_set_member` are reached by the person walk and carry nothing, each
with a pinned column tuple, and `PERSON_TABLES` is unchanged. **Owner:** E13 at
the latest; every epic boundary re-asks it of the tables it adds.

## The TypeScript 7 pair waits on typescript-eslint

Checked 2026-09-22: latest typescript-eslint 8.70.1, peer range still
`>=4.8.4 <6.1.0`. Installed pins: TypeScript 6.0.3, typescript-eslint 8.70.0.
**Owner / done when:** unchanged from the source entry.

## The session-read sweep's two disclosed limits

Re-affirmed at the E5 boundary by planting in `services/benchmarks.py` and
`api/leadership.py`. E5 added no route-serving package outside `backend/app/`.
**Owner:** each boundary re-affirms; the structural close is E13's.

## A reader can set a prior term's report against a current one

From the checks over E5-14's fix rounds (`privacy-authz`). The final cutoff is
the same for every reader of one population and week in one term (ADR 0178),
so nobody meets two snapshots of one week inside a term. Reports in different
terms still carry different snapshots of populations that overlap, because
past-referencing reaches every term: a prior-term report's week 3 and a current
one's differ by everything fixed between the two cutoffs, which can be a small
group. ADR 0179's closure argument fixes one term and one cutoff, so it does
not reach this. **Owner:** the owner, at the E5 epic review (the cutoff and
seal rulings are the orchestrator's, made while the owner was away, and are
flagged there); the construction then belongs to E9, whose dashboards put more
reports side by side. **Done when:** the owner has ruled whether snapshots
across terms need sealing against each other, and either a record says why they
need not, or a test plants two terms and shows their difference withheld when
it is below the minimums.

## A published figure moves if membership changes after publication

From the same checks. The freeze fixes which responses count, but populations
and the cutoff are resolved at read time. A lead mapping added or removed, a
section's length or start date changed, or a teaching assignment granted after
publication changes which sections a published week is computed over. The
final check on b2579f9 widened it (MEDIUM inside this residual): a section of
the same length and level that starts earlier and is synced late moves the
population cutoff for weeks already published, and with it every figure over
that population. The `benchmarks.py` docstring that claimed a published figure
depends only on rows fixed before its cutoff was corrected in E5-14 to say it
also depends on membership as resolved at read time. **Owner:** an owner ruling
first (freeze membership and the cutoff at publication, or accept the exposure
and say why), then E9, which edits lead mappings through its People & reporting
editor (SPEC §6.3). **Done when:** the ruling is recorded, and either
membership and the cutoff are fixed at publication — proven by a test that
changes a mapping, and one that syncs an earlier-starting section, after
publication and shows the figure unchanged — or a record states the accepted
exposure.

## Two readers who pool what they know are out of scope

From the final check on b2579f9. The seal (ADR 0179) protects against one
reader: every atom she cannot already see is empty or meets the minimums. Two
instructors who combine their own sections' figures can subtract atoms neither
could isolate alone, and no per-person rule can stop that. SPEC §4.1's threat
model is one reader, so this is recorded rather than scheduled. **Owner:** the
owner, at the E5 epic review. **Done when:** the owner confirms the one-reader
threat model for benchmarks, or rules otherwise and a ticket is cut.

## A submission racing the close can land on either side of the cutoff

From the same pass (LOW). `backend/app/services/submissions.py:512` reads the
clock before the commit, and the cutoff compares inclusively
(`last_submitted_at <= T(w)`), so a submission stamped at or just before the
close but committed after the report was first read can join a figure already
shown once. **Owner:** the next ticket that touches the submit path; E8, whose
student loop reuses it, is the first candidate. **Done when:** the stamp and the
window check happen under the same database clock inside the commit (or the
window closes by a rule the stamp cannot straddle), proven by a test that
submits at the boundary.

## The hero line keeps its scaling stroke

From E5-14's frontend round. The comparison and university strokes now keep
their width at narrow sizes (`vector-effect: non-scaling-stroke`); the hero
line does not, because its draw-in animation dashes along `pathLength`, which
a non-scaling stroke breaks. At narrow widths the hero's 2.5px line thins.
**Owner:** the next ticket that touches the trend chart's styles; E8's TrendDuo
is the first candidate. **Done when:** the hero line keeps its width at every
width without losing the animation (or with the animation replaced), pinned by
a stylesheet test.

## The exit drive does not show a week where only the university line is withheld

From the pass over round 2 (`spec-conformance`, LOW). The thin-cohort drive
exercises the default-set treatments; no drive shows the university line
withheld while the comparison line is drawn, the case the sealing rules (ADR
0179) produce. Component tests cover the treatment; the running stack does not.
**Owner:** the next ticket that extends the benchmark e2e (E9's dashboards at
the latest). **Done when:** a seeded week withholds only the university line
and a drive asserts the payload and the treatment.

## The test-edit hook misses its exemption inside a worktree

From E5-14's frontend round. `.claude/hooks/deny-test-edits.sh` computes a
path relative to the main checkout, so its exemption for frontend component
tests (which the implementer owns) does not match inside a worktree, and the
implementer had to write those tests through the shell. **Owner:** a
`process/` pull request. **Done when:** the hook resolves paths from
`git rev-parse --show-toplevel`, and a component test edited inside a worktree
is allowed while a backend test is still refused.

## The ledger

Every source entry, in its source file's order, with what happened to it.

### `../e5/carried-from-e4.md`

| Source entry | Disposition |
|---|---|
| The de-anonymization statement (E6's half) | Re-carried with a new fact |
| The held-note type is a free string | Carried through unchanged (E6) |
| A comment can forge block boundaries in the summary prompt | Carried through unchanged (E7 first) |
| `moderation_state` has no tie-breakable ordering | Carried through unchanged (E6) |
| SPEC §6.2's threat class is suppressed nowhere yet | Carried through unchanged (E6) |
| The course label is composed in two modules | Re-carried: now three composers, plus `_person_of` |
| The landing views' sentences sit outside the inventory | Carried through unchanged (E9) |
| The Monday summary walk is serial | Carried through unchanged (E13) |
| The reveal door accepts any answer id | Carried through unchanged (E6) |
| Aggregate ordering has no code-level gate | Carried through unchanged (E9) |
| The frontend confidentiality tests have no structural floor | Re-carried with a new fact (the e2e sweep) |
| The summary eval floor is a `DEFERRED` slot | Carried through unchanged (E10) |
| A quiet week's summary can be refused for ever | Carried through unchanged (E11) |
| The `PERSON_TABLES` standing question | Re-asked of E5's tables; re-carried |
| The TypeScript 7 pair | Re-checked 2026-09-22; re-carried |
| The session-read sweep's two disclosed limits | Re-affirmed by planting; re-carried |
| The denial-module inventory and the collection floor | Re-carried with a new instance, closed |
| Two report-payload fields the design mockup needs | Closed by E5-02 |
| The ledger's "carried through unchanged" list (E2 and E3 entries) | Carried through unchanged, each under its source owner |

### `../e5/deferred.md`

| Source entry | Disposition |
|---|---|
| The design brief maps the comparison lines to a failing colour | Closed by E5-14 (the brief edit) |
| E5-07's stroke pins live beside E5-07's tests | Closed by E5-13 |
| A `suppressed: false` member with no `points` crashes the panel | Closed by E5-10 |
| The benchmark definer's reach has no pinned equality | Closed by E5-04 |
| The benchmark service spells two statements `queries.py` also holds | Closed by E5-14 (the wrappers deleted; a marked sweep keeps one home) |
| The benchmark views do not filter a response's validity | Closed by E5-04; ADR 0166's amendment now carries it too |
| A course week assumes a section starts on a week boundary | Closed by E5-14 (a sentence) |
| Three cohort views pair whole-week counts with subset figures | Carried: "The rating term-axis read and three cohort views are unread" (E9) |
| The benchmark-history self-check has no term filter | Closed by E5-14 (a sentence) |
| The named-set API's eight refusal sentences sit outside the inventory | Closed by E5-13 |
| The instructor gate's 401 sentence is still a literal | Carried: "The instructor gate's 401 sentence is still a literal" (E9 likely) |
| A deleted comparison set leaves no trace anywhere | Carried: "A named-set write leaves no audit record" (E10) |
| E5-06's preview reads none of the three unread cohort views | Carried, folded into the cohort-views entry (E9) |
| The student benchmark sweep runs over one week | Carried: "E8's first obligation" (E8) |
| The length half of §5.1's matching has no test | Closed by E5-14 (the new test module) |

### The E5 boundary (`../e5/boundary-review.md`): findings carried, and findings closed outside the fix list

| Finding | Disposition |
|---|---|
| privacy-authz LOW: named-set figures take no reader or purview | Carried (E9) |
| invariant-coverage LOW: generative sibling isolation over named sets | Carried (E9) |
| spec-conformance MEDIUM: the rating term axis has no service read (decision 7) | Decision 7 amended; carried (E9) |
| data-model LOW: three cohort views granted and unread | Carried with the entry above (E9) |
| data-model LOW (rest): case-insensitive name uniqueness | Carried (named-set management, E9 first) |
| data-model LOW (rest): the route's refusal of a blank name | Closed by E5-14 (a 422 through the schema's minimum length) |
| spec-conformance LOW: named-set writes not audited | Carried with the deferred entry (E10) |
| a11y-copy LOW: hidden chart tables; input borders at 1.30:1 | Carried (E6) |
| adr-docs-completeness LOW: PR #238's `_person_of` and third label composer | Carried with the course-label entry |
| adr-docs-completeness HIGH, MEDIUM, LOW: process records from `main` | Closed by PR #248, merged to `main` as 0a9f81a |
| privacy-authz (pass over round 2) HIGH and MEDIUM: two snapshots per instructor; only the reported section excluded | Closed by E5-14 rounds 3 and 4 (ADRs 0178 and 0179) |
| privacy-authz (re-check on d7b4561) two HIGHs from co-teaching | Closed by E5-14 round 4 (reader-independent cutoff; per-person seal) |
| privacy-authz (final check on b2579f9) HIGH: two leads' default sets | Closed by E5-14 round 5 (the closure argument, ADR 0179) |
| privacy-authz (final check on b2579f9) MEDIUM: a late-synced earlier section moves the cutoff | Carried inside the membership residual (owner ruling, then E9) |
| privacy-authz (final check on b2579f9): two readers pooling | Recorded as out of scope (one-reader threat model); owner confirms at the epic review |
| Round-3 battery (22 rows; C3, B7, A3a real) | Closed by E5-14 round 4 (each pinned or recorded) |
| Round-4 battery (22 rows; C4, C5, C6b real; C3 equivalent in practice) | Closed by E5-14 round 5; C3 recorded |
| Round-5 battery (6 rows; the term, length and level filters in `_alike_in_this_term` survived, fail-closed) | Closed by E5-14 (ea2230e pins all three); nothing carried |
| privacy-authz (check on 0361fb3, aimed at the closure argument) HIGH: an unchecked lead atom | Closed by E5-14 round 6 (bf729fc; ADR 0179) |
| privacy-authz (pass over round 2) MEDIUM: membership resolved live | Docstring corrected; carried, widened on b2579f9 (owner ruling, then E9) |
| privacy-authz (pass over round 2): snapshots across terms | Carried (owner ruling at the epic review, then E9) |
| privacy-authz (pass over round 2) LOW: the submit-at-close race | Carried (the submit path, E8 first) |
| spec-conformance (pass over round 2) MEDIUM: SPEC §5.1 not amended; edit-page save silent; the drive's university premise | Closed by E5-14 (spec edit, round 3, the drive's `beforeAll`) |
| spec-conformance (pass over round 2) LOW: the drive shows no university-only withholding | Carried (the next benchmark e2e, E9 at the latest) |
| Battery on ce9df73: survivors FE09a, X1, X2 | Closed by E5-14 round 3 (each pinned) |
| Frontend round: the hero line's scaling stroke | Carried (the trend chart's next ticket, E8 first) |
| Frontend round: the test-edit hook misses its exemption in a worktree | Carried (a `process/` pull request) |
| epic-exit | <<EPIC-EXIT: findings not fixed, or "none">> |
| The per-PR security review of E5-14 (`app-security` on ce9df73) | Nothing found; nothing carried |
