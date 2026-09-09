# E4 boundary review

The §14.2 item 6 record for E4 (the instructor Monday report), written by
E4-15. E4 is not a ⚠ epic, so three boundary reviews were mandated; the four
moved specialist reviewers ran beside them (ADR 0004's standing arrangement),
and a whole-epic `privacy-authz` pass ran as this exit ticket's own mandate —
E3's retroactive lesson applied in the epic built almost entirely of read
paths. Eight reviews, all with fresh contexts, all on commit 524d3c6 against
the epic's cumulative diff (merge-base with `main`: 6121135). The fix rounds
they generated landed as commits 24afc32 through 1ed47f9 on PR #213.

**The roster, reconciled against the review skill's own trigger table**
(`.claude/skills/review-pr/SKILL.md`): `epic-exit`, `invariant-coverage`,
`adr-docs-completeness` (mandated by §14.2 item 6); `data-model`, `lti-oidc`,
`a11y-copy`, `prompt-eval` (the four the skill moves to the boundary);
`privacy-authz` whole-epic (the ticket's own addition). `threat-model` did
not run: §14.2 item 6 mandates it for ⚠ epics and E4 is unmarked — named
here so its absence reads as a decision, not an omission. `spec-conformance`
and the per-PR reviews ran on every one of the epic's nineteen ticket PRs.

## The exit clause, verified against the running system

SPEC §14.3 E4: *an instructor opens a real Monday report for a seeded
section with a diverging two-stream story.* Driven, not asserted. The exit
proof is `tests/e2e/exit-instructor-report.spec.ts` — eight tests in their
own Playwright project, ordered after every other project — over the story
`scripts/seed_exit_story.py` writes for `BIOL-215-R3WW`: six weeks, the
instructor stream rising 2.0 → 4.5 while the course stream falls 4.5 → 2.0,
two disjoint below-threshold weeks whose seven held comments cross the
cumulative release gate, one deliberately invalid comment, and workload
values whose mean and median differ.

The exit reviewer re-ran the drive (8/8) and then recomputed every figure
from the database rows rather than from the drive's expectations: per-week
rating sums and counts for both streams, distributions, the week-6 workload
mean 10.375 and median 9.5, response and validity rates including the week-5
7-of-8, and the enrolled denominator of 10 with the instructor excluded by
her staff assignment. All matched the payloads. The launch was walked from
the mock LMS through the section menu to the report; week navigation paged
6 → 1 with the ends disabling and focus landing on the heading; the release
appeared in week 6 only, seven comments, no week, no timestamp, no author,
no id at any depth; every week's `comparison` member was present and
suppressed with no benchmark key anywhere — the README's exit-mapping row
checked against the payload, not the ticket. CI tolerances: none stale, no
`continue-on-error`, the invariant checker's skip/xfail/empty-collection
refusals confirmed in the workflow.

One clause failed as first measured, and it is the boundary's headline
finding below: the small-N week's network response carried the withheld
comments' opening words inside the summary member.

## The reviews and their findings

Stopping rule, declared in the work order before any finding arrived:
confirmed HIGH and MEDIUM findings get tests-first fixes inside PR #213;
LOWs are fixed trivially or carried with an owner and a done-when; one
re-verification pass over the fixes with targeted re-mutations of what the
rounds touched; no further round unless something is red or a HIGH appears.
A HIGH appeared, so a second round ran under the same rule; it held.

**prompt-eval: nothing found**, with its checked list — the four eval-case
families with their offline breach proof, no floor lowered anywhere in the
epic's diff (the summary floor is a first-time DEFERRED slot, ADR 0149,
disclosed in the evals README), held-content exclusion proven at the gateway
boundary, the single-shot §7.4 boundary intact, no regeneration path.

**The one HIGH — found independently by two reviewers, one defect.**
`privacy-authz` (whole-epic) traced it as a de-anonymization channel: a
quiet week's stored summary paraphrases the very comments the cumulative
release later shows verbatim and week-stripped, so prose-matching
re-attaches a released comment to its week, and beside the gradebook's
per-week ledger the candidate set collapses below the floor ADR 0153
claimed. `epic-exit` measured it live: the development provider's summaries
quoted the first six words — 32 to 37 characters — of every withheld
comment, and the drive's 40-character absence check missed by 3 to 8.
§5.1 mandates the small-N summary and §4 mandates the release, so no fix
inside the epic could satisfy both records as written; the conflict was
surfaced and ruled on 2026-09-09: **below the threshold, a summary names
themes only and may not reuse the commenters' own word strings.** Built in
this PR as `summary.v2.md` (both prompt versions live, the stored
`prompt_version` saying which mode wrote each row), a store-time guard
refusing any small-N summary whose prose or theme labels share a
20-character normalized run with a fed comment (refuse-and-retry, the ADR
0148 family), the development provider's themes-only branch, a themes-only
eval case with its breach variant, and the drive's absence bound tightened
from 40-character prefixes to the guard's own 20. SPEC §5.1 carries the
ruling dated; ADR 0162 records the construction; ADR 0153's amendment
records the channel, the corrected floor claim, and the honest residual —
theme-level correlation remains, and the record now says so.

**Fixed inside the epic** (fix round 1, tests first):

- invariant-coverage HIGH ×2 — the only section-scope assertion for the
  comment reads, and the release gate's three-legged module, both sat
  outside the §4.1 isolated pass; the marked payload test compared the
  payload against the same service it would leak with. Fixed: nine modules
  and tests marked into the pass with their reasons, and a new marked
  payload-boundary test plants distinctive comments in two sections one
  instructor teaches and asserts neither report carries the other's text,
  both directions. The release-gate module's own boundary pairs already
  drove both legs one-below and at threshold; the mark was the gap.
- invariant-coverage MEDIUM — the first surface whose §4.1 rendering halves
  live in component tests, which sit in no guarded pass. Fixed in the cheap
  half: a marked sweep refuses `.skip`/`.todo`/disabled patterns in
  frontend test files; the structural half (a marker convention or
  collection floor for the frontend pass) is carried with the standing
  collection-floor entry. The backend payload boundary remains the enforced
  §4.1 wall; the component tests are defense in depth.
- data-model MEDIUM ×2 — the release read's missing indexes
  (`ix_release_batch_member_batch_id`, `ix_release_batch_section_id_term_id`)
  and the missing composite foreign key pairing a batch's section with its
  term, whose ADR 0146 rejection had borrowed a cost argument that does not
  hold for a table already carrying `term_id`. Fixed: migration
  e5a2b81c47d3, tests first (index existence and the pairing catalog); ADR
  0146 corrected dated.
- epic-exit MEDIUM — the report's enrolled denominator was a second reading
  of the enrollment window that ignored `lms_window_start`, contradicting
  ADR 0147's own argument and disagreeing with grading on the seeded
  section. Fixed: the window resolution promoted to one home,
  `app/services/enrollment_windows.py`; grading's whole suite green
  unmodified is the proof the promotion preserved behavior; the report now
  counts a platform-dated late add from the platform's date. ADR 0161
  records the promotion; ADR 0147 corrected dated.
- privacy-authz MEDIUM — the page narrowed moderation status and stream
  against a vocabulary the wire never sends, so the first real
  `flagged_collapsed` comment would have rendered as a plain published
  card. Fixed: the mapping reads the wire's spellings, the fixtures moved
  to the wire's shape, and component tests pin the collapsed treatment
  (chip, disclosure closed, words out of the DOM until reviewed) and the
  stream chip both directions.
- a11y-copy HIGH + MEDIUM — the excluded-comment text and its notice
  rendered in a token measuring 2.58:1, and the trend's hero line, terminal
  dot and tick sub-label sat under the graphical floor. Fixed: spruce-60
  and marigold-deep per the tokens file's own focus-ring precedent, the
  legend swatch moved with the line it names, and source-level token pins
  refuse a quiet revert; `design/tokens.css` itself is untouched and its
  stale mist recommendation is noted in the stylesheet that departs from it.
- data-model MEDIUM (by record) — the Monday summary walk is serial: 500
  sections × 2 streams ≈ 33 minutes at §7.4's p95 budget against §10's
  30-minute line, arithmetic no record carried. ADR 0154 amended dated;
  E13's load test owns the revisit; carried forward.
- lti-oidc LOW — E4-14's working purge made an unrecorded lifetime coupling
  load-bearing (replay after a purged nonce is bounded only by the ledger
  outliving the in-flight state). Fixed trivially: a unit test pins
  `NONCE_LEDGER_LIFETIME_SECONDS > IN_FLIGHT_LIFETIME_SECONDS` and both
  constants' comments name each other.
- The e2e world-reset helper owed the release and moderation tables their
  deletes (the RESTRICT edges are correct; the helper caught up).
- Record corrections: the README build-order table's E4-12 cell; the
  deferral entries this file's cleanup pass closes; the stale owner line on
  the course-label entry; ADR 0142's consequences cross-linked to the
  third Playwright project (folded into ADR 0160).

**Carried** (each in `../e5/carried-from-e4.md` with owner and done-when):
the serial summary walk (E13); the reveal door's predicate narrowing once
the harm vocabulary exists (E6, from data-model's LOW); the released list's
stream partition noted in ADR 0153's what-would-change clause; item 4's
score-sort half awaiting E9's first sortable surface; the frontend
confidentiality pass's structural floor (with the standing collection-floor
entry); the summary eval floor's DEFERRED slot (E10's floor-setting family).

