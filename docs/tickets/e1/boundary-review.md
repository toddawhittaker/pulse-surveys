# E1 epic-boundary review — the record

Run 2026-08-28 against the epic tip `ce25e39` (base: `main` at `8e48ecf`),
after all fifteen tickets, the four cleanup batches, and the two
workflow-speedup PRs merged. The roster: the eight epic-boundary agents per
ADR 0004 as amended 2026-08-28 — `epic-exit`, `threat-model`,
`invariant-coverage`, `adr-docs-completeness`, plus `data-model`, `lti-oidc`,
`a11y-copy` and `prompt-eval` on their first boundary run. `/review-selftest`
was not re-run for this pass; PR #117 ran the full ten-fixture set after the
prompt edits, all caught.

Every code finding below went through an adversarial verification pass — a
second, independent agent tasked with refuting it — before being recorded.
All survived; two were downgraded, two came back worse than reported, one
changed character. Verification evidence (repro outputs, a scratch-database
migration round trip, query-plan measurements at a million rows, library
source reads) is summarized inline.

## Verdict

**The exit criterion is met.** All five clauses of SPEC §14.3 E1's exit line
were proven against the running stack, including the refusal clauses: replay
and state-tamper refusals hand-driven (400 with the right `data-reason`, no
session issued), roster reads 401 without a service token, derived dates
checked against the seeded term map, the two-hat Dean through both doors. CI
was green on the tip (run 33211194697, every job including Playwright). The
§4.1 invariant suite collects 124 tests, all passing, none skipped. The only
CI tolerance left is the AI eval floors, which E2 owns.

No finding falsifies an exit clause. The three HIGHs live in code nothing
currently exercises: two are dormant until a real LMS platform arrives (E3),
one is a missing test.

## Disposition

Todd's ruling, 2026-08-28: fix the three HIGHs, the six mechanical MEDIUMs,
and all record corrections inside E1, before the epic merges; the no-`sub`
launch is refused politely with an ADR recording the deliberate
non-conformance; the leadership-trigger finding is carried to E2 under a hard
deadline. `boundary-fix-plan.md` beside this file holds the batches. LOWs are
carried with owners, listed at the end of this file.

## HIGH — all three fixed in the boundary fix round

**H1 — NRPS paging corrupts on case-carrying URLs.**
`backend/app/services/roster_sync.py` walks the roster by following the
`rel="next"` URL, and `pylti1p3` 2.0.0 (`service_connector.py:129`) extracts
that URL from a lowercased copy of the `Link` header. RFC 3986 makes path and
query case-sensitive; a repro showed `?page=Bookmark:QUJDeHl6` coming back as
`?page=bookmark:qujdehl6`. Canvas's base64 page cursor breaks (Moodle's
router happens to be case-tolerant, so the original Moodle example does not
hold). Verification found a worse sibling: a `Link` header carrying another
parameter before `rel="next"` (`<url>; title="x"; rel="next"`) misses the
regex entirely, ending the walk early as complete — a silently truncated
roster with no error recorded. Invisible today because the mock's cursor is a
decimal integer. Fixed in batch A.

**H2 — the section-binding migration's downgrade destroys data its docstring
never mentions.** Proven empirically on a scratch database: run
`20260826_b8c41f7d2e05` down and back up, and every bound section reads
`lms_context_id = 'pre-binding-section-<uuid>'`; the real provisioning code
then takes the `context_collision` branch on every staff launch, permanently
— the application holds no UPDATE on the column, and the docstring presents
the reversal as complete. Tempering facts from verification: a DBA can repair
it (the real context id lands in `launch_defect.context_id` on the first
collided launch), and hourly sync survives (the roster address column
round-trips intact); what dies is launch-triggered ingestion and refresh.
Fixed in batch B, which also corrects the E1-10 item 3
closure note in `deferred.md` that a `count(*) = 0` measurement had closed.
**One sentence of this entry was wrong and is struck**: it said "the fix shape
already exists in-tree: `e2c94b6a1f70`'s downgrade preserves into a scratch
table". It does not. That downgrade *fills* `user_identity.identity_name` with
a marker before restoring a `NOT NULL`; no migration in this repository creates
a scratch table, which batch B established by grep before writing one. The fix
is right and there was no precedent to copy — the preserve/restore blocks are
written in the style of `b8c41f7d2e05`'s own `BIND_EXISTING_SECTIONS`, a
`DO $$` block so that `alembic upgrade --sql` carries them.

