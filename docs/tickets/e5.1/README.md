# E5.1 — Main review fixes: build order

Nine tickets that fix what the 2026-10-03 review of `main` found at e259255,
before E6 builds on top of it. SPEC §14.3's E5.1 entry is the scope and the
exit. Each ticket is sized for one focused session and leaves the repository
working: CI green, the Compose stack healthy, nothing half-wired.

The review ran five passes over the whole repository: architecture, code
review, application security, privacy and authorization, and a threat model.
Its reports are not in the repository. Each finding below is named by its
pass and by what it found, and each ticket cites the code it fixes.

Say **"build E5.1, ticket 4"** and it means E5.1-04.

Branch names follow `CONTRIBUTING.md`. Cut `e5.1/<slug>` from
`epic/e5.1-main-review-fixes`, which is cut from `main` at e259255. One ticket
per branch, one pull request into the epic branch.

**Read before building anything here:** SPEC §4 and §4.1, §14.3's E5.1 entry,
`docs/tickets/e6/carried-from-e5.md` (several tickets here close entries in
it), and `docs/MISTAKES.md` whole. Ticket 06 also reads ADR 0117 and ADR 0074.

**Lanes in this breakdown:** three of the nine tickets are heavy: 01, 02 and
03. That is one in three, above the usual one in five. Each is heavy because
of what it touches, not its size. 01 rewrites the §4.1 item 3 invariant tests
and a §4 suppression rule. 02 adds a definer function that writes
`role_assignment`, an identity table, and edits `backend/app/lti/`. 03 edits
`api/deps.py` and `api/dev.py`. No natural split moves any of them to light.
01 and 02 also carry ⚠: SPEC §14.3 puts their paths under line-by-line human
review although the epic is unmarked. 05 was planned light and re-laned to
heavy during its build, because its 06:00 rule made invariant-marked tests red.

## Rulings this breakdown builds on

These were settled before the first ticket branch. No ticket reopens them.

1. **The comment threshold counts commenters per stream.** Raw comments for a
   stream in a week are shown only when at least 5 distinct students commented
   in that stream that week. Below that, the stream's comments are held for
   release batches. E5.1-01 builds this and edits SPEC §4.
2. **Weeks with one or two responses keep their figures.** Such a week keeps
   showing its own distributions, trend point and workload figures, and SPEC §4
   is unchanged. Threat-model MEDIUM (a 1- or 2-respondent week's figures
   joined to the gradebook ledger): owner ruling 2026-10-03 keeps SPEC §4 as
   written; closed without a ticket.
3. **Frontend wire types are generated from OpenAPI.** Only types are
   generated, not a client. The generator is a pinned dev dependency, and a
   check fails when the generated types are stale. E5.1-06 builds this.
4. **A week's report opens at 06:00 Monday in the institution's time zone.**
   The owner ruled this on 2026-10-03. E5.1-05 builds it and records the hour
   in SPEC §3.1, which said only "Monday morning".

Four facts were confirmed in the code before the breakdown, and the tickets
build on them without re-proving them. An instructor the LMS removes keeps their
teaching grant. The comment gate counts responses, not commenters.
`session_secret` has no validator. Clearing a judged comment on revise answers
409, which the client shows as "closed".

## Build order

| # | Ticket | Branch | Lane | Depends on | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [Raw comments need five commenters in their stream](E5.1-01-commenter-threshold.md) | `e5.1/commenter-threshold` | heavy ⚠ | none | The comment gate counts distinct commenters per stream; a held stream goes to release batches; a released comment never comes back under its week; summaries follow the stream's count; SPEC §4, ADR 0182. | |
| 02 | [The roster decides who teaches and who answers](E5.1-02-roster-grants-and-respondents.md) | `e5.1/roster-grants-and-respondents` | heavy ⚠ | none | A complete roster walk that drops an instructor ends their teaching grant through a guarded definer; teaching members and test users hold no student enrollment; the roster's token grant gets a time bound; ADR 0183. | |
| 03 | [The API edge holds one job per module](E5.1-03-api-edge.md) | `e5.1/api-edge` | heavy | none | Entry-page sentences join the copy registry; the dev clock routes gain the origin check; one module owns the clock row; one token CSS block; one `_person_of`; dead parts removed. | |
| 04 | [A deployment refuses the example session secret](E5.1-04-session-secret.md) | `e5.1/session-secret` | light | none | `Settings` refuses the `.env.example` secret, an empty one, or one under 32 characters outside development, naming the variable and never the value. | |
| 05 | [Five small behaviour fixes](E5.1-05-small-behaviour-fixes.md) | `e5.1/small-behaviour-fixes` | heavy (re-laned) | 01 | A judged-comment refusal shown inline; a truthful grading log line; the set form shows its stored length; a week opens at 06:00 Monday; a malformed `user_id` is refused; ADR 0184. | |
| 06 | [Frontend wire types come from the OpenAPI schema](E5.1-06-generated-wire-types.md) | `e5.1/generated-wire-types` | light | 01, 05 | A pinned generator builds `wire.gen.ts` from a committed `openapi.json`, with both stale cases going red; one copy of the fetch helpers, figure types and `PulseDivider`; ADR 0185. | |
| 07 | [One copy of each services rule](E5.1-07-services-one-rule-one-home.md) | `e5.1/services-one-rule-one-home` | light | 01, 05 | One question-set rule, one course-week rule, one live-on-a-day rule, one staff filter and one course-label composer, with the private copies deleted. | |
| 08 | [Records match the code](E5.1-08-records-match-code.md) | `e5.1/records-match-code` | light | 03, 06 | SPEC §13 matches the tree, with a test; ADRs 0073, 0132 and 0155 say true things; ADR 0089 records the login-forgery residual. | |
| 09 | [E5.1 exit](E5.1-09-e5.1-exit.md) | `e5.1/e5.1-exit` | light | all | The exit clause driven against the running stack; the hand-offs written into `../e6/carried-from-e5.md`; the ledger; the boundary reviews. | |

