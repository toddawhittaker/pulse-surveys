# E5 boundary review

The SPEC §14.2 item 6 record for E5 (benchmarks and comparison sets), written
by E5-14. E5 is not a ⚠ epic, so the roster is the unmarked one. Eight reviews
ran with fresh contexts, all on commit d1eaeff (the epic branch's tip, the
merge of #242) against the epic's cumulative diff from its merge-base with
`main`, f646dbb. A ninth, `epic-exit`, runs against the exit commit once the
fix rounds have landed. The fix rounds are on PR #249: round 2, commits
5bcc47b (tests, red) through ce9df73; round 3 (through d7b4561), round 4
(through b2579f9), round 5 (through 0361fb3) and round 6 (through bf729fc),
each opened by a HIGH in the check over the round before. (Round 1 settled §11 question 1 before the
reviews reported.)

**The roster, reconciled against the review skill's own trigger table**
(`.claude/skills/review-pr/SKILL.md`, section 2). §14.2 item 6 mandates
`epic-exit`, `invariant-coverage` and `adr-docs-completeness`. The skill moves
four specialists to the boundary, and all four ran: `data-model`, `lti-oidc`,
`a11y-copy` and `prompt-eval` (ADR 0004's standing arrangement). The ticket
adds `spec-conformance` over the whole epic. A whole-epic `privacy-authz` pass
ran as this exit ticket's own addition, as it did at E4, because E5's substance
is comparison figures, the class §4.1 item 7 polices. `threat-model` did not
run: §14.2 item 6 mandates it for ⚠ epics, and E5 is unmarked. It is named here
so that its absence reads as a decision rather than an omission. The per-PR
security review ran on each of the epic's fourteen pull requests before this
one — thirteen tickets and the seed fix, #224–#230 and #236–#242 — and each
body records it.

## The exit clause, verified against the running system

SPEC §14.3 E5: *an instructor sees three lines per panel benchmarked against
prior terms; a student provably sees two lines and no benchmarks.*

The drive is `tests/e2e/exit-benchmarks.spec.ts`, which runs in the existing
`chromium` project over the world `scripts/seed.py`,
`scripts/seed_demo_story.py` and `scripts/seed_benchmark_history.py` build. It
reads the payload before the page, runs serially, and clears the development
clock in a `finally`.

- **Three lines, reaching prior terms, on consecutive weeks.** The hero section
  `BIOL-310-R7FF` is walked from course week 6 down to week 1 through the week
  navigation (`docs/MISTAKES.md` entry 51 asks for consecutive views, not one
  Monday). Its default comparison set is exactly the three Spring 2026 sections
  `BIOL-310-U5FF`, `BIOL-310-U6WW` and `BIOL-310-R5FF`; **its current-term part
  is empty**. So reach into prior terms is proved by value, not by the legend:
  every week's default-set figures equal literals that only the three
  prior-term sections can produce. The literals were derived independently, by
  SQL over the raw `answer` rows of those three Spring 2026 sections — not
  through the benchmark views and not through the report API. They are:
  instructor means 4.0862, 3.9455, 4.2545, 4.0000, 3.9492, 3.9286 and
  course means 4.0345, 3.8000, 4.0909, 4.1379, 3.8136, 3.8214 for weeks 1 to 6,
  and a week-6 workload mean of 9.375 and median of 9.5, compared within
  5e-5 because they are rounded to four places. With the prior term
  excluded, the set would hold 0 sections and every one of those figures would
  be withheld. The university member is asserted present and not withheld, and
  not as a literal, because CI's earlier specs write into other current-term
  sections. The page draws three lines in each panel.
- **When the university line shows on the seeded stack.** Under the sealing
  rule (ADR 0179), the hero's university line shows only while no current-term
  12-week undergraduate section outside the hero instructor's own sections
  holds answers in course weeks 1 to 6; answers in such a section form a thin
  complement and withhold the line, correctly. The drive states that premise
  in its `beforeAll` and fails naming it, rather than failing later as a
  missing line. In the seeded world the one person who teaches the hero also
  teaches `BIOL-215-R3WW`, so E4's exit story in R3WW does not withhold the
  hero's university line.
- **The thin cohort.** `BIOL-215-R3WW`'s default set is empty because BIOL 215
  has no lead-faculty mapping. Every default-set point and both workload
  default members are withheld in the payload, and the page shows each withheld
  treatment. This exercises the default-set treatments only; a week where the
  university line alone is withheld is not driven (carried).
  `instructor-report-benchmarks.spec.ts` gave the wrong reason for
  that emptiness in a comment, and the comment is corrected. The drive reads
  R3WW's report only and writes nothing into it, so E4's exit story
  (`scripts/seed_exit_story.py`) is untouched.
- **The student half, per breakdown decision 9.** E8's results view has not
  merged, so the literal two-line TrendDuo walk cannot be driven. The
  structural proof stands: E5-11's suite (the student schemas refuse an
  undeclared member, ADR 0175; the student routes are swept) is green against
  the same world, and the drive walks a student seat over two consecutive weeks
  (landing, survey read, submit, and the read after) and finds no
  benchmark-shaped key in any network response and no comparison element in the
  page. The instructor's own page in the same world is the canary that reads
  three lines. The literal walk is carried as E8's first obligation
  (`../e6/carried-from-e5.md`).

The drive's result is the CI run on the exit head, cited below.

The `epic-exit` review ran on bf729fc against a stack rebuilt from that code
and migrated to head. It re-ran the exit drive (3 of 3 passed). It recomputed
every default-set figure by its own SQL over the raw answer rows of U5FF,
U6WW and R5FF, and each matched the drive's literals and the served payload to
four places. It drove the named-set refusals as the dean: a wrong-level
member, a zero length, a malformed level and a blank name each got a 422, and a
seven-week set was accepted under the length-is-data ruling. It found no stale
CI tolerance.

**Its one finding that needed code was HIGH: the three lines were two.** On
the seeded world the university line equalled the comparison line at every
week. The freeze's earliest-close cutoff is set by the U1WW and U2WW cohort,
which has no answers, so no current-term answer counts. The university then
reduced to the same three Spring 2026 BIOL-310 sections that make up the
default set. The drive only counted university lines, so it could not see
this. The rules were right and the world was too thin. A fifth prior-term
section, `BIOL-215-U8FF`, was seeded (cb5f05f). It is a 12-week undergraduate
section on BIOL 215, which has no lead, so it joins the hero's university but
not its default set. The drive now requires, at every week, a university
figure that differs from the comparison figure and equals a value measured by
SQL over the raw rows of the four Spring 2026 12-week sections. The rebuilt
stack passed it 3 of 3.

Its other findings: SPEC, the boundary record and the hand-off were not in a
commit at bf729fc (they landed after it, so this is resolved at the exit
head); CI on the exit head (see below); the Merged column (filled); a local
`.env` written before the ruling still sets 15 respondents (carried as a note
in the hand-off); and no university-only withholding is driven (carried).

**One trap for anybody driving the demo by hand**, from the `lti-oidc` review.
Launching a prior-term placement without first setting the development clock
back into that term binds the context to Fall 2026, and a later launch then
meets a context collision that only a database edit undoes. This is by design
and already documented (ADR 0167, `scripts/seed_benchmark_history.py`'s
runbook, `tests/e2e/support/benchmarkWorld.ts`); it is named here because the
exit drive is where somebody will next meet it.

## SPEC §11 question 1, settled

The breakdown's decision 10 left the benchmark minimums at their configuration
defaults until this ticket. The seeded worlds were measured first: the hero's
default set holds three prior-term sections of 55 to 59 distinct students per
course week, and the respondent minimum decides nothing in the seeded world.
The owner settled the question on 2026-09-22: **3 sections and 10 distinct
respondents**, both still configuration. SPEC §11 records it in place, §5.1
states both minimums, `backend/app/config.py` and `.env.example` default to 10
(commit bee6b8e), and the fixtures written for 15 were resized and their
expected figures re-derived by hand (commit 81f497d). No record outside the
historical tickets, disputes and attempt logs still calls the values open.

## The reviews and their findings

**Stopping rule, declared in the reviewers' common brief before any finding
arrived:** confirmed HIGH and MEDIUM findings get tests-first fixes inside the
E5-14 pull request; LOWs are fixed trivially or carried with an owner and a
done-when; one re-verification pass over the fixes; no further round unless
something is red or a HIGH appears. Two HIGHs about behavior arrived in the
first pass, and round 2 fixed them. The pass over round 2 (ce9df73) found a new
HIGH in the fix itself, and each later check found another, so four more
rounds ran; each round declared its own stopping rule and fallback before its
check. The rounds are recorded below.

**prompt-eval: nothing found.** The epic's diff touches nothing under
`backend/app/ai`, `tests/evals`, the floors, or the Makefile. The summary
prompt takes only a stream and its comments, so no benchmark figure reaches a
prompt. Live evals were not run, because no input to them changed.

**The two HIGHs about what a reader can learn.**

- **A published comparison moved one student at a time** (`privacy-authz`).
  The set functions counted responses in windows that were still open, and the
  report recomputes on every read with unrounded figures. While a
  later-starting section's same course week was open, a published figure
  changed with each submission, and a simulation recovered one student's rating
  from the change in 969 of 1000 trials. The owner ruled on 2026-09-22:
  **freeze at close.** A comparison or university figure for course week *w*
  counts only responses fixed when week *w* closed. Built in round 2 as `_v003`
  bodies of both set functions that take a cutoff per course week, taken from
  the reported section's own close. The checks that followed found every
  reader-dependent cutoff wrong (below); the final cutoff (round 4) is the
  earliest week-*w* close among all sections of the reported section's term,
  length and level, whoever reads. Recorded in ADR 0178 and SPEC §5.1. The tests
  (`test_a_published_benchmark_week_never_moves_after_its_own_close.py` and
  `test_the_benchmark_set_functions_count_only_what_each_weeks_cutoff_had_fixed.py`)
  show a published week byte-identical before and after a submission into
  another section's open window, a revision there, and a response last changed
  after the cutoff, with a positive control and both sides of the
  `closes_at <= T(w)` boundary.
- **The university line could be subtracted down to a small group**
  (`spec-conformance`, disputing breakdown decisions 2 and 5). The university
  line includes the reader's own section and was sealed on its whole
  population. The reader knows her own section's count and sum, and the default
  set is drawn beside the university line, so subtraction could isolate a
  population below the minimums — for example her section of 14 plus two
  one-student sections. Round 2 sealed the university figure on its
  contributors other than the reported section, and on the complement
  (university minus the reported section minus the default set). Rounds 3 to 6
  reworked the seal into its final form (below): per instructor of the
  reported section, with the university line withheld unless every group that
  instructor could isolate — each lead's set less her own sections, and the
  rest of the university — is empty or meets both minimums. Recorded in ADR 0179, with the closure
  argument, and SPEC §5.1.

**The HIGH about a record.** `adr-docs-completeness` found that ADR 0164
hard-codes the length set (`CHECK (length_weeks IN (3, 6, 8, 10, 12, 15, 16,
18))` and `CALENDAR_LENGTHS`) while SPEC §2.2 says the calendar is
configuration, not code. The owner ruled that a named set's length is data: the
`CHECK` becomes `length_weeks >= 1`, matching `section`, `CALENDAR_LENGTHS` is
removed, and the form offers the lengths sections actually have. ADR 0180
records it and supersedes that part of ADR 0164.

**Fixed inside the epic** (rounds 2 and 3, tests first where a test could fail):

- data-model HIGH (a record) — migration `b4d7e2a91c58`'s docstring called its
  downgrade a true reversal; it deletes every named set. The docstring now says
  so.
- data-model MEDIUM — `pulse_app` held table-wide `UPDATE` on
  `comparison_set`, so a request could rewrite `created_by_person_id`,
  `created_at` or `id`. Now `GRANT UPDATE (name, length_weeks, level,
  updated_at)` through `comparison_set_write_grants_v002.sql`, with the
  `RUNTIME_BASE_TABLE_PRIVILEGES` and column-privilege equalities updated and a
  mirrored downgrade.
- data-model MEDIUM (performance) — one report read made six service calls,
  resolved the university population three times, called the rating function
  once per stream though one call answers both, and aggregated every week for a
  one-week workload figure. Now each population is resolved once per read and
  each set function is called once per population with every published week's
  cutoff.
- data-model LOW — `views_sql/queries.py`'s wrappers for the two set functions
  were unused and selected whole-week counts. Deleted with their dataclasses and
  the test that pinned them, which also closes `deferred.md`'s "two
  statements" entry.
- data-model LOW (in part) — a set name could be empty or blank. The table now
  carries `CHECK (btrim(name) <> '')`, and the request schema strips whitespace
  and requires at least one character, so a blank name through the route is a
  422 carrying the framework's field errors, by design (`api/leadership.py`'s
  docstring says so). Case-insensitive uniqueness is carried.