**H3 — the roster sync's log is an untested read path.** The one component
that handles a whole section's names and email addresses has no test of any
kind over what it logs; `caplog` appears in exactly three test modules, none
of them the sync's. The code is clean today, and the module already logs the
roster service address — the same value the dev console guards with two
spelling-independent backstops. Fixed in batch A (log-scan tests over success
and failure paths, canary-shaped).

## MEDIUM

**Fixed in the fix round:**

- **M2 — no dedup across roster pages** (`roster_sync.py`, ingest loop).
  Confirmed by live repro: a member re-served across a page boundary raises
  `ExclusionViolation` on the enrollment-overlap constraint, uncaught,
  aborting the section's whole sync. Batch A.
- **M4 — a launch with no `sub` spends its nonce, then 500s**
  (`provisioning.py:343`, no handler anywhere). Verification made it worse:
  LTI 1.3 Core §5.3.6.1 says the tool MUST treat a missing `sub` as an
  anonymous-user launch, so this is a *conformant* message answered with a
  500. Pulse has no anonymous user; Todd ruled: refuse politely, and record
  the deliberate break with the MUST in an ADR. Batch B.
- **M5 — `nrps_call` indexed on `section_id` alone** (`models/lti.py:1121`).
  Measured at a million rows laid out hour-major: 2,006 buffers per
  staff-launch debounce probe against 5 with `(section_id, called_at DESC)`,
  growing all term with no purge until E13. Verification also found
  `sync_all_rosters` has no term filter, so retired sections are called
  hourly forever — recorded below as carried. Batch A. (The Batch A index
  was descending; E2-02 later replaced it with the ascending composite
  `ix_nrps_call_section_id_called_at`, which performs identically and is
  visible to `alembic check`.)
- **M6 — seven of E1's strongest confidentiality denials carry no
  `invariant` marker**, so they sit outside the isolated pass CI cannot see
  skipped — including the whole E1-12 identity-merge module and the only test
  keeping `pulse_app` off `person`. Confirmed with the collector (124
  collected; none of the seven among them). Batch C.
- **M7 — `refusal_page` is the one door answer whose body no test scans**
  for caller-supplied values; the sibling pages each have a scan. Latent
  (every message passed today is a constant). ~~Batch C.~~ **Batch B**: the
  page renders its text argument, so the scan this finding asks for fails
  against the code and the fix is code, not a test — the copy comes from the
  guard name through a constant map now and the free-text parameter is gone.
- **M8 — the org-view sweep polices a hand-written list** that omits
  `section_roster`, `section_enrollment_count`, and base `enrollment` —
  the three relations where `pulse_app` holds table-grain SELECT and
  `ScopedReader` is the only narrowing — and the suite's own allow-list
  positively protects the bypassing query shape. The dev console's count-only
  read (gated, ADR 0100) is legitimate but teaches a spelling no sweep can
  grade. Batch C closes the inventory against the catalog the guarded
  structure cannot shrink.
