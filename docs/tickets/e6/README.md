# E6 — Moderation & exclusions: build order

Seven tickets that decompose SPEC §14.3's E6 entry. Each is sized for one
focused session and leaves the repository working: CI green, the Compose stack
healthy, nothing half-wired.

E6 writes the first moderation verdicts this system will hold. Until now
`moderation_state` has no writer, and a comment with no row counts as
published. So the first ticket changes what the read path means before anything
writes to it, and every later ticket builds on that.

Say **"build E6, ticket 4"** and it means E6-04.

Branch names follow `CONTRIBUTING.md`. Cut `e6/<slug>` from
`epic/e6-moderation-exclusions`, which is cut from `main` at 9c9ef4ee. One
ticket per branch, one pull request into the epic branch.

**Read before building anything here:** SPEC §4 and §4.1, §5.2, §5.5, §6.2,
§7.4, §8 and §13; §14.3's E6 entry; this README's rulings; `carried-from-e5.md`
in this folder whole; and `docs/MISTAKES.md` whole. Ticket 01 also reads
ADRs 0144, 0145, 0153 and 0162. Tickets 03 and 05 also read ADRs 0153, 0162,
0178 and 0179 before writing the first view that shows a decision beside a
comment. UI tickets (04, 06) read `docs/DESIGN_BRIEF.md`, `design/tokens.css`
and §7.6 first.

**Lanes in this breakdown:** three of the seven tickets are heavy: 01, 03 and
05. Each is heavy by what it touches, not by its size. 01 adds views and a
definer under `backend/app/views_sql/`, creates a Care table, and rewrites
invariant-marked tests. 03 adds a grants file under `views_sql/`, edits
`api/deps.py`, and changes the invariant-marked payload test. 05 edits
`services/authz.py` and adds sibling-isolation invariant tests. SPEC marks no
⚠ on E6, so no ticket carries ⚠ and no ticket has a verifier step. The UI is
split out of 03 and 05 into 04 and 06 so that it rides the light lane. A light
ticket whose change reds an invariant-marked test re-lanes to heavy, as
E5.1-05 did.

## Rulings this breakdown builds on

The owner ruled on these on 2026-10-09, at the start of the epic. They settle
the four decisions the architect's design left open. No ticket reopens them.

1. **The Lead Faculty reviews harmful comments below the threshold.** The Lead
   Faculty sees a harmful comment's text and its section at any threshold. The
   queue shows no week and no time. The Lead Faculty can exclude or keep the
   comment. SPEC §5.5 gains one exception sentence for this; E6-05 writes it.
2. **The neutral participation trace is built.** When a comment is held, the
   instructor sees a neutral note such as "1 response held for review". The
   note never names a category (§5.2). The breakdown settles how the note sits
   beside §5.2's "no count" below the threshold. The rule:
   - Below the threshold, a flagged comment shows no chip and no flag-type
     hint, and the instructor sees no count except this one note.
   - There is at most one note per section-week. It names no stream and no
     category.
   - It counts the comments in that week's held streams that carry a harmful
     or privacy verdict and that a decision has not kept.
   - It never counts a threat or self-harm comment. Those leave no trace in any
     instructor view (§6.2, and the E6 exit).

   E6-03 builds the note's payload member and writes this rule into SPEC §5.2,
   so that §5.2 no longer says both "no count" and "1 response held". E6-04
   renders it.

   **The cost, accepted by the ruling.** In a thin week, the note beside the
   gradebook ledger can help an instructor guess who wrote a held comment. The
   ledger shows who completed the survey, and the note says one of those
   responses was held. The owner accepted this cost when ruling to build the
   note. It is not an open question; ADR 0189 records it.
3. **The exclusion record lives on `moderation_state`.** The table gains a
   decider column and a reason column, and the exclusion log is a read over it.
   There is no separate `exclusion_log` table and no `audit_log` row for an
   exclusion or a keep. E6-03 edits SPEC §8 and §13 to match.
4. **The exclusion log shows the section and the decider's role, not a name.**
   Staff names carry to E9, which builds the staff-name read.

