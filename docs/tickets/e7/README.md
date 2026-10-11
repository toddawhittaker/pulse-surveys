# E7 — Response loop: build order

Nine tickets that decompose SPEC §14.3's E7 entry. Each is sized for one
focused session and leaves the repository working: CI green, the Compose stack
healthy, nothing half-wired.

E7 is the first epic in which a staff member's name reaches a student, and the
first in which a leader reads a section's summaries in order to write to its
students. So the first ticket builds the records and the one narrow channel a
name travels through, and the rest build on those.

Say **"build E7, ticket 4"** and it means E7-04.

Branch names follow `CONTRIBUTING.md`. Cut `e7/<slug>` from
`epic/e7-response-loop`, which is cut from `main` at ffec4dd6. One ticket per
branch, one pull request into the epic branch.

**Read before building anything here:** SPEC §2.1, §4 and §4.1, §5.1, §5.2,
§5.3, §5.4, §5.5, §5.6, §7.4, §8 and §13; §14.3's E7 entry; this README's
rulings; `carried-from-e6.md` and `carried-requirements.md` in this folder,
whole; and `docs/MISTAKES.md` whole. Tickets 01 and 02 also read ADRs 0043,
0187 and 0189 (the definer pattern, and the append-only record with its
sequence column). Tickets 03 and 04 also read ADRs 0148, 0153, 0184 and 0190
before writing the first read that hands a summary to a new reader. UI tickets
(05, 06, 07) read `docs/DESIGN_BRIEF.md`, `design/tokens.css` and §7.6 first.

**Lanes in this breakdown:** five of the nine tickets are heavy: 01, 02, 03,
04 and 08. Each is heavy by what it touches, not by its size. 01 adds a definer
and a grants file under `backend/app/views_sql/`, and amends invariant-marked
grant tests. 02 extends the invariant-marked student-route sweep. 03 gives a
Lead Faculty member a new read of one section's summaries and ratings, pinned by
sibling-isolation and taught-section invariant tests. 04 refuses a draft that
reuses the words of a comment students will not see, which is §4.1 item 3, and
the repository's precedent marks that kind of test `invariant`
(`tests/integration/test_a_small_n_summary_never_reuses_a_commenters_words.py`).
08 edits `backend/app/api/deps.py`. SPEC marks no ⚠ on E7, so no ticket carries
⚠ and no ticket has a verifier step. The pages are split out into 05, 06 and 07
so that they ride the light lane, and 09 is light. A light ticket whose change
reaches a path in `.claude/heavy-lane-paths.md`, or reds an invariant-marked
test, stops and re-lanes in its pull request.

## Rulings this breakdown builds on

Rulings 1 to 4 are the owner's, made on 2026-10-10 at the start of the epic.
Rulings 5 to 11 were settled the same day as breakdown decisions, each
following from the spec or from an E6 ruling. Decision 12 was settled the same
day, on the privacy review of this breakdown. No ticket reopens them.

1. **A policy covers only its setter's own courses in that prefix.** The
   required-response policy is keyed by prefix and by the person responsible.
   A Lead Faculty member's switch for a prefix covers only the courses in that
   prefix that `authz.lead_review_courses` gives them, and never another lead's
   courses there. SPEC §5.3 says so; this breakdown's pull request writes it.
2. **The 48-hour and 96-hour clocks start when the week's report opens.** That
   is Monday 06:00 in the institution's time zone, as `report_opens_at` in
   `services/reporting.py` computes it (ADR 0184). SPEC §5.3 says so.
3. **One response per section-week.** Every edit is a new row, and the latest
   row is what students see. An edit never holds the week again. Only the
   person who first published the week's response may edit it. SPEC §5.3 says
   so.
4. **An on-behalf response shows students the lead's name and role.** The name
   reaches students through one narrow channel, a single database function. It
   answers a section's live teaching instructors' names, and the name of anyone
   who has published a response to that section, and nothing else. It answers
   only a reader of that section: an enrolled student, the section's
   instructor, or the lead or chair responsible for its course.
