# E1 boundary fix plan — three batches

The fix round `boundary-review.md`'s disposition orders. Scope is Todd's
2026-08-28 ruling; nothing here exceeds it. Every batch is **heavy lane**
(each reaches `backend/app/services/`, `backend/migrations/`, or
invariant-marked tests — `.claude/heavy-lane-paths.md`), so each rides the
test-author → implementer → verifier loop with the standing per-PR reviews,
and merges only on Todd's written approval. Batches A and B partition by
file; C is tests-only. The finding labels (H1…) are `boundary-review.md`'s.

## Batch A — the roster sync is robust to real platforms

**Branch:** `e1/boundary-fix-roster-sync`. **Touches:**
`backend/app/services/roster_sync.py`, one new migration, roster-sync tests.

1. **H1.** The walk follows the `rel="next"` URL exactly as the platform
   sent it — case preserved — and recognizes the link whatever else the
   `Link` header carries: other parameters before or after `rel`, unquoted
   `rel=next`, multiple links in one header. A page whose header has no next
   link ends the walk complete; a next URL that cannot be fetched still ends
   it incomplete (the existing truncated-walk safety holds). This means not
   trusting `pylti1p3`'s extraction for the next-page URL; how (subclassing
   the connector or reading the response header directly) is the
   implementer's choice.
2. **M2.** Members are deduplicated by `user_id` across the assembled pages
   before ingest — first occurrence wins, a duplicate is logged — so a
   member re-served across a page boundary cannot abort the section's sync.
   The exclusion constraint still guards genuine overlaps.
3. **M5.** A migration adds an index on `nrps_call (section_id, called_at
   DESC)`; `alembic check` clean; the downgrade drops exactly it. New
   revision chains from `f3a5c92d8e14` — batch B creates no revision, so
   there is no head collision.
4. **H3.** Log-scan tests over the sync: no record under
   `app.services.roster_sync` ever carries a served member's name, email, or
   subject — canary-shaped (the values planted, then scanned for), success
   and failure paths both, since failure paths are where values get printed.

## Batch B — the launch door's two honesty fixes

**Branch:** `e1/boundary-fix-launch-door`. **Touches:**
`backend/app/services/provisioning.py`, `backend/app/api/lti.py` if the
refusal wiring needs it, `backend/migrations/versions/20260826_b8c41f7d2e05_*`,
provisioning tests, ADR 0106, two record lines.

1. **M4.** A launch token with no `sub` is refused with the calm refusal
   page and its own `data-reason` marker, before any 500 can happen — the
   same shape as every other refused launch, nonce treatment included.
   **ADR 0106** records the deliberate break with LTI 1.3 Core §5.3.6.1's
   "MUST interpret … as an anonymous user": Pulse has no anonymous user, and
   pretending to admit one would be the worse lie. (Todd's ruling; the
   alternatives — support anonymous, or carry the crash — go in the ADR's
   rejected section.)
2. **H2.** The `b8c41f7d2e05` downgrade preserves `lms_context_id` and
   `lti_deployment_id` into a scratch table and the upgrade restores them —
   the `e2c94b6a1f70` style — so a downgrade/re-upgrade round trip is
   actually the identity its docstring claims. The docstring says plainly
   what is preserved where. The E1-10 item 3 closure in `deferred.md`
   (`count(*) = 0`) gets a line noting the round-trip hazard existed and is
   now closed.
3. **R6.** The `caplog` assertion PR #105 promised for
   `_log_a_refused_write`: the refusal log line is exercised and scanned for
   claim values, closing the `deferred.md` entry the records PR added.

## Batch C — the guards close their sets

**Branch:** `e1/boundary-fix-guards`. **Touches:** `tests/` only — but the
tests it marks and writes are invariant-marked, which is a heavy row.

1. **M6.** The seven named tests carry the `invariant` marker; the collector
   count rises from 124 by exactly the tests added, and
   `scripts/ci/check_invariants.py` still passes. The seven are listed in
   the invariant-coverage boundary report (E1-13's claims-vs-assignments
   landing test, the E1-12 identity-merge module, the `person`/`user`/
   `web_login_subject` grant refusals, the `resolve_scope` union test, two
   roster-definer denials, the launch-provisioning defect test).
2. **M7.** `refusal_page`'s rendered body gets the same scan the sibling
   pages have: a canary value planted in the guard exception's message must
   not appear in the body (only the constant copy and the `data-reason`
   class name may).
3. **M8.** The org-view sweep's inventory comes from the `views_sql` catalog
   — the structure the guarded set cannot shrink — instead of a hand-written
   three-name list, and covers base `enrollment`. The `SQL_MUST_ALLOW` entry
   that positively protects the bypassing roster shape is removed; the dev
   console's count-only read (ADR 0100) is exempted explicitly by location,
   never by shape. Each newly-policed pattern is proven by a planted
   offender the sweep must catch (manifest-style, per the heavy lane).

## Sequencing and the re-review

The records PR (`e1/boundary-records`: this plan, `boundary-review.md`, the
record corrections, ADR 0105, the focus-ring fix) merges first so the
batches' test authors read the plan from the tree. A, B and C then build in
parallel worktrees — files partitioned as above, one migration revision
total, ADR numbers pre-assigned (0105 records PR, 0106 batch B).

After all three merge: one re-review pass — `lti-oidc` over A and B's door
work, `data-model` over A's migration and B's downgrade, `invariant-coverage`
over C, `threat-model` over M8's closure, `a11y-copy` over the ring — then
stop, per the stopping rule in `boundary-review.md`. Then the epic → `main`
PR, on Todd's word.