**A stated limit, not a choice.** "No trace in the instructor view" means the
Pulse surfaces. A reader who also holds the LMS gradebook can sometimes see
that a student completed the survey with a comment that never reached the
report. The gradebook never shows that comment's content or the reason it was
withheld. Participation credit does not depend on moderation, so nothing in
Pulse can close this without changing §3.4's grade. ADR 0189 records it, and
E6-02 makes the empty-week sentence stop claiming that no comments were
submitted.

**Facts checked in the code at 9c9ef4ee, which the tickets build on:**

- `ModerationVerdict` (six members) and `ModerationOutput` exist in
  `backend/app/ai/contracts.py`. Nothing calls them.
- `ClassificationTask` has one member, `COMMENT_VALIDITY`
  (`backend/app/models/ai.py:70`). Adding a second reds the tripwire
  `test_no_harm_classification_task_exists_yet_for_this_filter_to_have_missed`
  in `tests/integration/test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py`.
- `moderation_state` has `answer_id`, `state` and `decided_at`, and no writer.
  `pulse_app` holds `SELECT` on it.
- `CommentView` (`backend/app/schemas/report.py:232`) is `text`, `status` and
  `stream`. It has no handle, so nothing can name a comment to act on it.
- `api/deps.py` has `csrf_verified_student` and `csrf_verified_leadership`, and
  no instructor counterpart.
- `audit_log` has one action, `IDENTITY_REVEAL`, and `subject_user_id` is not
  nullable.
- `backend/app/services/moderation.py`, `backend/app/models/safety.py` and
  `backend/app/schemas/moderation.py` do not exist. `backend/app/services/safety.py`
  does.
- The weekly beat runs the release cut at Monday 02:40 and the summaries at
  Monday 02:50; the floored reclassification runs hourly at :45.

## Build order

| # | Ticket | Branch | Lane | Depends on | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [Moderation verdicts govern the read path](E6-01-verdicts-below-the-read-path.md) | `e6/verdicts-below-the-read-path` | heavy | none | The moderation task and its verdict check; a tie-break column; the `threat_case` table; one definer that writes a verdict and its route; `report_comment` v004 shows only verdicted, non-Care comments; the summary gather reads the view and waits for verdicts; the reveal door narrows to Care-class answers; every fixture and seed plants verdicts; ADR 0187. | |
| 02 | [Moderation runs when a window closes](E6-02-moderation-at-window-close.md) | `e6/moderation-at-window-close` | light | 01 | The moderation prompt and call; an hourly sweep that moderates closed windows; the summary walk turns hourly; mock-ai verdict markers; typed eval cases; the per-stream small-N premise; a true empty-week sentence; ADR 0188. | |
| 03 | [The instructor excludes, keeps and undoes](E6-03-instructor-decisions.md) | `e6/instructor-decisions` | heavy | 01 | Decider, role and reason columns; the instructor's decision routes and CSRF gate; a comment handle and flag class on the payload; the closed held-note type and the participation note; SPEC §5.2, §8 and §13; ADR 0189. | |
| 04 | [Moderation on the instructor report page](E6-04-report-page-moderation.md) | `e6/report-page-moderation` | light | 03 | Comment cards gain the flagged, excluded and kept variants with actions, Undo and the reason prompt; the participation note renders; input boundaries reach 3:1; the chart tables reach sighted readers; the mockups show per-stream notices. | |
| 05 | [The Lead Faculty review queue and the exclusion log](E6-05-review-queue-and-exclusion-log.md) | `e6/review-queue-and-exclusion-log` | heavy | 03 | A leadership-only own-grant read in `authz.py`; the review queue (no week, no time, random order); Lead Faculty decisions through 03's service; the exclusion log in both directions; sibling-isolation and Care-absence invariants; SPEC §5.2, §5.5 and §11; ADR 0190. | |
| 06 | [The leadership queue and log pages](E6-06-leadership-moderation-pages.md) | `e6/leadership-moderation-pages` | light | 04, 05 | The review queue page, the exclusion log page and its row, the routes and landing links. | |
| 07 | [E6 exit](E6-07-e6-exit.md) | `e6/e6-exit` | light | all | The exit clause driven on the running stack; the carried files closed and `../e7/carried-from-e6.md` written; the boundary reviews; SPEC §14.3. | |

