# E5.1 boundary review

The SPEC §14.2 item 6 record for E5.1 (main review fixes), written by E5.1-09.
It has three parts: who reviewed, the exit clause driven against the running
stack, and every finding with where it went.

## The roster

Twelve reviews ran with fresh contexts, in parallel, all on commit e14da4a (the
epic branch's tip, the merge of #270). Each read the epic's cumulative diff,
`git diff origin/main...origin/epic/e5.1-main-review-fixes`, 185 files, before
reading the epic's tickets and ADRs.

- **Mandated by §14.2 item 6:** `epic-exit`, `invariant-coverage` and
  `adr-docs-completeness`.
- **The boundary specialists:** `data-model`, `lti-oidc`, `a11y-copy` and
  `prompt-eval`.
- **Over the whole epic:** `spec-conformance`, `code-reviewer`, `app-security`
  and `privacy-authz`.
- **`threat-model`.** E5.1 is not a ⚠ epic, but two of the guarantees it added
  carry ⚠ in SPEC §14.3: the per-stream comment threshold (E5.1-01) and the
  ending of a teaching grant (E5.1-02). So the threat model ran too.

The reviews were read-only. None ran `make` or `docker`, because the exit drive
was using the Compose stack at the same time.

## The exit clause, driven against the running stack

**The stack.** Built from e14da4a on 2026-10-04 between 02:10 and 02:12 UTC,
with a fresh database volume. `alembic upgrade head` reached `c5e8a1f3b9d4`,
and `scripts/seed.py` ran; both exited 0. The drive ran from 02:13 to 02:22 UTC.
Launches were driven over plain HTTP the way the SPA makes them: the mock LMS
form posted to `/lti/login`, the mock authorize step, the `id_token` posted to
`/lti/launch`, and the session token taken from the `#session=` fragment.

| # | Criterion | Result |
|---|---|---|
| 1 | Six respondents and one instructor-stream commenter: no raw instructor comment is shown, and the course comments are shown | PASS |
| 2 | An instructor removed from the mock roster gets the section-unavailable answer on their next read | PASS |
| 3 | `ENVIRONMENT` not `development`, with the example session secret, refuses to start | PASS |
| 4 | A backend schema change without regenerated frontend types fails CI | PASS |

### 1. The comment threshold

No committed seeder plants this world, which `epic-exit` raised as a LOW. This
is exactly how it was planted, so the drive can be repeated.

1. Section `BIOL-215-R3WW`, course week 1 (term week 4, window closed
   2026-09-13), at the real clock.
2. An instructor launch into the section, `derive_survey_windows`, and
   `POST /dev/roster-sync`. That enrolled ten members; the instructor holds no
   enrollment.
3. A copy of `scripts/seed_exit_story.py` with only its `STORY` plan replaced
   by one week, piped into `docker compose exec -T api python -`. The week has
   six respondents. One respondent wrote the one instructor-stream comment.
   Five distinct respondents wrote five course-stream comments, which is the
   threshold exactly. The seeder reported 6 responses, 24 answers and 6 comment
   verdicts, and exited 0.
4. `POST /dev/clock` to Monday 2026-10-05 09:00, after every provisioning
   launch. Then `cut_release_batches()` (0 batches) and
   `generate_weekly_summaries()` (152 written, 0 failed). No release batch
   members existed.

A fresh instructor launch then read `GET /instructor/sections/{id}/report/1`
with its Bearer token, the call the SPA makes. The answer was 200, with 6
responses. The instructor stream carried no comments and
`small_n = {"suppressed": true, "threshold": 5}`, and its summary was written
in small-N mode. The course stream carried its 5 comments, all published, with
`small_n.suppressed` false. No released comments were attached. The lone
instructor comment's words appear nowhere in the body (a search for them
counted 0). The course stream in the same response is the readable control. A
second read after the dev clock was cleared gave the same result.

### 2. The roster drop

Section `MATH-140-E1FF`, at the real clock. A staff launch and a roster sync
wrote one teaching grant. With one session token throughout:

- **Before:** the section list named E1FF, and its week 1 report answered 200.
- **The drop:** the mock LMS marked the instructor `Inactive` on E1FF. A roster
  sync then made a complete walk (final page 200, 5 members).
- **After:** the grant row was gone, and `ended_teaching_grant` held one
  `INSTRUCTOR` row dated 2026-10-03. The section list no longer named E1FF. The
  report answered 404, "There is no report here for you to read.", with the same
  status and body as a random section id.

### 3. The example session secret

Run in the deployment shape: the base Compose file only, so the image's own
command runs, with `ENVIRONMENT=production` and non-mock `OIDC_*` values so the
session secret is the only setting under test. Neither secret was echoed.

- **With the example secret:** exit status 1. The startup report names
  `SESSION_SECRET` and its rule, and the example value appears in the output 0
  times.
