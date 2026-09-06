# E3 boundary review

The §14.2 item 6 record for E3 (grade passback), written by E3-08. E3 is not
a ⚠ epic, so three boundary reviews were mandated; the four standing
specialist reviewers ran beside them, as at the E2 boundary. All seven ran on
commit 6ebc4a8 with fresh contexts; the fix round they generated landed as
commits 3b10536 through 981813b on PR #178.

## The exit clause, verified against the running system

SPEC §14.3 E3: *the mock-LMS gradebook shows correct percentages across
enrollment edge cases.* Driven, not asserted. The exit proof is
`tests/e2e/exit-grade-passback.spec.ts` — a six-position clock drive against
the Compose stack in its own Playwright project, run after every other spec —
plus `tests/integration/test_the_results_container_and_the_mock_log_agree.py`
(criterion 2) and
`tests/unit/test_no_backend_module_reads_the_mock_only_score_log.py`
(criterion 3).

The exit reviewer re-ran the drive independently, read
`GET /mock/posted-scores` itself, grouped it per (context, user), and
hand-checked every exit-table row against §3.4's calendars rather than
against the assertions: 100% for the full record; 16.0 with `Week 4: 4 of 5
items` beside four zero lines still in the denominator; the platform-dated
late add's ledger opening at week 4; the undated member identical to a
day-one classmate on score, maximum and ledger; the member first seen in a
later sync opening at week 2; the seeded already-Inactive member absent from
every entry; the amended drop frozen at 16.0 while classmates re-posted; and
the absent-versus-posted-zero rule at the first position. The one non-exact
value (28.6 = 10/35, half up) exercises the canonical rounding on the wire.

Exit-table row 7 is driven in two halves, per the ruling in
`../../disputes/E3-08-02.md`: a member the platform already reports dropped
at the first sync is never enrolled and never gets a column (ADR 0095), and
the mid-drive drop proves the score stops updating with the last posted
value standing. The ticket's exit table was corrected to say so.

## The reviews and their findings

Stopping rule, declared before any finding arrived: confirmed HIGH and
MEDIUM findings get tests-first fixes inside PR #178; LOWs are fixed
trivially or carried with an owner and a done-when; one re-verification pass
over the fixes with targeted re-mutations; no further round unless something
is red or a HIGH appears. The rule extends the round to cover gaps the round
itself introduces and forbids re-polish of accepted work. It held.

**prompt-eval** and **a11y-copy**: nothing found, each with its checked list
— no eval floor or prompt moved, no new model call, the refused-verdict set
a single import; the console controls natively keyboard-operable, the ledger
carrying counts and nothing else, exactly what ADR 0125's acceptance rests
on.

**Fixed inside the epic** (the boundary round, rulings R1–R9 in the PR):

- lti-oidc HIGH — the posted score never scaled to the line item's maximum,
  so an instructor editing the column's points corrupted every later post.
  Fixed: `scoreGiven` scales to the maximum read at post time; a
  nonpositive or absent maximum is walked past with a logged refusal; the
  max-100 case stays a byte-identical carry so ADR 0052's identity holds.
- data-model HIGH — `ags_call` was unindexed under the sweep's per-delivery
  read, and its model docstring ("nothing reads this table on a request
  path") had been falsified by this same epic. Fixed: migration c4a8e51db9f3
  adds `ix_ags_call_section_id_called_at` and `ix_section_term_id`; both
  docstrings corrected.
- invariant-coverage HIGH ×3 — the sweep-log and dev-trigger denial modules
  sat outside the §4.1 isolated pass, and the epic's new SECURITY DEFINER
  function was missing from the Care-refusal list. Fixed: both modules
  marked, the definer added; the isolated pass grew from 218 to 230 tests.
- epic-exit MEDIUM — the sweep posted a participation score for the
  instructor in every section; `_live_enrollments` selected on dates alone.
  Fixed: delivery excludes members holding a section-scoped staff
  assignment (§3.4 makes the score a student's; the two-hat person is still
  scored where they are the student; the ruling's original "holds a student
  role" phrasing was unimplementable — ADR 0028 gives students no
  assignment rows — and the working predicate is the exclusion).
- lti-oidc MEDIUM ×4 — reads requested a scope an ordinary registration may
  not hold (now the writing scope); one token grant per student (now one
  per section); token-refusal `nrps_call` rows set the tier-3 boundary (now
  filtered to rows that read a roster); and the line-item trigger was
  conditioned on this launch carrying a roster address (now keyed on the
  section the context resolved to, with a door-level guard driven through a
  new `no_roster_service` near-miss launch the mock signs).
- lti-oidc MEDIUM — newest-signs defeated ADR 0127's own rotation
  procedure against platforms that cache a key set. Fixed: the oldest live
  key signs; ADR 0143 supersedes ADR 0127 in part.
- invariant-coverage MEDIUM ×4 — raw comment text was selected into the
  worker (now a nullness predicate, and comment text joined the forbidden
  log sets); the sibling-lead gradebook denial was missing (written,
  invariant-marked); the AGS redaction denials sat outside the pass
  (extracted into a marked module, the originals deleted with pointers
  after a dropped-leg check); and the denial-name inventory was blind to
  the epic's module names (widened, then widened again after the
  re-verification battery — see below).
