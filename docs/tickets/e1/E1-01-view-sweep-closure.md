# E1-01 — Close the §4.1 view sweep over aliases and join keys

**ID:** E1-01
**Branch:** `e1/view-sweep-closure`
**Depends on:** nothing
**Security-relevant (⚠ line-by-line):** the sweep's closure logic itself — a
guard that believes it is closed and is not is worse than the open guard it
replaces.

## Context

The reviewer self-test measured two blind spots in the §4.1 identity-separation
sweep (`tests/integration/test_identity_separated_views.py`), recorded as the
carried entry "The §4.1 view sweep is blind to an aliased identity column and to
join keys" in [`carried-from-e0.md`](carried-from-e0.md) — **its "done when"
governs this ticket**:

1. The sweep matches identity columns by output label. A view selecting
   `user_identity.identity_name AS respondent_display_name` exposes the name
   and matches no fragment.
2. `user.lms_user_id` is a stable per-person join key flagged by nothing —
   `lms_` is ADR 0014's ownership marker, not an identity marker — and a view
   returning it beside a comment lets an instructor resolve a student in the
   LMS in one step.

Neither is live: no such view exists. That is exactly why this ticket runs
first in E1 — the guard closes before the first epic capable of adding such a
view by accident writes any view at all.

Read first: the carried entry (its reproduction lives in the reviewer's writeup
and the fixture `identity-column-in-view` under `.claude/review-fixtures/`);
SPEC §4.1 and §8 (identity separation); ADR 0014, ADR 0022 (the two marker
prefixes and what each means); ADR 0041 (view files are immutable and
versioned); the "Adding a read view" rule in `CONTRIBUTING.md`.

## Scope

- The sweep detects an identity column **by lineage** — what the column *is*,
  traced to `user_identity` (or any identity-marked source per ADR 0022) —
  rather than by the label the view author chose. An aliased identity column in
  a planted view file fails the sweep with a message naming the source column.
- The set of columns `pulse_app` may read from each view is **enumerated**, so
  a new grant exposing a join key (`user.lms_user_id` or any equivalent stable
  per-person key) fails the sweep rather than passing it. The enumeration's
  inventory comes from somewhere the guarded structure cannot shrink
  (`docs/MISTAKES.md` entry 35's rule): derive the candidate set from the
  catalog, not from a hand-kept list in the test.
- Both closures carry their control case (entry 35 again): the sweep must
  *find* a planted aliased identity column and a planted join-key grant, in
  fixtures, before its green means anything. The planted cases mirror the
  reviewer fixture rather than being retyped from it (entry 3's canary rule).
- The existing sweep's passing verdicts on E0's real views are unchanged — this
  closes blind spots; it does not reclassify anything currently shipped.

## Acceptance criteria

1. A view file aliasing an identity column to an unmarked name is caught, with
   the source column named in the failure message.
2. A view exposing `user.lms_user_id` (or granting `pulse_app` any column the
   enumeration does not allow) is caught.
3. Both detections are proven by planted fixtures that fail before the fix and
   pass after removal — run against the text they catch *and* the text they
   allow.
4. All existing views and the full §4.1 isolated pass stay green, with no
   marked test weakened.

## Out of scope

- Any new production view (none is needed; the fixtures are test-only).
- The reveal-subject composition guard (E4's — see the README's not-do list).
- Widening `IDENTITY_NAME_FRAGMENTS` as the mechanism: the carried entry is
  explicit that the fix is lineage and enumeration, not a longer fragment list.
