# Carried from E9 into E10

Things E9 decided or deferred that later work has to know, per SPEC §14.1: one
entry per thing, each with an owner and what it looks like to be finished. This
is a hand-off note, not a ticket; the next breakdown schedules the work, and an
entry here is what that breakdown has to have read first. Created by E9-13.
Entries point at the record that owns the detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e9/carried-from-e8.md` not closed inside E9, every older entry E9 carried as
it stood, plus everything an E9 pull request deferred to a later epic or
accepted as residue, plus everything the E9 boundary reviews found and did not
fix inside the epic, appears here.** E9 kept no `deferred.md`; its tickets named
their deferrals in their pull request bodies, and those are the second source.
The demonstration is the ledger at the end of this file: every source entry is
named with what happened to it, in the source's own order.

## How the sources were dispositioned

**Closed inside E9,** each closure recorded in its source file with the pull
request and the merge commit: the entries `../e9/carried-from-e8.md` marks
closed, and the older entries E9 owned in `../e8/carried-from-e7.md`,
`../e7/carried-from-e6.md`, `../e6/carried-from-e5.md`,
`../e5/carried-from-e4.md` and `../e3/carried-from-e2.md`.

**Carried through unchanged**, under the owner and done-when of the source
entry, every entry the ledger below marks so. They are not restated here.

**Re-carried below with a new fact from E9,** and **new from E9,** under their
own headings.

## For E10

### No deployment reaches real students until E10's Care queue exists

The owner's ruling 5 (`../e6/README.md`), repeated by every epic since E6. E9
adds no reader of `threat_case`. **Owner:** E10. **Done when:** the Care queue
reads `threat_case`, and only then may a deployment reach real students.

### Every Care grant is shown in the Admin access log

E9's ruling 1 (`../e9/README.md`): the People editor grants Care and Admin to
anyone, the acting admin included, and the audit row is the control rather than
a code refusal (ADR 0200). SPEC §6.2's outside review needs to see each grant
beside the reveals. Two LOWs from the boundary make the join wider:
`threat-model` found that linking a login to a person before granting Care
hides who holds Care, since the linkage row records the role only at its own
time; `privacy-authz` found that creating and editing a person writes no audit
row. **Owner:** E10, with the access log. **Done when:** the Admin access log
shows every Care grant and revocation with its actor and time, joined with the
linkage, grant and person-creation history so the person who holds Care is
named at each point, with a test that a link written before a grant still names
the Care holder; and person creation and edits are audited, or a record says
why not.

### E10's audit screen scopes `audit_log.detail`

E9-06 (#338) and SPEC §8: an applied import's row holds every staff name its
dry-run diff shows. No runtime role reads `audit_log` today. **Owner:** the first
screen that reads `audit_log.detail` (E10's). **Done when:** that read is scoped
as a staff-name read, with a test that a reader outside the admin console gets no
name from it.

### Conflict-of-interest marking across a revealer's whole purview

SPEC §6.2 and the E9 README's "Left out": E9-01's purview walk (ADR 0199) now
makes a revealer's whole purview computable. **Owner:** E10, with the reveal
flow. **Done when:** a reveal is marked a conflict of interest when the revealed
student's section lies anywhere in the revealer's purview, not only their own
assignment's node, with a test over a supervised chair's section.

### The `moderation.py` split and its import cycle

From `../e7/carried-from-e6.md` (three entries: the import cycle, the module's
two jobs, its small redundancies). E9-09 widened the module (the purview read)
and E9-14 its docstring; neither split it, because E10's Care sweep restructures
the module, which is where the split belongs. **Owner:** E10. **Done when:** the
classification and the review-queue reads live in separate modules, the import
cycle with the report services is gone, and the redundancies the source entry
lists are removed.

### A leadership session reaches no Care route

From E9-04 (#336): the switcher issues one role per session, and the test that a
leadership session is refused at every Care route belongs with the Care routes.
**Owner:** E10. **Done when:** an invariant-marked test drives every Care route
with a leadership session, and a session switched from Care to leadership, and
each is refused.

### The summary-sequence race

E9-09's accepted residue (#340, ADR 0206): the decision sequence orders inserts,
not commits, so two removals racing one summary walk in one section-week can let
a summary written before a removal pass the filter. It reaches the drill-down,
the on-behalf read and the draft and check. **Owner:** the next ticket that
touches the summary walk or moderation decisions (E10's sweep at the latest).
**Done when:** each decision takes a per-section-week `pg_advisory_xact_lock` and
the walk takes and releases the same key just before reading the sequence, or a
record argues the residue again.

### Undated exclusion-log rows that tie keep their input order

E9-14's re-check LOW (#349): withheld rows that tie on section, decision and
answer id keep newest-first order, so a non-decider can tell which came later.
**Owner:** the next ticket that touches the exclusion log. **Done when:**
undated rows sort by every field the reader sees before the answer id, with a
test of an exclusion, its undo and a second exclusion of one comment.

### The cookie's lifetime after a switch

E9-04's residue (#336): after a switch the session cookie's `max_age` is a full
hour while the token keeps the old expiry, so the browser keeps a cookie no
gate accepts. Nothing lives longer. **Owner:** the next ticket that touches the
switch. **Done when:** the cookie's `max_age` is the token's remaining life,
with a test.

### Back-channel logout

E9's ruling 8 and SPEC §14.3. **Owner:** E13. **Done when:** ending the identity
provider's session ends the Pulse session.

### The exit drives read pinned dates in Fall 2026

From `../e9/carried-from-e8.md`. The `process/` pull request did not land in E9,
and the latest pinned reading is **2026-11-23**: after that date those drives
fail on every CI run. **Owner:** a `process/` pull request, **before
2026-11-23**. **Done when:** no spec under `tests/e2e/` sets the clock to a
literal date.

### Comments that tell ticket history

From `../e9/carried-from-e8.md`. Each E9 ticket rewrote the comments in the
files it edited, and E9-16 (#348) four more, but
`rg "E[0-9]+(\.[0-9]+)?-[0-9]{2}" backend/app frontend/src` still matches in 209
files outside the tests and the generated files. **Owner:** the next ticket that
touches each file. **Done when:** that search finds no comment naming a ticket.

### Simplifications the E7 boundary proposed

From `../e9/carried-from-e8.md`, less the chair's walk (E9-01). Still open: the
lead-and-chair rule written three times in SQL; `record_policy` recomputing what
its caller knows; `publish_response` converting a course week itself.
**Owner / done when:** unchanged.

### The e2e suite's shared-stack residue

From `../e9/carried-from-e8.md`, unchanged in E9: three specs leave rows a
second run trips over, and the hold banner is driven in component tests only.
E9's own drives each run twice on one stack by construction
(`../e9/boundary-review.md`). **Owner / done when:** unchanged.

### The standing questions, re-asked at the E9 exit

The answers are in `../e9/boundary-review.md`.

- **`PERSON_TABLES`**: E9 widened `audit_log` and added `revoked_session`;
  unchanged and correct. **Owner:** E13 at the latest.
- **The TypeScript 7 pair**: re-checked 2026-10-12, typescript-eslint 8.71.2,
  peer range still `>=4.8.4 <6.1.0`. **Owner / done when:** unchanged.
- **The session-read sweep's two disclosed limits**: re-affirmed by planting in
  `api/admin.py` and `services/rollups.py`. **Owner:** each boundary; the
  structural close is E13's.
- **The denial-module inventory and the collection floor**: thirty-seven new E9
  invariant-marked modules, every one collected. The boundary's
  `invariant-coverage` adds that the marker gate finds modules by file name.
  **Owner:** a candidate process ticket. **Done when:** unchanged.

### Small things the boundary left

- **A redundant unique constraint** (`data-model` LOW): `uq_comparison_set_name`
  is covered by E9-05's normalized-name index. **Owner:** the next migration on
  `comparison_set`. **Done when:** it is dropped.
- **The AST sweep helpers** (`code-reviewer`): five sweeps each write their own
  AST walk. **Owner:** a test-only tidy-up. **Done when:** one helper serves
  them, or a record says why not.
- **The bundle gate measures the largest chunk only** (E9-15, #347): a partition
  change moved the largest chunk from 100.0 KB to 121.3 KB while first-load
  JavaScript fell. **Owner:** the owner's call, on a `process/` pull request.
  **Done when:** the gate measures what a visitor downloads, or a record says
  why the largest chunk is the right measure.

## Re-carried from E8 unchanged

Each under its owner and done-when in `../e9/carried-from-e8.md`: the landing
reads a full results payload for each section (E13); ADR 0198 overstates a
failed post with no response code; a release batch's `cut_at` is the database's
clock; the exit drive's posted score is planted; the student trend's axis ends
at the latest published week.

## The ledger

Every source entry, in its source's order, with what happened to it.

### `../e9/carried-from-e8.md`

| Source entry | Disposition |
|---|---|
| How the sources were dispositioned: the pass-throughs | Carried through unchanged, under their source owners |
| No deployment reaches real students until E10's Care queue exists | Repeated (E10) |
| A stored summary can carry a comment excluded after it was written | Closed by E9-09 (#340); the race left is new above |
| The Lead Faculty name in the student page header | Closed by E9-08 (#337) |
| The leadership rollup mockup still passes a count | Closed by E9-11 (#344) |
| Comments that tell ticket history | Re-carried |
| The exit drives read pinned dates in Fall 2026 | Re-carried (before 2026-11-23) |
| Simplifications the E7 boundary proposed, and the chair's walk | Chair's walk closed by E9-01 (#335); three re-carried |
| The e2e suite's shared-stack residue | Re-carried |
| The standing questions | Re-asked; re-carried |
| Shares at small n can still pin the rater count | Closed by ruling 9 and E9-08 (#337) |
| Split the student read out of the response-loop service | Closed by E9-08 (#337) |
| The landing reads a full results payload for each section | Re-carried unchanged (E13) |
| Leadership staff-name reads are set-based | Closed by E9-03 (#333) with E9-07, E9-09, E9-11 |
| ADR 0198 overstates a failed post with no response code | Re-carried unchanged |
| A release batch's `cut_at` is the database's clock | Re-carried unchanged |
| The exit drive's posted score is planted | Re-carried unchanged |
| The student trend's axis ends at the latest published week | Re-carried unchanged |

### Older entries E9 carried as they stood

From `../e8/carried-from-e7.md` (and through it the pass-throughs of
`../e7/carried-from-e6.md`), in source order.

| Source entry | Disposition |
|---|---|
| The forged summary block boundaries, passed on unchanged | Not triggered in E9; carried through unchanged |
| For E9: the attention list, staff names, and three leadership roles | Closed by E9-07 (#341), E9-03 (#333), E9-09 (#340) |
| For E9: purview-wide reads of the response tables | Closed by E9-07 (#341) |
| The on-behalf summary filter compares transaction-start times | Closed by E9-09 (#340); its narrower race is new above |
| Two publishes at the same instant: a 500 and a second author's row | Carried through unchanged (the next publish-door ticket) |
| The draft and check evals have no floor | Carried through unchanged (E10) |
| `record_teaching_instructor` accepts any person key | Carried through unchanged (the next teaching-definer ticket, or E13) |
| The staff-name definer judges "today" by the database's UTC date | Closed by E9-03 (#333) |
| The draft eval set bypasses the output contracts | Carried through unchanged (E10) |
| `response_gather` has a keyword that changes nothing | Carried through unchanged |
| The E7-10 graders' closed word lists | Carried through unchanged (E10) |
| The composer's busy line is inserted with its text | Carried through unchanged |
| The Care sweep owes two kinds of held comment, and old summaries owe a look (`../e7/carried-from-e6.md`) | Carried through unchanged (E10) |
| The bounced comment stays outside the moderation pass | Carried through unchanged (E10) |
| Deans, vice presidents and the assistant dean have no review queue | Closed by E9-09 (#340), by decision 12 |
| Two behaviours no test covers: the unlock log line | Carried through unchanged (the next sweep ticket) |
| The import cycle between moderation and the report services | Re-carried: "The `moderation.py` split and its import cycle" |
| `services/moderation.py` does two jobs | Re-carried with the same |
| Small redundancies in `services/moderation.py` | Re-carried with the same |
| The review queue has no index of its own | Carried through unchanged (E10) |
| No precision or recall floor for moderation | Carried through unchanged (E10) |
| Grading reads the close the other way | Carried through unchanged (the next grading ticket) |
| A named set's figures are read with no reader and no purview (`../e6/carried-from-e5.md`) | Closed by E9-05 (#339) |
| Generative sibling isolation does not cover named sets | Closed by E9-05 (#339) |
| The rating term-axis read and three cohort views are unread | Closed by E9-05 (#339) and E9-12 (#345) |
| Set names that differ only in case are two sets | Closed by E9-05 (#339) |
| A teaching grant with a child edge would stop its section's roster sync | Closed by E9-06 (#338) |
| Six server-required members stay optional in the frontend | Closed by E9-11 (#344) |
| The exit drive does not show a week where only the university line is withheld | Closed by E9-13 (#346) |
| The landing views' sentences sit outside the inventory (`../e5/carried-from-e4.md`) | Closed by E9-04 (#336) and E9-11 (#344) |
| Aggregate ordering has no code-level gate | Closed by E9-07 (#341), E9-12 (#345), E9-14 (#349) |
| The E1 generative purview coverage note (`../e3/carried-from-e2.md`) | Closed by E9-01 (#335) |
| A web-login linkage can only be provisioned by the demo seed or by hand | Closed by E9-02 (#334), E9-06 (#338), E9-10 (#343) |
| Logout and back-channel logout | Logout closed by E9-04 (#336); back-channel logout new above (E13) |

### E9's pull requests, in merge order

| Deferral or residue | Disposition |
|---|---|
| #332 (the breakdown): the §5.1 instructor-clause wording | Closed by E9-05 (#339), done-when 16 |
| #333 (E9-03): the section list has no length cap; the definer trusts the reader's date | Accepted residue (ADR 0201); nothing owed while only internal code calls the door |
| #334 (E9-02): the linkage row names no login; any admin's key can grant Care or Admin | Accepted (ADR 0200); the Care grants new above |
| #337 (E9-08): `section_lead_name` fixed `scope=None` | Closed by E9-14 (#349): the scope is required |
| #336 (E9-04): a switch racing a logout survives it | Accepted residue (ADR 0202); nothing owed |
| #336: the cookie's `max_age` after a switch | New above |
| #336: a leadership session reaches no Care route | New above |
| #336: back-channel logout | New above (E13) |
| #335 (E9-01): `leadership_grant_covers` has no caller sweep | Closed by E9-12 (#345) |
| #339 (E9-05): `benchmark_trend` and `benchmark_workload` take no reader | Closed by E9-12 (#345): the sweep pins them |
| #340 (E9-09): the summary-sequence race | New above |
| #338 (E9-06): a serialization failure on a read answers 500; the `detail` check counts a JSON null | Accepted residue; nothing owed |
| #338: E10's audit screen must scope `detail` | New above |
| #342 (a test flake fix) | Nothing deferred |
| #341 (E9-07): `pulse_app` can map every user to a person in one call; the course label spelled twice | Accepted residue (ADR 0205); nothing owed |
| #343 (E9-10): an assignment falls back to its role label if the org-nodes read fails | Accepted residue; nothing owed |
| #343: heavy code written before its tests | Recorded in #343; nothing owed |
| #344 (E9-11): focus on every tree choice; a collapsed chosen row; the attention rule's word | Focus closed by E9-15 (#347); the collapsed row accepted; the word closed by E9-15 under the owner's ruling |
| #345 (E9-12) | Nothing deferred |
| #347 (E9-15): the duplicate sentence and the dotted tier | Closed by E9-16 (#348) |
| #347: the bundle gate measures the largest chunk only | New above |
| #348 (E9-16): two wording LOWs | Closed by E9-13 |
| #349 (E9-14): a non-decider learns roughly when an undated row appeared; a second LEAD_FACULTY assignment cannot be revoked while mappings exist | Accepted residue; nothing owed |
| #349: undated rows that tie keep their order | New above |
| #346 (E9-13): the drives were not run on a local stack | Shown by structure and by CI (`../e9/boundary-review.md`) |

### The E9 README's "Left out, and why"

| Item | Disposition |
|---|---|
| Back-channel logout | New above (E13) |
| Assignment end-dating and history | Ruling 7; SPEC §14.3 records the four predicates to change together |
| Pooled comments on roll-up pages | Ruling 2; nothing owed |
| A code refusal of Care, Admin or self-targeted grants | Ruling 1; the access log new above |
| Freezing set membership at publication | Ruling 6; nothing owed |
| Coarser share buckets or a higher floor | Ruling 9; nothing owed |
| A SQL copy of the purview walk | Ruling 3; nothing owed |
| Loading the tree lazily | Revisit at E13's load test |
| Escalation along the supervision graph | Nothing owed |
| The Care case count on a leadership surface | E10 or E11, an institutional decision |
| Policy writes by the assistant dean, dean or VP | §5.3; nothing owed |
| A composer or AI panels in the drill-down | §5.5; nothing owed |
| Conflict-of-interest marking across a revealer's purview | New above |
| The `moderation.py` split and its import cycle | New above |
| Per-level questions and the MCP server | Phase 3 |

### The E9 boundary (`../e9/boundary-review.md`)

Everything the boundary reviews found and E9-14 (#349), E9-15 (#347), E9-16
(#348) and E9-13 did not fix.

| Finding | Disposition |
|---|---|
| `threat-model` LOW: a login linked before a Care grant hides who holds Care | New above, with the Care grants |
| `privacy-authz` LOW: person creation and edits are unaudited | New above, with the Care grants |
| `data-model` LOW: redundant `uq_comparison_set_name` | New above |
| `code-reviewer`: the AST sweep-helper consolidation | New above |
| `invariant-coverage` LOW: the marker gate finds modules by file name | Re-carried with the standing questions |
| `spec-conformance` LOWs: E9-10's code before its tests; a weak test E9-12 covers; a removed series check | Recorded; nothing owed |
| Every other finding | Fixed in E9-14, E9-15, E9-16 or E9-13 |