**Accepted as argued, recorded**: the no-store pair deliberately unmarked
(caching hygiene, not a §4.1 line — with invariant-coverage's partial
disagreement noted: the scenario both docstrings name is a
shared-machine disclosure); the histogram and rate bar's numeric
`role="img"` labels as a deliberate divergence from the trend chart's
table pattern.

## Disputes

Two were raised in this ticket, both sustained on measurement and recorded
in `../../disputes/E4-15-0{1,2}.md`: a prompt comparator whose normalization
erased the discriminator its own filters needed (control unpassable,
subject vacuous — repaired to one normalization), and a themes-only eval
case that joined the registry without the faithful answer and breach
variant every case owes (supplied). Six ticket-level disputes predate the
exit and stand ruled in their files.

## The verification, in kind

No green believed on its author's word, twice over.

- Build round: CI run 34298717151 on 524d3c6 resolved by id — completed,
  success, head exact; totals reconciled to the logs (pytest 3380,
  invariant 306, Playwright 78 = 63/7/8, vitest 113). Battery of 27 rows:
  22 killed (20 by the named killer, 2 by the seeder's own refusal —
  mechanism recorded), 2 detected at collection, 3 fresh-database residue
  with re-run recipes, 0 unaddressed survivors. One battery finding was a
  record correction: a manifest row's "five or fewer" claim was wrong — the
  mutation shifts the boundary in the safe direction, invisible to this
  story, and E4-04's own threshold test is what kills it.