## Waves

| Wave | Tickets (in parallel within a wave) | Why it waits |
|---|---|---|
| 1 | 01 | Everything else reads what v004 and the definer mean. |
| 2 | 02, 03 | Both need 01's task member, columns and definer. They share `services/moderation.py` and `services/reporting.py` in different functions. |
| 3 | 04, 05 | 04 renders 03's payload. 05 calls 03's decision service. They share no files. |
| 4 | 06 | Reuses 04's card actions and calls 05's routes. |
| 5 | 07 | Waits for everything. |

## Counters, allotted now

Each was checked in the tree at 9c9ef4ee.

- **Alembic.** The single head is `ad9da2d96664`
  (`20261003_ad9da2d96664_blank_comment_text_is_the_same_under_every_collation.py`),
  one of 52 revisions. E6-01 owns **M1**, with
  `down_revision = "ad9da2d96664"`. E6-03 owns **M2**, whose `down_revision` is
  M1's revision id as merged. E6-05 owns **M3** only if it needs one, with
  `down_revision` set to M2's id. No other ticket adds a migration.
- **ADRs.** 0185 is the last file; 0186 is a recorded gap. **0187** is 01's,
  **0188** is 02's, **0189** is 03's, **0190** is 05's. A number left unused is
  recorded as a gap by 07 and never reused.
- **MISTAKES.** The next entry is **61**. Entries 54 to 57 have no detail file
  and no heading, and `docs/MISTAKES.md` explains only the gap at 32. E6-07
  finds out why from git history and adds the note.

## Shared files

The ticket that merges second merges the epic branch in first, and resolves by
keeping both sides.