- **Control, with a fresh `secrets.token_urlsafe(32)`:** the application started
  and answered `/healthz` until a 60-second timeout stopped it. The output never
  names `SESSION_SECRET` and never contains the value.

Under the development Compose override the refused start does not exit,
because `uvicorn --reload` keeps its reloader alive. That is the override's
behaviour, not the product's.

### 4. Stale frontend types

Run in a throwaway worktree at e14da4a, since removed. One field was added to
the `TaughtSection` response model. The two checks are the ones ADR 0185 names:
`tests/unit/test_the_committed_openapi_json_is_current.py` (run alone, while CI
runs it inside the sharded pytest job) and `frontend/src/api/wire.gen.test.ts`
(run with CI's exact command, `npm run test --workspace frontend`).

| Tree | pytest | vitest |
|---|---|---|
| unchanged | pass | pass (312) |
| backend changed, nothing exported | **fail**: `openapi.json is stale` | pass |
| `openapi.json` exported, `wire.gen.ts` not regenerated | pass | **fail**: `wire.gen.ts is stale` |
| fully regenerated | pass | pass |

Both stale cases fail a CI job, and each failure names the command that fixes it.

## The findings, and where each went

No review found a HIGH. The MEDIUM findings come first, then the LOWs. A
defect that several reviews found is listed once.

Where a finding went:

- **E5.1-11** (#274, merged as 7c82662), heavy ⚠: the roster fixes.
- **E5.1-12** (#273, merged as e62c081), heavy: comments in heavy-lane files,
  and new invariant tests.
- **E5.1-13** (#272, merged as 7bea76f), light.
- **This branch,** by commit.
- **Carried,** by file and entry. "The E6 file" below is
  `docs/tickets/e6/carried-from-e5.md`.
- **Accepted,** with the reason.

### MEDIUM

- **"Enrollment means student" was a deny-list** (`lti-oidc`, `privacy-authz`,
  `threat-model`; `roster_sync.py:317-324`). Every member was a student unless
  listed as Instructor or test user. So a teaching assistant listed only by the
  sub-role, a mentor or a content developer could answer, and counted toward a
  stream's five commenters. **Fixed in E5.1-11:** a student must be listed as
  Learner and as no kind of Instructor, and ADR 0183 is amended.
- **Grants on finished sections were ended when the LMS closed the course**
  (`lti-oidc`; `roster_sync.py:1534`). **Fixed in E5.1-11:** no grant is ended
  after the section's end date. That PR's own `privacy-authz` review then found
  that grant *creation* was still ungated after the end date, so a person added
  as Instructor after the term kept a grant forever. It was fixed in the same PR
  by applying the gate to creation, with a test.
- **The held-comment notice was a duplicated landmark** (`a11y-copy`;
  `SmallNNotice.tsx:48`). With both streams held, two regions had the same name.
  **Fixed in E5.1-13.**
- **A raised threshold re-holds a shown stream, and ADR 0182 said it did not**
  (`threat-model`; `report_comments.py:850`). The hold reads the threshold in
  force at each read. So a changed `N_THRESHOLD_DEFAULT`, or a web process and a
  worker running different values, hides comments the instructor has read and
  can put them in a batch. **The record is fixed on this branch** (b461507:
  ADR 0182 and the README). **The behaviour is carried** to E11: the E6 file,
  "Raising the comment threshold re-holds weeks the instructor already saw".
  Its done-when is rewritten: the shown or held state is stored at first read.
- **Comments said the login cookie's `Secure` flag is set in `deps.py`**
  (`adr-docs-completeness`). In `config.py` they are **fixed on this branch**
  (4b80bbe, 4288036). In `services/session.py` they are **fixed in E5.1-12**.
- **Invariant pins** (`invariant-coverage`, three MEDIUMs). Nothing pinned what
  a stream's `small_n` object carries. The notice's no-count test was not in the
  isolated pass. An open week's absence from trends and `published_weeks` was
  guarded only by an unmarked module. **All three fixed in E5.1-12.**
- **A blank comment counted as a commenter** (found by E5.1-12's new test). The
  comment view's one-argument `btrim` trimmed only spaces, so a tab-only or
  newline-only answer counted toward the threshold. The submission path strips
  input, so this was reachable only by a row written past it. **Fixed in
  E5.1-12:** a new view version with an explicit whitespace class. The PR's own
  `privacy-authz` review found that `[:space:]` depends on the database's
  character type, so v003 (revision ad9da2d96664) lists by code point exactly the characters
  Python's `strip` removes, and v002 stays as it was pushed (ADR 0041).

### LOW, fixed

- **In E5.1-11:**
  - A complete walk that read zero members ended every grant (`lti-oidc`).
  - The timeout comment claimed a ceiling on one attempt (`lti-oidc`).
  - `_RESOLVE_PERSON_FOR_USER` repeated `identity.person_for_user`
    (`code-reviewer`).
- **In E5.1-12:**
  - False §13 comments in `lti/__init__.py:3` and `services/identity.py:9`
    (`epic-exit`).
  - False docstrings in `auth.py` and `deps.py`, and "Expected red" paragraphs
    in tests (`code-reviewer`).
  - The `c5e8a1f3b9d4` downgrade docstring, and the missing downgrade test
    (`data-model`).
  - The live-enrollment and blank-comment invariant cases
    (`invariant-coverage`).
- **In E5.1-13:** the one-copy test did not guard the question-set query
  (`spec-conformance`).
- **On this branch:**
  - The README rated the launch forgery LOW where ADR 0089 says MEDIUM
    (`epic-exit`, `spec-conformance`): 57e4218.
  - ADR 0089's note lacked the window, one use within 300 seconds (`lti-oidc`):
    3ae5e56.
  - The ADR index rows for 0086 and 0152 (`epic-exit`): 57e4218.
  - The ADR index row for 0078, and ADR 0093 (`adr-docs-completeness`):
    4b80bbe.
  - ADR 0182 lacked its header lines: b461507.
  - ADR 0161 did not name the SQL copy of the live-on rule: 6b7a826.
  - `.env.example`'s session secret comment: e24d6c9.
  - No record of the session-secret rules, now an amendment to ADR 0077:
    724b164 and 6209510.
  - SPEC §5.1's summary bullet read as a per-week rule (`spec-conformance`):
    b17eb6a.
  - The student copy told students results appear when the week closes
    (`epic-exit`): carried to E8, ebae7bd. The design mockups
    (`spec-conformance`): carried to E6, ebae7bd.

### LOW, carried

All are entries in the E6 file unless named otherwise.

- **Stored summaries and the small-N prompt's premise** (`prompt-eval` and
  `threat-model`). One entry, owner E6: "Summaries written before the per-stream
  rule, and the small-N prompt's premise".
- **No generated property for the per-stream gate** (`invariant-coverage`).
  Owner E6: "The per-stream gate has no generated property".
- **`AddedLater` keeps six required members optional, and the figure type has
  three names** (`code-reviewer`). Owner E9.
- **The definer's `DELETE` would fail on a grant with a child edge**
  (`data-model`). Owner E9.
- **`ended_teaching_grant` has no retention rule** (`data-model`). Owner E13.
- **The `/dev` origin check trusts the Host header, so DNS rebinding passes it
  in development** (`app-security`). Owner E13.
- **The roster reads full role URIs only** (`app-security` on #274). A short
  form fails closed. Owner E13: "The roster reads full role URIs only".
- **No total deadline on one LTI call.** It goes with the existing rehoming
  entry in `docs/tickets/e4/carried-from-e3.md`, which gains that done-when
  (c8f297d).
- **The summary gather's copy of the blank class is not pinned to the view's**
  (`privacy-authz` re-check on #273). The view's class is tested character by
  character; the gather's copy only against a return to `btrim`. Owner E6:
  "The summary gather's blank-comment class is not pinned to the view's".

### LOW, accepted

- **The 398-line AST guard** for one copy of each API helper
  (`code-reviewer`). It works, and its cost is reading time, not a defect.
- **`course_label`'s paired optional parameters** (`code-reviewer`). A runtime
  check guards the pairing. Split it when the function is next touched.
- **`api/student.py` rebuilds `require_student`'s refusal** (`code-reviewer`).
  It has one caller.
- **The vestigial `AnyMethodRoute` and `carry_across`'s name parameter**
  (`code-reviewer`). These are cosmetic, in heavy-lane files, and not worth a
  heavy round.
- **The unread foreign-key indexes and the one-valued role column on
  `ended_teaching_grant`** (`data-model`). The table is small and append-only,
  and dropping an index later is cheap.
- **A staff member enrolled today can submit today** (`spec-conformance`;
  `roster_sync.py:1736`). This is the one-day residue ADR 0183 records.
- **No committed seeder for exit criterion 1** (`epic-exit`). The world is
  recorded exactly above.
- **Process files** (`adr-docs-completeness`). `CLAUDE.md`'s active-epic line,
  `CONTRIBUTING.md`'s E5.1 row and a type-regeneration line are process files.
  They ride a `process/` pull request, which this ticket does not open, so they
  are left for the owner for that reason.

## Clean results

`app-security` (on e14da4a), `data-model` and `prompt-eval` found no HIGH or
MEDIUM. `code-reviewer` found no correctness defect; its nine items were all
simplicity LOWs. `a11y-copy`'s one MEDIUM is above, and every other surface it
checked was clean.

## CI on the exit commit

TODO: run id, status, conclusion and head SHA.