- invariant-coverage MEDIUM — nothing limited which module may name the
  benchmark relations, so a second service could call a set function with one
  or two section ids. A marked sweep,
  `tests/unit/test_only_the_benchmark_service_names_the_benchmark_relations.py`,
  allows only `app/services/benchmarks.py` to name the two set functions and
  the four cohort views, with planted-offender and near-miss controls, and it
  runs in the job a documentation-only diff cannot switch off (commit a9a7820).
- invariant-coverage MEDIUM — the two denial tests for the named-set routes
  sat outside the isolated invariant pass. Both are now marked.
- invariant-coverage LOW — `student-benchmark-exclusion.spec.ts` could be
  disabled in place with `test.skip` or `test.fixme`. The disabled-form sweep
  now walks `tests/e2e/**/*.spec.ts` too, with a planted control.
- invariant-coverage LOW — the set functions' signature and result columns
  were unpinned. A marked test now compares both `_v003` functions' arguments
  and result column names with the contract.
- spec-conformance MEDIUM — the length half of §5.1's matching had no test that
  failed without it. `test_a_comparison_population_matches_length_and_level_inside_one_leads_courses.py`
  plants a led course with sections of two lengths, both directions and both
  resolvers, with the level half as its sibling.
- spec-conformance LOW — the empty-set tests asserted only that a figure was
  not 9.0. They now assert `suppressed` and the chokepoint's own reason.