- **M10 — the focus ring failed non-text contrast** (measured 2.09:1 on
  chalk, 2.24:1 on paper against SC 1.4.11's 3:1 floor). Nothing focusable
  renders in E1, but every future control inherits the token. Fixed in this
  records PR: the ring is now `--marigold-deep` (measured 4.64:1 and
  4.96:1), the design brief amended to match.

**Carried:**

- **M9 — any leadership assignment is an unscoped roster-ingestion
  trigger.** A Lead Faculty enrolled as a Learner in a sibling lead's course
  can launch from it; `holds_leadership` admits them with no reference to
  the launch's context, and Pulse binds the section, stores its roster
  address, and pulls the membership. Verification sharpened it: this is
  write/ingest integrity, not a read leak — the roster is never shown to the
  trigger, and the INSTRUCTOR row goes to the real teacher. The fix needs a
  design answer (a dean's legitimate first launch into a course no purview
  yet covers must keep working), so Todd ruled: carried to **E2**, hard
  deadline **before any surface renders roster-derived data** — recorded in
  `../e2/carried-from-e1.md`.

## Downgraded on verification

- **`aud[0]` / `azp`** (`lti/launch.py:520,536`; `provisioning.py:266`) —
  reported MEDIUM, verified LOW. The IMS Security Framework makes the `azp`
  checks SHOULD, not MUST; refusing extra untrusted audiences (half the
  reported failure) is required behavior; and the nonce-to-state binding
  makes the one wrongly-accepted ordering unexploitable. Owner: E3, with the
  platform adapters.
- **`nbf` with zero leeway** (`lti/launch.py:381`) — reported MEDIUM,
  verified LOW by repro (PyJWT 2.13.0 raises `ImmatureSignatureError`, read
  back as `SignatureRefused`). `nbf` appears nowhere in LTI 1.3 Core or the
  Security Framework, so only a platform volunteering an off-profile claim
  is affected. Owner: E3.

## LOW — carried, with owners

| Where | What | Owner |
|---|---|---|
| `lti/launch.py:133` | Bare `Instructor` (deprecated-but-permitted simple name) and the `urn:lti:role:ims/lis/*` spellings read as student. Refusing is conformant (recognition is a MAY); the risk is a silent wrong landing on a real platform | E3 |
| `models/org.py:316` | `course.title_is_fallback` written and cleared, read by nothing; costs a column-grain UPDATE grant | E2, first title-reading surface |
| `views_sql/launch_provisioning_grants_v001.sql:43/99` | Table-wide INSERT writes the derived calendar columns at row creation, undercutting the reason UPDATE was withheld; an unrepairable wrong calendar | E2, with ADR 0021's owners |
| `models/org.py:379`, `identity.py:702` | Two justifying comments now false; `(section_id, role)` index wanted by E4's report | E4 |
| `main.py` framing | Registered-LMS origins disclosed unauthenticated via `frame-ancestors` on every SPA path, one pool session per request | E3, real-platform hardening |
| `authz.py:1078` | `sanction_for` has no caller check; `record_teaching_instructor` checks only duplicates. Needs code already inside `backend/app/`, so LOW | E2, first new sanctioned writer |
| `tests/unit/test_no_service_reads_an_identity_table_directly.py:49` | Identity-read sweep parses `services/` only; E1 put ~1,300 lines of request handling in `api/` and `lti/` | E2, with M8's closure pattern |
| `roster_sync.py:493` | `sync_all_rosters` has no term filter — retired sections are called hourly forever (found verifying M5) | E13's retention, or sooner if E11's console shows it |
| `services/session.py:110,136` | ADR 0093's recorded `SessionClaims.iss` mismatch, still open, previously unowned | E2 |
| `Makefile` / README | `make up` (no `--build`) + `make e2e` fails on a stale `mock-lms` image; clean checkouts and CI unaffected | next process PR that touches the Makefile |

The beat-cadence ADR gap flagged by `adr-docs-completeness` is closed in this
PR (ADR 0105). Record corrections (stale claims in the epic README, the root
README, `deferred.md`, `carried-from-e1.md`, and a comment in `landings.ts`)
land in this PR; each is listed in the PR body.

## Clean passes

- **prompt-eval**: nothing found — zero changed lines on the AI/eval
  surface; floors, probes and the §9.3 comments byte-identical to `main`.
- **adr-docs-completeness**: 24 new ADRs, none restating or contradicting
  the spec; CLAUDE.md still process-only, under budget.
- **threat-model** positively confirmed three records rather than trusting
  them: the reveal path is unreachable, the mock's dean/section pairing is
  enforced server-side, and no wrong-launch selector widens a roles claim.
- **a11y-copy**: landmarks, heading structure, copy register, and token
  conformance clean across the five landings and four door pages; the one
  latent leak slot (`data-reason`) never reaches assistive technology.

## Stopping rule

Declared before the fix round: one fix round over the ruled scope (batches
A–C plus this records PR), each batch through its lane with the standing
per-PR reviews; then one re-review pass over the fixes by the reviewers whose
findings they answer (`lti-oidc`, `data-model`, `invariant-coverage`,
`threat-model` on M8's closure, `a11y-copy` on the ring); then stop. Findings
not selected for fixing are carried above — silence stays accounted either
way.

## Re-review disposition (2026-08-31)

The re-review pass ran 2026-08-31 against the epic tip 87448d7 — the five
reviewers scoped exactly as the fix plan mandates — and its consolidated
result is a comment on PR #123. Every finding selected for the fix round
verified closed, with two qualifications: the focus-ring fix left two
hand-copied duplicates of the superseded color, and M8's closure holds in
substance with defects in its own perimeter. The pass found one new HIGH
(the fix round's three new confidentiality-denial test modules carry no
`invariant` marker — M6's own defect recurring), four further MEDIUMs,
seven LOWs, and record notes.

Ruling (Todd, 2026-08-31): the HIGH is fixed inside E1 together with the
three ride-along MEDIUMs — the recursive catalog derivation, the
`--marigold` comment correction, and the door-page focus color — through
one further tests-first PR into the epic branch (`e1/re-review-fixes`).
The `views_sql` package-exemption MEDIUM is carried to E2 with a hard
deadline, and the LOWs and record notes are carried with owners; both in
`docs/tickets/e2/carried-from-e1.md`. This ruling supersedes the stopping
rule's "then stop" for exactly that scope and no more.