- Fix rounds: CI run 34310142332 on 1ed47f9 resolved by id — completed,
  success, head exact; totals reconciled to the logs (pytest 3401,
  invariant 356 ran with 286 asserting, Playwright 78 = 63/7/8, vitest
  120). The eval-floor job ran live (108 provider requests): validity
  precision 1.0000 against its 0.92 floor and recall 0.9815 against 0.9;
  the summary and threat slots reported `deferred / ungraded` as their
  records stage them — so nothing in CI yet grades the themes-only family
  against a real provider, a fact carried forward with the summary-floor
  entry. The targeted re-mutation battery ran ten rows over what the two
  rounds touched: eight killed by their named killers (the inverted guard
  scope, the unpassed mode flag, the forced prompt version, the vocabulary
  revert, the token revert, the enrollment-window revert, and two original
  rows whose subject moved — suppression off and the sliced release, both
  killed by the drive at the payload). Two survived and were covered
  rather than accepted: the guard's bound was untested at exactly its own
  value (the near-miss pair straddled 19/21), and the theme-label leg had
  no killer anywhere — the development provider labels themes by ordinal,
  so no drive could ever meet a comment fragment in a label. Both gaps
  were closed tests-first in 9b175e8 and both previously-surviving
  mutations were re-run to red against the new tests, tree restored and
  byte-compared after every row.