- spec-conformance LOW — false docstrings in `services/benchmarks.py` and the
  README's decision 4 said the preview uses term-axis figures; it answers two
  counts. Corrected.
- spec-conformance LOW — the README's Merged column and the seed fix #241.
  Corrected.
- a11y-copy MEDIUM ×4 — on the comparison-set form, arrowing through Level
  emptied the set and the notice cleared on return; the removal notice was not
  a live region; controls that vanish on save or delete left focus nowhere, no
  status line announced the result, and a route change did not focus the
  heading; and the leadership landing's link looked like text. Each is fixed
  with a component test beside it. The pass over round 2 found one more gap in
  the same family (spec-conformance MEDIUM): a save from the edit page
  announced nothing. Round 3 announces "Set saved." on the list it returns to,
  once, not again on reload.
- a11y-copy LOW ×4 — the comparison strokes thinned at narrow widths (now
  `vector-effect: non-scaling-stroke`); "no line this week" was shown for a
  series absent all term (now "no line on this chart"); the preview read "1
  courses" (a singular entry); and the disabled Save button was not described
  (now `aria-describedby`).
- adr-docs-completeness MEDIUM — the design brief mapped the comparison lines
  to `--mist`, which measures 2.58:1 on paper, while the code ships
  `--spruce-60` at 5.18:1. The owner ruled for the brief edit, and
  `docs/DESIGN_BRIEF.md` now names `--spruce-60` with the reason.