## Waves

| Wave | Tickets (each runs in parallel within its wave) | Why it waits |
|---|---|---|
| 1 | 01 (heavy), 02 (heavy), 03 (heavy), 04 | No shared files between them. |
| 2 | 05 | Waits for 01, because both edit `reporting.py`. |
| 3 | 06, 07 | Both wait for 01 and 05, which edit the frontend API files, `reporting.py` and `grading.py`. 06 and 07 share no files. |
| 4 | 08 | Waits for 03 and 06, which add modules §13 must draw. |
| 5 | 09 | Waits for everything. |

**Identifiers, allotted now.** ADR numbers 0182 to 0186; the last on `main` is
0181. 0182 is 01's, 0183 is 02's, 0184 is 05's, 0185 is 06's, and 0186 is
03's only if it needs one. If 0186 goes unused, E5.1-09 records the gap in the
ADR README. There is one migration, owned by 02, with
`down_revision = "a3f6c1d8e5b7"` (the current head).

**Expected conflicts.**

- **`docs/adr/README.md`.** 01, 02, 03, 05, 06 and 08 each add or edit their
  own rows. 01 and 02 add adjacent rows in the same wave, so expect conflicts
  the merger cannot settle on its own. Merge in ADR-number order, and keep both
  rows when resolving.
- **`docs/SPEC.md`.** The breakdown PR edits §14.3 and §14.4, then 01 edits §4,
  05 edits §3.1, 08 edits §13, and 09 edits §14.3. The edits are in different
  sections, and the waves make them sequential.

## Every finding, and where it went