5. **A chair acts as lead for a course with no lead.** For such a course the
   chair sets the policy and may respond on behalf. For a course that has a
   lead, the chair reads the policy and cannot change it. This follows §2.1
   (an unmapped course falls to its chair) and E6's review queue. SPEC §5.3
   says so.
6. **The policy in force when a week's report opens governs that week.** A
   later change never releases a held week and never holds back a week already
   shown. SPEC §5.3 says so.
7. **The two new append-only tables are the record.** `response_policy` records
   every policy change, and `instructor_response` records every response and
   every on-behalf response with its author. There is no `audit_log` row for
   either, as E6's ruling 3 decided for exclusions. E7-01 edits SPEC §8's
   `audit_log` line to match.
8. **E7 ships a student results route that answers the week's state and the
   response only, and a minimal page for it.** The aggregates, comments and
   small-N state on that page are E8's.
9. **The on-behalf reader sees summaries and ratings, never raw comments.** A
   lead (or a chair acting as lead) writing on behalf of a section sees that
   section-week's stored summaries and ratings, and the draft and the draft
   check, and no comment text. They are refused a section they teach or have
   taught, with the same 404 the review queue gives (E6's ruling 7). A summary
   written before the week's latest exclusion is withheld from them, because it
   may carry the excluded comment. This closes, for this reader, the carried
   entry "A stored summary can carry a comment excluded after it was written".
10. **E7 builds §5.6 rule 4 and the lead's list of responses owed.** The
    predicate is a function E9's attention list will call rather than copy.
11. **A signed-in reader without a leadership role gets a 403.** The pages then
    say the page is not part of their role. A reader whose session has really
    ended still gets the 401 and the ended-session sentence. This changes
    `api/deps.py`, so it is a heavy ticket of its own (08).
12. **Below the threshold, a theme carries no count.** For a stream held below
    the threshold, no per-theme count field reaches the prompt of the draft
    or the draft check, or the check's payload, and the check names such a
    theme without one. A summary's prose is not a count field and may state a
    number, so in a week with a held stream a draft that carries any number
    except one naming a course structure is refused. A count of comments in a small week is the
    participation trace SPEC §5.2 rules out. A shown stream's themes keep their
    counts. Old-format (`summary.v1`) rows of a held stream give no themes at
    all. E7-04 builds it; SPEC §5.3 says so.

**Facts checked in the code at ffec4dd6, which the tickets build on:**

- The Alembic head is `b7d2e94c1a05`, and it is the only head.
- The last ADR is 0190; the next free number is 0191.
- `ResponseDraftOutput`, `DraftCheckOutput` and `CommentTheme` exist in
  `backend/app/ai/contracts.py`. Nothing calls the first two.
- `weekly_summary` stores `themes` (JSONB, nullable) and `generated_at`.
  `moderation_state` stores `decided_at` and a `sequence` identity column.
- `models/loop.py` and `services/response_loop.py` do not exist. SPEC §13 draws
  both as "not built yet: E7".
- `pulse_app` holds no grant on `person` or `user_identity`. Staff names live in
  `person.identity_name`.
- `audit_log.subject_user_id` must always hold a student, so a staff action has
  no row it could write there.
- `require_leadership` answers 401 for every refusal, a real session in another
  role included. The choice is argued in `api/deps.py`'s docstrings, not in an
  ADR.
- `tests/evals/moderation/` holds typed cases with no `floors.py`. That is the
  pattern for eval cases that ship without a floor.
- `@axe-core/playwright` is not installed, and adding it needs `package.json`,
  which the merger refuses on a ticket pull request.

## Build order

| # | Ticket | Branch | Lane | Depends on | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [The response records and the name channel](E7-01-response-records-and-name-channel.md) | `e7/response-records-and-name-channel` | heavy | none | M1: the append-only `instructor_response` and `response_policy` tables and their grants; the staff-name definer; `models/loop.py`; `services/response_loop.py` with the name read; the survey payload carries the instructor's name; SPEC §8 and §13; ADRs 0191 and 0192. | |
| 02 | [The hold](E7-02-the-hold.md) | `e7/the-hold` | heavy | 01 | The policy of record for a week; the latest response; the student's week state; the one publish writer; the student results route; the student-route sweep extended; ADR 0193. | |
| 03 | [Publish, policy and on-behalf](E7-03-publish-policy-on-behalf.md) | `e7/publish-policy-on-behalf` | heavy | 02, 04 | The instructor's publish and edit routes; the lead's policy routes; the 48h and 96h predicates; the responses-owed read; the on-behalf read, draft, check and publish; ADR 0194. | |
| 04 | [The AI draft and the draft check](E7-04-ai-draft-and-check.md) | `e7/ai-draft-and-check` | heavy | none | Two prompts and their tasks; a gather from stored themes and ratings; the structural refusals; the instructor's draft and check routes; mock-ai answers; typed eval cases with no floor; ADR 0195. | |
| 05 | [The instructor's composer](E7-05-instructor-composer.md) | `e7/instructor-composer` | light | 03, 04, 06 | The composer on the report page: draft, check, publish, the as-students-see-it card with Edit, the hold banner; decisions on released comments; the reason bound checked once. | |
| 06 | [The student's heading and results page](E7-06-student-heading-and-results-shell.md) | `e7/student-heading-and-results-shell` | light | 02 | The survey heading names the instructor; the results page shows the closed door or the response card with its attribution; the `ResponseCard` component. | |
| 07 | [The leadership response pages](E7-07-leadership-response-pages.md) | `e7/leadership-response-pages` | light | 03, 05 | The policy page, the responses-owed list, and the on-behalf composer reusing 05's. | |
| 08 | [Leadership pages say "not part of your role"](E7-08-leadership-not-your-role.md) | `e7/leadership-not-your-role` | heavy | none | `require_leadership` answers 403 to a signed-in reader in another role; the pages say so; an ended session still reads the ended sentence; the two LOWs on the leadership drive; ADR 0196. | |
| 09 | [E7 exit](E7-09-e7-exit.md) | `e7/e7-exit` | light | all | The exit driven on the running stack with dates from the seeded calendar; the carried files closed and `../e8/carried-from-e7.md` written; SPEC §14.3; the standing questions re-asked. | |

## Waves

| Wave | Tickets (in parallel within a wave) | Why it waits |
|---|---|---|
| 1 | 01, 04, 08 | 01 builds the tables and the channel. 04 reads only stored summaries and ratings, which exist. 08 touches only the leadership gate. They share `openapi.json`, `wire.gen.ts` and `docs/adr/README.md`. |
| 2 | 02 | Reads 01's tables and writes through 01's grants. |
| 3 | 03, 06 | 03 builds on 02's gate and writer and calls 04's tasks. 06 renders 02's route and 01's name. They share no files. |
| 4 | 05 | Calls 03's and 04's routes, and reuses 06's `ResponseCard`. |
| 5 | 07 | Reuses 05's composer and calls 03's leadership routes. |
| 6 | 09 | Waits for everything. |

## Counters, allotted now

Each was checked in the tree at ffec4dd6.

- **Alembic.** The single head is `b7d2e94c1a05`
  (`20261011_b7d2e94c1a05_the_application_reads_two_columns_of_the_ended_grant_record.py`).
  E7-01 owns **M1**, with `down_revision = "b7d2e94c1a05"`. No other ticket adds
  a migration. A ticket that finds it needs one stops and says so in its pull
  request; its `down_revision` is M1's id as merged.
- **ADRs.** **0191** and **0192** are 01's (the name channel; the records and
  their keying). **0193** is 02's (the hold). **0194** is 03's (publish, policy
  and on-behalf). **0195** is 04's (the draft and the check). **0196** is 08's
  (the 403). A number left unused is recorded as a gap by 09 and never reused.
- **MISTAKES.** The next entry is **61**.

## Shared files

The ticket that merges second merges the epic branch in first, and resolves by
keeping both sides.

| File | Tickets | How it is shared |
|---|---|---|
| `backend/app/services/response_loop.py` | 01 creates it; 02, then 03 add | 01 the name read; 02 the gate, the state and the writer; 03 the routes' services and the predicates. |
| `backend/app/schemas/response_loop.py`, `backend/app/copy/response_loop.py` | 02 creates them; 03 adds | Different members. |
| `backend/app/schemas/student.py` | 01, then 02 | 01 the instructor's name on the survey payload; 02 the results payload. |
| `backend/app/api/instructor.py` | 04, then 03 | 04 the draft and check routes; 03 publish and edit. |
| `backend/app/api/leadership.py` | 08, then 03 | 08 the module docstring's 401 paragraph; 03 the policy, owed and on-behalf routes. |
| `backend/app/services/reporting.py` | 04, then 03 | 04 the draft gather; 03 the lead's summary filter beside it. |
| `frontend/src/router.tsx` | 06, then 07 | Each adds its own routes. |
| `frontend/src/api/leadership.ts` | 08, then 07 | 08 the 403 outcome; 07 the new calls. |
| `frontend/src/api/instructor.ts` | 05 only | |
| `frontend/src/components/CommentCard.tsx` | 05 only | |
| `frontend/src/components/ResponseCard.tsx` | 06 creates it; 05 and 07 reuse it | Reuse, never fork. |
| `frontend/src/components/InstructorResponse.tsx` | 05 creates it; 07 reuses it | 07 adds the on-behalf mode, not a copy. |
| `frontend/src/api/openapi.json`, `frontend/src/api/wire.gen.ts` | 01, 04, 08 (wave 1); 02; 03 | On conflict, regenerate with `scripts/export_openapi.py` and `npm run gen:wire`; never hand-merge. |
| `tests/e2e/leadership-moderation.spec.ts` | 08 only | |
| `docs/SPEC.md` | 01; 02; 03; 09 | 01 §8 and §13; 02 §5.4 if its states need a word; 03 §5.3 only if a built fact differs; 09 §14.3. Keep both sides. |
| `docs/adr/README.md` | 01, 02, 03, 04, 08, 09 | Merge in ADR order; keep both rows. |
| `tests/integration/test_identity_grants.py` | 01 only | |

`tests/unit/test_spec_section_13_draws_the_tree.py` reads the filesystem, so a
ticket that adds a backend module draws it in SPEC §13 and edits no test.

## Process pull requests this epic needs

- **The accessibility scan.** Adding `@axe-core/playwright` touches
  `frontend/package.json` and the lockfile, which no ticket may change. If a
  `process/` pull request adds it before 05 or 07 is built, that ticket adds the
  scan to its drive. If not, 09 passes the entry on to E8 unchanged.
- **No E7 ticket needs any other path the merger refuses.** 04 adds typed eval
  cases with no `floors.py`, following `tests/evals/moderation/`.

## Exit criterion and the tickets that prove it

SPEC §14.3: "a required-mode section shows nothing to students until a named
human publishes."

| Piece of the exit | Rests on |
|---|---|
| Required mode holds the week: the student reads the closed door and no response. | 01 (the policy record), 02 (the gate and the route), 06 (the page), 09 (the drive) |
| A named human publishes and the week releases: the student reads the response under the instructor's name. | 01 (the name channel), 02 (the writer), 03 (the route), 05 (the composer), 06 (the card), 09 (the drive) |
| Past 96h the lead publishes on behalf, and the student reads the lead's name and role. | 03 (the on-behalf route), 07 (the page), 09 (the drive) |
| An edit never holds the week again. | 02, 03, 09 |

## Where the carried work lands

Only E7-09 edits the carried files. Every other ticket names the entries it
closes in its pull request body, and 09 marks them closed with the pull request
and the merge commit.

### `carried-requirements.md`

| Entry | Owner |
|---|---|
| The professor's name reaches the student, through a sanctioned channel | **E7-01** builds the channel, ADR 0191 and its two-direction pins. **E7-06** renders the name in the survey heading and on the student's response card. **E7-05** renders it on the instructor's as-students-see-it card. 09 records the closure. |

### `carried-from-e6.md`

| Entry | Owner |
|---|---|
| No deployment reaches real students until E10's Care queue exists | Carries to E10; 09 repeats it |
| The Care sweep owes two kinds of held comment, and old summaries owe a look | Carries to E10 |
| A note for E8: what a student's comment read uses | Carries to E8. E7's student route reads no comment. |
| The bounced comment stays outside the moderation pass | Carries to E10 |
| The accessibility scan is not run on the moderation pages | Needs the process pull request above. With it, **E7-05** and **E7-07**; without it, 09 passes it to E8 |
| Two LOWs on the leadership moderation drive | **E7-08**, which adds its cases to that spec |
| Released comments are read-only on the instructor page | **E7-05**. SPEC §5.2 already lets an instructor decide on a comment in a release batch; the page follows it. |
| Deans, vice presidents and the assistant dean have no review queue | Carries to E9. E7 refuses them the policy and on-behalf routes the same way. |
| Two older copies of "closed" | Closed by E6-09 |
| Two behaviours no test covers: the unlock log line | Carries. No E7 ticket touches the moderation sweep. |
| The import cycle; `services/moderation.py` does two jobs; small redundancies | Carry. No E7 ticket touches `services/moderation.py`. A ticket that finds it must takes all three. |
| The reason bound is written twice | **E7-05**, which touches the comment card |
| Comments that tell ticket history | Each E7 ticket, in the files it edits; 09 lists any it saw and left |
| The review queue has no index of its own | Carries to E10 |
| No precision or recall floor for moderation | Carries to E10 |
| Grading reads the close the other way | Carries. No E7 ticket touches grading. |
| A stored summary can carry a comment excluded after it was written | **E7-03**, for the on-behalf reader (ruling 9). Students read no summary in E7; E8 and E9 inherit the rule for their readers. |
| A signed-in reader without the role is told their session ended | **E7-08** |
| Two mockups still pass a count to the small-N notice | Carries to E8 or E9. No E7 ticket edits either mockup. |
| The exit drives read pinned dates in Fall 2026 | 09 adds no pinned date. The existing drives stay with a `process/` pull request, which must land before 2026-11-23. |
| The `PERSON_TABLES` standing question | **E7-09** asks it of `instructor_response` and `response_policy` |
| The TypeScript 7 pair | **E7-09** re-checks the peer range |
| The session-read sweep's two disclosed limits | **E7-09** re-affirms by planting in E7's new routes |
| The denial-module inventory and the collection floor | **E7-09** checks every new E7 invariant module is collected |
| Carried through unchanged: the forged summary block boundaries | **E7-04** sends the model no comment, so the entry does not trigger; ADR 0195 says so, and 09 passes it on to the next ticket that renders comments into a prompt |
| Carried through unchanged: every other pass-through | Unchanged, under its source owner |

## Left out, and why

- **Notifications** (the Monday-after email). E12.
- **Staff names on leadership pages.** E9. The channel answers a responsible
  lead so the on-behalf preview matches what students will read, and no
  leadership list shows a name.
- **Aggregates, comments and the small-N state on the student page.** E8.
- **Eval floors for the draft and the check.** Typed cases only; a floor needs
  the owner's live endpoint.
- **Unpublished drafts stored on the server**, an "edited" marker, and
  unpublishing. Nothing in §5.3 asks for them.
- **The assistant dean's, the dean's and the vice president's policy views.**
  Refused until E9's supervision walk, as the review queue is.
- **A new scheduled job.** The 48h and 96h deadlines are computed on read.