- adr-docs-completeness MEDIUM — the root README's seed descriptions were stale
  (three sections in one term, fifteen courses, eight unmapped) and had no
  runbook for the prior-term world. Rewritten from the code.
- adr-docs-completeness MEDIUM — no record said that a course with no lead has
  no default set, that a course with two leads takes the union of both leads'
  courses, or that invalid responses are counted. ADR 0166's amendment
  records all three.
- adr-docs-completeness MEDIUM and lti-oidc LOW — stale comments saying
  leadership writes carry no CSRF check "until E5-06 lands"
  (`frontend/src/lib/session.ts`, `frontend/src/api/leadership.ts`). Trimmed.
- adr-docs-completeness LOW ×4 — ADR 0158's "five and fifteen" (the inventory
  holds eleven prefixes); ADR 0173 and `comparison_sets.py` citing a
  `benchmarks.py` docstring claim that does not exist; the README's E5-06
  scoping line and decision 1's §13 (the sentence is in §8); and the stale
  comments in `StatPair.tsx` and `comparisonSetFixtures.ts`, whose refusal text
  now matches the server's `set_unavailable`. Corrected.

**Carried** (each in `../e6/carried-from-e5.md` with an owner and a
done-when):

- privacy-authz LOW, a decision it disputes — the named-set figure functions
  take no reader and no purview, and ADR 0173 lets every leader read every set.
  Rendering a named set to a Lead Faculty member would be a sibling lead's
  course report by another road. E9, with purview.