Invariant counts, one currency (the isolated CI pass's run count, the same
currency E3's 238 was recorded in): **238 at E3's close → 306 at the
epic's last content merge → 356 after the boundary rounds.** The assertion
checker's static count (286 marked test functions) is a different currency
and is deliberately not compared against any of the three.

## Criterion 5 — every cited CI run, re-resolved by id

All twenty run ids cited in the epic's PR bodies (#184–#195, #205–#212)
were re-resolved on 2026-09-09: nineteen cited as green resolve completed/
success with their claimed heads; the twentieth, 34062392613 in #184, is
cited as a deliberate planted-red proof ("the gate was watched refusing")
and resolves completed/failure on exactly the head the record names — the
citation's claim, confirmed. One eleven-digit number in #192's body is a
floating-point value in prose, not a run id. The runs this record itself
cites are 34298717151 and 34310142332; the run on the branch's final head
is resolved by id in the pull request body, where the ready-marking
asserts it.

## Criterion 6 — the de-anonymization statement, verified

The carried entry's done-when asked E4 to state in writing that its
suppression holds against a reader who also has the gradebook open, or to
change what it suppresses. The whole-epic privacy pass re-read ADR 0153
against what shipped and found the statement did not hold: two of its three
floors were true of every batch the cutter can write, and the third fell to
the summary channel above. The answer was to change what it suppresses —
the 2026-09-09 ruling — and ADR 0153's amendment now carries the corrected
statement: the batch floors hold at the payload; the quiet-week summary may
not reuse a commenter's words, enforced at store time; the residual is
theme-level correlation, named. The entry's E4 half closes on that
statement; E6 still owes its own half for the moderation views.

## Criterion 6's sibling — `PERSON_TABLES`, re-asked of everything E4 added

`PERSON_TABLES` is unchanged, and the walk answered the question in the
guard itself: `weekly_summary` (id, section_id, week_id, stream,
summary_text, response_count, themes, prompt_version, model_id,
generated_at) and `release_batch` (id, section_id, term_id, cut_at) are not
reached by the person walk and their column tuples are pinned;
`moderation_state` (id, answer_id, state, decided_at) and
`release_batch_member` (id, batch_id, answer_id) are reached through
`answer` and sit in `REACHED_TABLES_THAT_CARRY_NOTHING` with pinned tuples
that expire the entries the first time either table grows a column. The one
column E4 added to a pre-existing table, `question.stream`, is a two-token
report-group label reaching no person. `summary_text` carries the same
judgment `answer.comment_text` does: prose that could quote a name, held by
the views' identity separation rather than by a marker.

## Criterion 7's sibling — the session-read sweep, shown by planting

A `session_from_request` import was planted in the epic's two new
route-serving modules, `backend/app/services/reporting.py` and
`backend/app/api/instructor.py`, in one run;
`tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
failed on its offender assertion, naming both planted modules and the
alias each hid behind. Restored, the sweep is green and the tree clean.
One incident worth its sentence: the first plant silently failed to land
and the sweep read green — the demonstration only counts because the
plant's landing was verified before the run, which is `docs/MISTAKES.md`
entry 16's rule applied to a demonstration rather than a mutation. The
sweep's two disclosed limits stand and are re-carried.

## The TypeScript 7 watch

Checked 2026-09-08: `typescript-eslint` latest is 8.70.0, peer range
`typescript >=4.8.4 <6.1.0`; 7.x was not admitted during E4 and the wait
re-carries dated. Installed pins unchanged (6.0.3 / 8.68.0).

## The per-PR security review

Recorded in a closing commit after the review ran; see the section
appended below and the pull request body.