| File | Tickets | How it is shared |
|---|---|---|
| `backend/app/services/moderation.py` | 01 creates it; 02 and 03 add to it in parallel; 05 later | 01 creates it with the one Python call to the routing definer, so 02 and 03 meet an existing file rather than an add/add conflict. 02 adds the sweep, 03 the decision service. |
| `backend/app/services/reporting.py` | 01, then 02 and 03 in parallel | 01 the gather; 02 `_stored_summaries` and the empty-week path; 03 the held-note member in `_payload`. |
| `backend/app/services/report_comments.py` | 01, then 03 | 01 the ordering and the view; 03 the handle and flag class. |
| `backend/app/ai/contracts.py` | 02 and 03 in parallel | 02 may touch `ModerationOutput`; 03 adds `HeldNoteType`. Different classes. |
| `docs/adr/README.md` | 01, 02, 03, 05 | Merge in ADR order; keep both rows. |
| `docs/SPEC.md` | 01; 02 and 03 in parallel; 05; 07 | Different sections, except §13 (01, 02's line on the sweep, 03's `loop.py` line, 05's two modules) and §5.2 (01, 02, 03, 05). Keep both sides. |
| `tests/integration/test_identity_grants.py` | 01, then 03 | Each adds its own grants. |
| `tests/fixtures/report_comments.py`, `tests/fixtures/summary_job.py` | 01, then 03 | 01 plants verdicts; 03 adds decisions. |
| `scripts/seed_demo_story.py`, `scripts/seed_exit_story.py`, `scripts/seed_benchmark_history.py` | 01, then 07 | 01 plants verdicts; 07 adds the exit story. |
| `frontend/src/api/openapi.json`, `frontend/src/api/wire.gen.ts` | 03, then 05 | Serial. On conflict, regenerate with `scripts/export_openapi.py` and `npm run gen:wire`; never hand-merge. |
| `frontend/src/api/instructor.ts` | 03, then 04 | 03 edits it only as far as the type check needs after regenerating; 04 owns the rest. |
| `frontend/src/components/CommentCard.tsx` | 04, then 06 | 06 reuses 04's actions; it does not fork the component. |
| `frontend/src/api/leadership.ts`, `frontend/src/router.tsx` | 06 only | |

`tests/unit/test_spec_section_13_draws_the_tree.py` reads the filesystem, so a
ticket that adds a backend module draws it in SPEC §13 and edits no test.

## Spec contradictions, and the ticket that settles each

| # | Where | What disagrees | Settled by |
|---|---|---|---|
| 1 | §13 | `models/safety.py` (`threat_case`) is "not built yet: E10", but §14.3 has E6 write the case records. | 01 draws it as built. |
| 2 | §5.2 | "Harmful … can be a self-harm disclosure" sends a self-harm disclosure to the instructor and the Lead Faculty. The contract and §6.2 make self-harm its own verdict, routed to Care. | 01 rewrites the sentence. |
| 3 | §5.2 vs §5.5 | Flags "route immediately" even below the threshold, but leadership sees raw comments only where the threshold is met and never mutates student data. | Ruling 1; 05 adds §5.5's exception sentence. |
| 4 | §5.2 | "No count" below the threshold, and "1 response held for review". | Ruling 2; 03 writes the rule above into §5.2. |
| 5 | §8 | Lists `exclusion_log`, and says `audit_log` includes exclusions and kept-decisions. | Ruling 3; 03 edits §8 and §13's `loop.py` line. |
| 6 | §8 | "A comment with no row is published", against the carried rule that an unmoderated comment is held. | 01 edits §8. |
| 7 | §5.2 vs §7.4 | "Route to Care immediately" against "Moderation: async at window close". | Moderation runs at window close, swept hourly. 02 edits §5.2's word and records it in ADR 0188. E10 can revisit. |
| 8 | §5.2 | The log is "visible at the Lead Faculty prefix scope", but a lead holds no prefix scope (§2.1, ADR 0025). | 05 rewrites it as the lead's own courses, read over the reader's own grant. |
| 9 | §5.2 | The log lists "instructor"; there is no staff-name read. | Ruling 4; 05 edits the sentence. |
| 10 | `ai/tasks.py` | `EMPTY_WEEK_SUMMARY` says no comments were submitted, which is false once a comment is withheld. | 02. |
| 11 | §5.2 open item, §11 question 5 | Kept decisions are logged but not surfaced. | 05 shows both directions and marks both settled. |

## Exit criterion and the tickets that prove it

| Piece of the exit | Rests on |
|---|---|
| A welfare-flagged comment in a 3-response week reaches Care: a `threat_case` row exists for it. | 01 (the definer and the proof at the service and payload), 02 (the sweep that calls it), 07 (the drive) |
| …with no trace in the instructor view: no comment, no count, no note, no summary text, and the same empty-week sentence as a week with no comments. | 01 (v004 and the gather), 02 (the sentence), 03 (the note never counts Care-class), 07 (the drive) |
| The anti-cherry-picking trail is visible up-chain: an unflagged exclusion with its reason, and a keep, appear in the exclusion log for the Lead Faculty and the chair. | 03 (the record), 05 (the log read), 06 (the page), 07 (the drive) |

## Where the carried work lands

Every section of `carried-from-e5.md`, in file order. Only E6-07 edits the
carried files themselves (`carried-from-e5.md`, `../e5/carried-from-e4.md`,
`../e4/deferred.md`); every other ticket names the entries it closes in its PR
body.

| Section of `carried-from-e5.md` | Owner |
|---|---|
| How the sources were dispositioned (the pass-through list) | Each pass-through keeps its source owner. The E6-owned pass-throughs are below. |
| — the held-note type is a free string | **E6-03** |
| — `moderation_state` has no tie-breakable ordering | **E6-01**, before the first writer, which is 01's definer |
| — SPEC §6.2's threat class is suppressed nowhere | **E6-01** |
| — the reveal door's harm-class narrowing | **E6-01** |
| — forged summary block boundaries | Carries to E7. E6's moderation prompt renders one comment, so it does not trigger the entry. |
| — every other pass-through | Unchanged, under its source owner |
| E8's first obligation: the literal two-line walk | Carries to E8 |
| A named set's figures are read with no reader and no purview | Carries to E9 |
| Generative sibling isolation does not cover named sets | Carries to E9 |
| The rating term-axis read and three cohort views are unread | Carries to E9 |
| Set names that differ only in case are two sets | Carries to E9 |
| Two older accessibility patterns | **E6-04** |
| A named-set write leaves no audit record | Carries to E10. Under ruling 3, E6 writes no `audit_log` row. |
| The instructor gate's 401 sentence is still a literal | Already closed by E5.1-03 |
| The course label is composed in three places, and `_person_of` in two | Already closed by E5.1-03 and E5.1-07 |
| The de-anonymization statement, E6's half | **E6-03** (instructor views, ADR 0189) and **E6-05** (leadership views, ADR 0190) |
| The frontend confidentiality tests have no structural floor | Carries to a process ticket |
| The denial-module inventory and the collection floor | Carries to a process ticket. 07 checks that every new E6 invariant module is marked and collected. |
| The `PERSON_TABLES` standing question | 07 asks it of `threat_case` and of `moderation_state.decided_by_person_id`; the owner stays E13 |
| The TypeScript 7 pair | Carries (dependency watch); 07 re-checks the peer range |
| The session-read sweep's two disclosed limits | 07 re-affirms by planting in E6's new routes; the structural close stays E13's |
| A reader can set a prior term's report against a current one | Carries: an owner ruling, then E9. Unchecked: whether the owner ruled at the E5 merge. No record of a ruling was found in `docs/`. |
| A published figure moves if membership changes after publication | Carries: an owner ruling, then E9 |
| Two readers who pool what they know are out of scope | Carries to the owner. Unchecked: whether the owner confirmed it at the E5 merge; no record was found. |
| A submission racing the close can land on either side of the cutoff | Carries to E8 |
| The hero line keeps its scaling stroke | Carries to E8 |
| The exit drive does not show a week where only the university line is withheld | Carries to E9 |
| The test-edit hook misses its exemption inside a worktree | Carries to a `process/` pull request |
| A comment with no moderation verdict counts as published | **E6-01** |
| Raising the comment threshold re-holds weeks the instructor already saw | Carries to E11 |
| Summaries written before the per-stream rule, and the small-N prompt's premise | **E6-02** |
| A week's item total uses today's question set | Carries to the ticket that adds a second question set |
| The cookieless launch is not bound to the browser that started it | Carries to E13 |
| `.env.example` ships `ENVIRONMENT=development` | Carries to E13 |
| The student's submitted notice says results appear when the week closes | Carries to E8 |
| The design mockups show one notice per week and a response count | **E6-04** |
| A teaching grant with a child edge would stop its section's roster sync | Carries to E9 |
| `ended_teaching_grant` has no retention rule | Carries to E13 |
| The `/dev` controls' origin check trusts the request's own Host header | Carries to E13 |
| Six server-required members stay optional in the frontend, and one figure has three names | Carries to E9 |
| The per-stream gate has no generated property | **E6-01** |
| The summary gather's blank-comment class is not pinned to the view's | **E6-01**: the gather reads the view, so its copy of the class is deleted |
| The roster reads full role URIs only | Carries to E13 |
| Ledger row: a local `.env` keeps `BENCHMARK_MIN_RESPONDENTS_DEFAULT=15` ("E6's first ticket") | **E6-02**, as a dev runbook line telling every developer to set 10 |
| Ledger row: the submit budget measured 2.95 s once | Closed by E5.1-10, checked: `test_a_submission_is_prompt_while_the_broker_is_unreachable` now asserts the median of three submissions. 07 records the closure. |

## Left out, and why

- **The Care queue UI, the case lifecycle, `pulse_care`'s grants on
  `threat_case`, and the escalation notice.** E10's. E6 writes the opening row
  only.
- **Student-facing comment reads.** E8's. 07 hands E8 a note: read
  `report_comment` v004, and show published and kept comments only.
- **Staff names anywhere.** Ruling 4; E9 and E7.
- **The transitive purview for the log.** E9. The assistant dean fails closed
  until then (ADR 0108).
- **Live-provider moderation and threat eval floors.** E10, which needs the
  owner's endpoint. E6 adds typed cases.
- **A moderation drift panel or backlog view.** E11.
- **Retention of moderation rows and of `threat_case`.** E13.
- **Moderating on each submit.** E6 moderates at window close (§7.4); E10 can
  revisit when someone reads the Care queue.