- invariant-coverage LOW — generative sibling isolation over named sets. E9.
- data-model LOW and spec-conformance MEDIUM — three cohort views are granted
  and unread, and the rating term-axis view has no service read at all, so
  breakdown decision 7's "views and service reads" was only half true. The
  decision is amended in the README; the read and the three views go to E9.
- data-model LOW (the rest) — case-insensitive uniqueness of set names.
- spec-conformance LOW — named-set writes are not in the audit log (ADR 0174).
  E10.
- a11y-copy LOW ×2, older patterns — chart data tables that only a screen
  reader reaches, and input borders at 1.30:1. The next epic with UI work.
- adr-docs-completeness LOW — PR #238's "proposed, not done" pair: `_person_of`
  copied in `api/leadership.py` beside `api/instructor.py`, and a third course
  label composer. Joined to the course-label entry.
- a11y-copy, from the frontend round — the hero line keeps its scaling stroke,
  because its draw-in animation dashes along `pathLength`, which
  `non-scaling-stroke` would break. Carried.
- The frontend round's process defect — `.claude/hooks/deny-test-edits.sh`
  computes paths from the main checkout, so its exemption for frontend
  component tests misses inside a worktree. A `process/` pull request.
- From the checks over the fix rounds: snapshots across terms; membership
  resolved at read time, now wider (a late-synced, earlier-starting section of
  the same length and level moves the population cutoff for published weeks,
  MEDIUM inside the residual); and the submit-at-close race. Two readers
  pooling what they know is recorded as out of scope, not carried: §4.1's
  threat model is one reader.
- spec-conformance LOW, from the pass over round 2 — the exit drive shows the
  default-set treatments only, not a week where the university line alone is
  withheld.