- epic-exit MEDIUM + adr-docs MEDIUM (one fact, found twice) — the roster
  sync's unbounded token dial was deferred only in merged PR prose. The
  record is durable now: `../e4/carried-from-e3.md` carries it with an
  owner and a done-when.
- Record corrections: the ticket's exit-table row 7 cell and the README's
  exit mapping (falsified by the E3-08-02 ruling), the README's Merged
  column, three module docstrings citing ADR 0132 for a ruling it does not
  contain, and the drive header's stale project-split sentence.

**Carried** (each in `../e4/carried-from-e3.md` with owner and done-when):
the roster-sync token dial's code fix; the gradebook's two strings outside
the copy inventory; `azp`/multi-audience handling and the per-launch JWKS
fetch (both pre-date E3); and the structural half of the denial-inventory
question, sharpened by the battery: `check_invariants.py` has no
collection-count floor, so a shrinking isolated pass passes both layers.

**Cleared by the reviews, explicitly**: NRPS paging and status vocabulary,
the Link parser, idempotent line-item creation under lock, retry identity
and monotonic timestamps, nonce/state handling, PKCE on the mock IdP; the
ledger's completion-counts boundary asserted mechanically in two
independent currencies; the new grants inside the marked equality
inventories; migrations reversible with the rotation downgrade's refusal
stated; no CI tolerance stale; ADR sequence 0124–0143 complete and indexed.

## Disputes

Four were raised across the ticket, all ruled on sources and recorded in
`../../disputes/E3-08-0{1,2,3,4}.md`: a whole-document equality over the
identifier that selected it; the seeded Inactive member's non-enrollment
(ADR 0095); a test constant naming a column the schema does not declare;
and a fail-open boolean carrying an assertion it cannot carry — that last
one is now MISTAKES entry 49.

## The verification, in kind

No green was believed on its author's word. CI was resolved by run id
against the exact head three times (33999804072 on bac63f4, 34001273838 on
6ebc4a8, 34007542530 on dc8aaae — each completed, successful, head matched).
Two mutation batteries ran: the exit proof's (seven kills, one predicted
survivor — the dev sync control's clock stamp, time-dependent by nature —
covered the same day by a deterministic pair asserting both clock
directions) and the fix round's (eight kills with every predicted near-miss
staying green, one genuine survivor — the denial-inventory shape gap —
closed and watched dying). Every mutation was verified landed before its
run and restored from snapshots.

## Criterion 6 — `PERSON_TABLES`, re-asked of everything E3 added

`grade_sync`: in `REACHED_TABLES_THAT_CARRY_NOTHING`
(`tests/integration/test_identity_column_marker.py`) with columns
(created_at, id, ledger_text, outcome, response_code, score_text,
score_timestamp, section_id, user_id) — E3-02's judgement, standing.
`ags_call`: not reached by the person walk — its single foreign key is into
`section`; columns (id, section_id, url, response_code, called_at).
Columns added to existing tables: `section.lms_ags_line_items_url` and
`section.ags_line_item_url` (service addresses), and `tool_signing_key`'s
rotation columns (key custody) — none holds or reaches a person. E3-08's
own migration added two indexes and no column. `PERSON_TABLES` is
unchanged; the structural source remains E13's carried item.

## Criterion 7 — the session-read sweep, shown by planting

A `session_from_request` import and call were planted in
`backend/app/services/grading.py` and `backend/app/lti/ags.py` in one run;
`tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
failed on its offender assertion ("These modules under backend/app read a
session out of a request themselves, which only ['api/deps.py',
'services/session.py'] may do"), naming the planted modules. Restored, the
sweep is green and the tree clean. The sweep's two disclosed limits stand
and are re-carried.

## The TypeScript 7 watch

Checked 2026-09-05: `typescript-eslint` latest is 8.69.0, peer range
`typescript >=4.8.4 <6.1.0`. 7.x was not admitted during E3; the wait is
re-carried dated.