| Finding (review pass) | Same as | Lands in |
|---|---|---|
| Threat model, HIGH: the comment gate counts responses, not commenters | | E5.1-01 |
| Privacy: a released comment reappears under its own week after the threshold is lowered | | E5.1-01. The second half (raising the threshold re-holds weeks the instructor already saw) is carried to E11, hand-off 3. |
| Privacy, HIGH: the teaching grant is never ended | | E5.1-02 |
| Privacy: staff and LMS test users count as respondents | | E5.1-02 |
| Architecture: the transport copies have drifted (no timeout on the roster's token grant) | the carried entry "the roster sync's unbounded token-acquisition dial" | E5.1-02, the timeout fix only. Rehoming the shared code stays carried; see below. |
| Architecture: the stale `lti/__init__.py` docstring | | E5.1-02 |
| Architecture: `deps.py` holds several jobs, and the entry-page copy lives outside the registry; code review: three copied guard bodies, and copied token CSS | the carried entry for the instructor 401 literal | E5.1-03 |
| Architecture: `dev.py` writes the clock row, and the clock routes lack the origin check | the carried entry "the clock routes lack the origin check" | E5.1-03 |
| Code review: `_person_of` is copied, and the course label is composed three times | the carried entry for the course label and `_person_of` | E5.1-03 (`_person_of`) and E5.1-07 (the label) |
| Architecture: the dead `LTI_LOGIN_COOKIE` and the "both doors" docstring in `deps.py` | | E5.1-03 |
| Application security, MEDIUM: `session_secret` has no validator | | E5.1-04 |
| Code review: a 409 read as "closed"; a misleading log line; the edit form drops the stored length; a week is readable before its summary exists | | E5.1-05 |
| Code review: `api/student.py:166` has no guard on a malformed `user_id` | | E5.1-05 |
| Architecture and code review: the API modules repeat their fetch helpers and wire types; `PulseDivider` and the page stylesheet are copied or misplaced | ruling 3 | E5.1-06 |
| Architecture and code review: the student enrollment rule has four copies, and other services rules are copied | the carried course-label entry | E5.1-07 |
| Architecture: the §13 tree has drifted; ADRs 0073, 0132 and 0155 say untrue things | | E5.1-08 |
| Application security, LOW: the cookieless launch is open to login request forgery | | E5.1-08 records the risk in ADR 0089. The fix is carried to E13, hand-off 5. |
| Application security, MEDIUM: a comment with no moderation row counts as published | | Carried to E6, hand-off 1 |
| Privacy: named-set figures are open to subtraction and are not purview-scoped | the existing E9 entry in `../e6/carried-from-e5.md` | That E9 entry gains done-when lines, hand-off 2 |
| Code review: the weekly item total uses today's question set | | Carried to the ticket that adds a second question set, hand-off 4 |
| Threat model, MEDIUM: one- or two-respondent weeks | | Closed by ruling 2, without a ticket |
| Application security, LOW: `.env.example` ships `ENVIRONMENT=development` | | Carried to E13, hand-off 6 |
| Code review: the bounce coaches every comment | `../e6/carried-from-e5.md`, already carried | Dropped here |
| The "already recorded" items of the security and privacy passes, and the threat model's "considered" items | the ledgers they name | Dropped here, already carried |
| Architecture and code review: the seal cycle, and the summary job living inside `reporting.py` | | Left out. Only ADR 0155's stale sentence is fixed, in E5.1-08. |
| Code review: comment volume, the duplicate `comparison` member, the test-only benchmark wrappers, `post_score`'s return, per-row preview requests; architecture: copied seeder helpers | | Left out (below) |

## Hand-offs to later epics

E5.1-09 writes these into `../e6/carried-from-e5.md`, the file E6's breakdown
reads. No ticket before 09 edits that file, and no new carried file is needed.
The exact entries and their done-when lines are in E5.1-09.

1. A comment with no moderation verdict counts as published. Owner E6.
2. The existing E9 named-set entry gains three done-when lines.
3. Raising the comment threshold re-holds weeks the instructor already saw.
   Owner E11.
4. A week's item total uses today's question set. Owner: the ticket that adds
   a second question set.
5. The cookieless launch is not bound to the browser that started it. Owner
   E13.
6. `.env.example` ships `ENVIRONMENT=development`. Owner E13.

## Exit criterion and the tickets that prove it

| Piece of the exit | Rests on |
|---|---|
| one instructor-stream commenter in six respondents shows no raw comment in that stream, and the course stream's comments show | 01 |
| an instructor removed from the mock roster gets the section-unavailable answer | 02 |
| a deployment whose `ENVIRONMENT` is not `development` refuses to start with the example session secret. The check is skipped in development, and `.env.example` ships `ENVIRONMENT=development`, so an unedited copy of it skips the check; that default is E13's (hand-off 6) | 04 |
| a backend schema change without regenerated frontend types fails CI | 06 |

## Left out, and why

- **The comment-volume sweep.** It touches nearly every file, so it would
  collide with every ticket here, and it changes no behaviour; do it module by
  module when a ticket next opens a file.
- **Rehoming the LTI transport, and moving `roster_sync` to `lti/nrps.py`.**
  E5.1-02 fixes the real defect, the timeout drift; the refactor would add a
  heavy `lti/` ticket, and its carried entry keeps its owner.
- **Moving the seal out of `reporting.py`, and splitting out the summary job.**
  They fix no defect, moving the seal makes a ticket heavy, ADR 0155 chose
  this shape, and E9's drill-down reopens the code.
- **The duplicate `comparison` payload member.** ADR 0170 decided it stays and
  an invariant test guards it, so removing it is an ADR change, not a fix.
- **The test-only benchmark wrappers.** Their callers include invariant-marked
  tests, and the named-set pair is tied to the E9 entry.
- **`post_score` returning its status.** Already carried, and it needs a heavy
  `lti/ags.py` edit to save one query.
- **The per-row preview requests.** Low priority, and E9 reshapes that API
  when it attaches sets to views.
- **The copied seeder helpers.** Development scripts with no defect; fold them
  when the next exit seeder is written.
- **Renaming the shared component stylesheets.** Rename them when E8 first
  reuses a component.
- **`.env.example`'s `ENVIRONMENT`.** CI copies the file, so the fix needs a
  workflow change, which is `process/` work; carried to E13.
- **The "already recorded", "considered" and bounce-coaching items.** Each
  already has an owner in a ledger.
- **One- or two-respondent weeks.** Closed by ruling 2; a README line, not a
  ticket.