**Closed outside this pull request:** the adr-docs-completeness HIGH, MEDIUM
and LOW about process records on `main` (#245, which the epic branch took in
#247 after the reviewed commit) — dated markers in `CLAUDE.md`,
`CONTRIBUTING.md`'s step 5 and lane text contradicting the new merge rule, and
ADR 0004's agent count. None was in E5's diff. PR #248 fixed all three and
merged to `main` as 0a9f81a: the markers are gone, `CONTRIBUTING.md` agrees with
`CLAUDE.md`, and ADR 0004 names sixteen agents.

**Not checked, as the reviewers reported it:** `lti-oidc` did not run the
Playwright benchmark specs (they share the development clock) and did not judge
whether leadership should reuse the CSRF refusal copy. `data-model` did not run
`alembic check` or the downgrade round trips at d1eaeff. The fix round ran them
on its own revision, `a3f6c1d8e5b7`, against a scratch Postgres: `alembic
check` clean; upgrade, downgrade one step and upgrade again give an identical
catalog snapshot; and a downgrade with a 4-week set stored refuses loudly,
because the old length list cannot hold it. `alembic check` was clean again
after every later round.

## The re-verification pass over the fixes

**The pass over round 2, on ce9df73.** Three fresh reviewers read the fix
commits: `app-security`, `privacy-authz` and `spec-conformance`.

- `app-security`: nothing found. It checked the migration's grants (four new
  definer columns, none a person's; the column-grain `UPDATE`), a downgrade that
  fails loudly on a length outside the old list, the pinned `search_path`,
  `EXECUTE` to `pulse_app` only, mismatched arrays counting nothing, cutoffs
  derived on the server with a naive time refused, CSRF on the three writes,
  and the name rules.
- `privacy-authz`, **HIGH** — round 2 cut each report at its own section's
  close. An instructor teaching sections A and B of one cohort, with staggered
  starts, therefore saw two snapshots of one population frozen at different
  instants, and the difference isolated whatever closed between them. **MEDIUM**
  — "everyone but the reader" excluded only the reported section, not every
  section the reader teaches. Both went to round 3.
- `privacy-authz`, MEDIUM — a published figure still moves if membership
  changes after publication (a lead mapping, a section's length or start
  date), because populations are resolved at read time. The `benchmarks.py`
  docstring that said a figure depends only on rows fixed before its cutoff is
  corrected; freezing membership needs the owner's ruling and is carried.
- `privacy-authz`, LOW — `submissions.py:512` reads the clock before the
  commit, and the cutoff is inclusive, so a submission racing the close can
  land either side. Carried. LOW — ADR 0178 was cited before it existed; it
  exists now.
- `spec-conformance`, MEDIUM — the exit drive's university assertion depends on
  the complement holding no answers (now a stated premise, above); SPEC §5.1
  had to be amended for the freeze and for length as data (done: the freeze
  narrows "regardless of start date"); and the edit-page save announced
  nothing (round 3). LOWs: record how the literals were derived (above), the
  blank-name 422's docstring (fixed), and the drive's missing
  university-only treatment (carried).

**The battery on ce9df73:** 76 mutations, 73 killed, 3 survivors, each then
pinned tests-first in round 3: FE09a (opening a delete confirmation must clear
a stale announcement), X1 (a cutoff with no time zone is refused) and X2 (a
course week with no cutoff is refused loudly), each with its accepted twin.

**Rounds 3 to 6: the orchestrator's rulings while the owner was away**,
flagged for the owner's review at the epic pull request. Each only ever
withholds more. ADRs 0178 and 0179 carry the full path; in short:

- **Round 3** (to d7b4561). The reader group *R* — every section taught by
  anyone who teaches the reported section — got one cutoff (the earliest week
  close among its sections in the term), and the seal moved from the reported
  section to *R*. A draft that removed *R* from the populations was withdrawn
  before it was built, because the hero's instructor teaches its whole default
  set. The round-3 battery ran 22 rows: 16 killed, 3 equivalent, and 3 real
  survivors, which fed round 4 — C3 (deleting the cutoff's term filter
  survived, because the prior-term tests only asserted "withheld"), B7 (what
  "empty" means for a workload remainder with no hour-reporters) and A3a (which
  rule a section with no instructor falls under).
- **The re-check on d7b4561** found two HIGHs, both from co-teaching. The seal
  assumed the reader knew all of *R*, but each co-teacher knows only her own
  sections; a scratch test showed a default set "empty after *R*" that was two
  sections and six people after one teacher's own (verified). And *R* differs
  between two co-taught sections, so one reader could meet two cutoffs
  (inferred). It found sound: the single-instructor staggered case, cross-week
  reads, and `reader_group_section_ids` never reaching the wire.
- **Round 4** (to b2579f9), with a stopping rule declared first: one more
  check, and on another HIGH in sealing or freezing, fall back to prior terms
  only. The cutoff became reader-independent — the earliest week-*w* close
  among all sections of the term, length and level — which removes the
  within-term snapshot class. The seal became per person: for each instructor
  *p*, the population minus every section *p* teaches, and for the university
  line also minus this report's default set, must be empty or meet both
  minimums. "Empty" is zero contributors to that figure, so an hour-less
  workload remainder is empty (B7); a section with no instructor gets only the
  population's own minimums (A3a); `authz.reader_group_section_ids` is
  removed. The round-4 battery ran 22 rows. C4, C5 and C6b fed round 5. C3 is
  equivalent in practice unless two terms start within one section length of
  each other, and is recorded as that; the cutoff's term filter is pinned by a
  current-term figure whose value a same-length-and-level prior-term section
  leaves unchanged.
- **The final check on b2579f9** found one HIGH, verified through the report
  route: a reader teaching sections under two leads sees both leads' default
  sets and the university line at one cutoff, and university minus both sets
  minus her own sections was an unled section with one student, whose rating
  the arithmetic recovered. It rated a MEDIUM inside the carried membership
  residual (a late-synced, earlier-starting section of the same length and
  level moves the population cutoff for weeks already published), and ruled
  two readers pooling out of scope (§4.1's threat model is one reader). It
  found the reader-independent cutoff, the per-person rule, the no-instructor
  case and the per-read cache sound. The declared fallback, prior terms only,
  was not used: it fixes snapshot timing, and this was set algebra between
  populations at one cutoff, which happens with prior-term data too.
- **Round 5** (to 0361fb3). The university remainder removes the default sets
  of every section *p* teaches in the reported term at its length and level,
  not only this report's. ADR 0179 records why that closes the class: for one
  reader, one population, one term and one week, every figure she can see
  combines disjoint atoms — her own sections, each lead's set less her own,
  and the rest of the university — and every atom but her own is empty or
  meets both minimums. A new stopping rule was declared first: one check aimed
  at that argument; if it breaks, withhold the university line entirely, carry
  and flag.

- **The check aimed at the closure argument, on 0361fb3**, found one HIGH,
  verified through the report route: the university seal never checked the
  lead atoms themselves. With the rest of the university empty, the university
  minus the reader's own sections minus the default set she is shown was a
  second lead's thin set of one student, whose hours the arithmetic recovered
  exactly (152 − 83 − 28 = 41). It found sound: two leads on one course are
  impossible (a unique key on the course), the default set leaves out only its
  own section, only teaching instructors reach a report, the cutoff is
  reader-independent, rating and workload figures do not combine, different
  weeks are disjoint, and a grant's removal is inside the carried membership
  residual. The declared fallback — withholding the university line entirely
  — would have broken the exit clause's three lines per panel, and the fix is
  exactly what the closure argument requires, so it was not used.
- **Round 6** (to bf729fc). The university line also checks each lead atom:
  for each instructor *p*, each default set of *p*'s sections alike in the
  term, less *p*'s own sections, must be empty or meet both minimums. With it,
  the argument closes: the university is shown only if every atom but the
  reader's own is empty or meets both minimums, and a default-set figure only
  if its own lead atom does, so every combination the reader can compute is
  over atoms that meet them. Tests first
  (`test_the_university_remainder_removes_every_default_set_its_reader_sees.py`:
  a thin lead atom withholds the university line on both of the reader's
  reports, and an empty one leaves it shown); the named mutation is the
  round-5 code, which did not check the lead atoms.

**The stop.** No review round followed round 6, by the rule declared with round
5 and by the decision recorded with the check on 0361fb3: the owner reviews the
whole seal and the cutoff at the epic pull request, where both are flagged as
the orchestrator's rulings made while the owner was away.

## The verification, in kind

- The exit head: a record cannot name the CI run of the commit that carries
  it, so the run on the final exit head is resolved by id (status, conclusion
  and head SHA) and recorded in PR #249's body. The last run before the
  records landed, 35828315690 on e0483a9, was green in every job, the exit
  drive included.
- Local gates after round 6, from the attempt log: the backend suite 3902
  passed and 0 failed; the invariant pass 542 passed, with
  `check_invariants.py` and `check_invariant_assertions.py` (389) both OK;
  vitest 285 passed; ruff, the four mypy runs, both `tsc` runs and eslint
  clean; `alembic check` clean.
- Batteries: ce9df73, 76 rows, 73 killed, 3 survivors (FE09a, X1, X2), all
  pinned; round 3 (d7b4561), 22 rows, 16 killed, 3 equivalent, 3 real
  survivors fed into round 4; round 4 (b2579f9), 22 rows, with C4, C5 and C6b
  fed into round 5 and C3 recorded as equivalent in practice. Round 5
  (0361fb3), 6 rows: 3 killed (one only by the full suite) and 3 survivors,
  the term, length and level filters in `_alike_in_this_term`. Each
  survivor could only withhold more. All three are now pinned by tests in
  `test_the_university_remainder_removes_every_default_set_its_reader_sees.py`
  (ea2230e), and each mutation was seen killed by its own test and no other.
  Round 6's named mutation, lead atoms unchecked, was killed by the
  implementer's pre-fix restore: 2 red, then all 7 green.

**Invariant counts, in both currencies, never compared across them.** The
isolated CI pass's run count: **358 at the merge-base → 441 at the epic's last
content merge (d1eaeff) → 542 after round 6** (the local isolated pass; the
CI figure is in the run above). The assertion checker's static count of marked
test functions: **288 → 340 (+52, none removed) → 389.** E4 recorded 356 and 286 after its own rounds; the
difference of two in each currency is work that reached `main` between that
commit and E5's merge-base.

## `PERSON_TABLES`, re-asked of the tables E5 added

`PERSON_TABLES` is unchanged, and the answer is correct for both of E5-01's
tables. `comparison_set` is one hop from `person` through
`created_by_person_id`, and `comparison_set_member` is two, so the person walk
reaches both. Both sit in `REACHED_TABLES_THAT_CARRY_NOTHING`
(`tests/integration/test_identity_column_marker.py`) with pinned column tuples:
a set is a statement about courses, its one person is the creator as a foreign
key whose identity sits on `user_identity` (which `pulse_app` cannot read), and
no student is reachable from either table. E5-14 adds a `CHECK` and narrows a
grant but adds no column, so both pins still hold and would expire the entries
the first time either table grows one.

## The session-read sweep, shown by planting

A session read from the request was planted in E5's two new route-serving
modules, `backend/app/services/benchmarks.py` and `backend/app/api/leadership.py`,
and `tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
went red; restored, it is green and the tree clean. E5 added no route-serving
package outside `backend/app/`, so the sweep's two disclosed limits stand as
disclosed and are re-carried.

## The TypeScript 7 watch

Checked 2026-09-22: `typescript-eslint`'s latest is 8.70.1, and its peer range
is still `typescript >=4.8.4 <6.1.0`, so TypeScript 7 was not admitted during
E5. Installed pins: TypeScript 6.0.3, typescript-eslint 8.70.0. Re-carried
with the date.

## Disputes

Two were raised in this ticket, both ruled for the code, and recorded in
`../../disputes/`:

- `E5-14-01` — the freeze needs the benchmark definer to read four more
  columns (`response.last_submitted_at` and `survey_window`'s `section_id`,
  `week_id` and `closes_at`), and the definer equality still listed eighteen.
  The test was out of date; ADR 0165 was amended first to name the four, and
  the expected set moved to twenty-two pairs over seven tables.
- `E5-14-02` — under round 3's revised ruling, two sections one instructor
  teaches cannot have byte-identical default-set members, because each default
  set holds the other section: two populations by design, whose difference is
  the reader's own sections. The assertion was replaced by one that holds:
  their university figures at a shared week are identical.

## The per-PR security review of E5-14

`app-security` read the fix diff on ce9df73 fresh and found nothing. It checked
the migration's grants (four definer columns, none a person's; the
column-grain `UPDATE`), a downgrade that refuses loudly on a length outside the
old list, the pinned `search_path` and `EXECUTE` to `pulse_app` only,
mismatched cutoff arrays counting nothing, cutoffs derived on the server with a
naive instant refused, CSRF on the three writes, the name rules, and no new
logging, secret, dependency or eval surface. Rounds 3 to 6 changed only how
the service seals and cuts figures, and each was read by a privacy-authz check
(above); the security review of the final diff is recorded in the pull
request body.
