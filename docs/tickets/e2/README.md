# E2 — Weekly survey & validity: build order

Thirteen tickets decomposing SPEC §14.3's E2 entry. Each is sized for a
single focused session and leaves the repository in a working state: CI
green, Compose stack healthy, nothing half-wired at a boundary. E2 is **not**
a ⚠ epic — no line-by-line human review mandate — but it is the first epic
with a student-visible path, every ticket still gets the independent per-PR
security review, and two lanes still govern how tickets are built
(`.claude/heavy-lane-paths.md` is the authority; the header decides, a
missing field means heavy).

Say **"build E2, ticket 5"** and it means E2-05.

Branch names follow `CONTRIBUTING.md`: cut `e2/<slug>` from
`epic/e2-weekly-survey-validity`, one ticket per branch, one pull request
into the epic branch.

**Read before building anything here:** `docs/tickets/e2/carried-from-e1.md`
(every entry — this breakdown schedules the E2-owned ones, and the mapping is
below), SPEC §3.1–§3.3, §4.1, §7.4, §9.3, and `docs/MISTAKES.md` whole.

Items an E2 ticket defers rather than fixes live in `deferred.md` (created by
the first PR that needs it); a PR that defers something adds it there in the
same PR, and E2-13 runs the cleanup pass over the file.

**Lanes in this breakdown:** E2-10 (the frontend form) rides the light lane;
every other ticket is heavy — the epic's substance lives in `services/`,
`models/`, `migrations/`, `api/`, compose, workflows, and invariant-marked
tests, all heavy-lane paths.

**Three decisions Todd made at breakdown time (2026-08-31),** recorded here
so no ticket re-litigates them:

1. **Live AI calls happen only in the eval suite.** Ordinary tests and e2e
   use the loopback stub and the E2-07 mock. The eval suite runs on
   AI-touching changes (step-level path condition), on manual dispatch, and
   locally — never on every merge. E2-12 carries the mechanics; the provider
   key secret is created by Todd and referenced only after his written go.
2. **Time is mocked by a clock service with a development-only override**,
   set interactively from `/dev`, stored in the database so backend and
   worker agree. E2-04 builds it; protocol clocks (launch validation,
   session expiry) stay real.
3. **Term-map re-derivation goes to E11**, per ADR 0018/0021's own lean:
   the calendar editor is where a map is edited, and whoever builds that
   owns the re-derivation. E2 builds nothing that edits a map. The three
   records that described this as open — SPEC §14.3's E2 entry, ADR 0018,
   ADR 0021 — are corrected in this same PR, so no record goes on asserting
   an undecided question (MISTAKES entry 1).

## Build order

| # | Ticket | Branch | Depends on | Summary | Merged |
|---|---|---|---|---|---|
| 01 | [The `views_sql` exemption and the import guard name the same object](E2-01-sweep-guard-agreement.md) | `e2/sweep-guard-agreement` | none | The carried disagreement fixed fail-closed before E2's first read path, proven by the re-review's planted offender; ADR 0107 corrected; the org-sweep record fixes ride along. | |
| 02 | [A staff launch binds a roster address only inside the launcher's purview](E2-02-staff-launch-purview.md) | `e2/staff-launch-purview` | none | M9, verified by the E1 boundary review, fixed before any surface renders roster-derived data; out-of-purview launches record a defect row; the roster low findings ride along. | |
| 03 | [The registration restore refuses with a sentence](E2-03-migration-restore-refusal.md) | `e2/migration-restore-refusal` | none | The downgrade-delete-upgrade path gets the family's actionable refusal; a docstring stops citing a struck precedent. | |
| 04 | [One clock service, and a dev-only time control on `/dev`](E2-04-dev-clock.md) | `e2/dev-clock` | none | All scheduling reads go through one clock; in development a pretend "now" is set interactively and time flows from it; protocol clocks stay real. | |
| 05 | [The survey schema](E2-05-survey-schema.md) | `e2/survey-schema` | none | `question_set`, `question`, `response`, `answer`, the seeded v1 five questions, and ADR 0018's deferred cross-term rule on `survey_window`. | |
| 06 | [Survey windows derive from the calendar](E2-06-window-scheduling.md) | `e2/window-scheduling` | 04, 05 | Friday 18:00 → Sunday 23:59:59 in the institution timezone, derived per active course week; one open window per section, missed weeks never back-filled. | |
| 07 | [A mock AI provider joins the Compose stack](E2-07-mock-ai-provider.md) | `e2/mock-ai-provider` | none | Deterministic OpenAI-compatible verdicts plus selectable wrong answers, so dev and e2e never spend a token and the non-timeout paths are actually drivable. | |
| 08 | [The submit path](E2-08-submit-path.md) | `e2/submit-path` | 05, 06 (07 for stack tests) | Required fields, conditional-required comments, synchronous validity gating with the coached bounce, fail-open on timeout with async re-classify, resubmission within window. | |
| 09 | [The student read path, and §4.1 item 1 gets its assertion](E2-09-student-read-path.md) | `e2/student-read-path` | 01, 02, 05, 06 | What the form fetches, scoped to the student's own enrollment; the invariant test whose path inventory the code cannot quietly shrink. 02 is a dependency by deadline. | |
| 10 | [StudentWeeklySurvey: the five-question form](E2-10-student-survey-form.md) | `e2/student-survey-form` | 08, 09 | The first real screen per §7.6: LikertInput, ConditionalTextArea, WorkloadSlider, SubmitBar; the carried webfont decision lands here. Light lane. | |
| 11 | [The copy-inventory test](E2-11-copy-inventory.md) | `e2/copy-inventory` | 08, 09, 10 | §4.1 items 4 and 5 become assertions over the shipped strings, with planted violations red and a canary against a blind collector. | |
| 12 | [The validity eval set, and the floors turn enforcing](E2-12-eval-floors.md) | `e2/eval-floors` | none | `tests/evals/` becomes real, §11 question 4 gets its operational answer, and the last E0 tolerance flips — live calls only on AI-touching changes and manual dispatch. | |
| 13 | [E2 exit](E2-13-e2-exit.md) | `e2/e2-exit` | all | The four exit clauses in a browser on the dev clock against the mock; boundary reviews; the denial-sweep re-affirmation; `../e3/carried-from-e2.md`. | |

## Dependency graph

```
01, 02 ─────┐
04 ─┬─ 06 ─┬┴─ 09 ─┬─ 10 ── 11 ──┐
05 ─┘      └── 08 ─┘             ├── 13
03   07   12 (free-standing) ────┘
```

(09 needs 01, 02, 05, 06; 08 needs 05, 06; 10 needs 08 and 09; 11 needs all
three; 13 needs everything.)

Six starts run independently and can interleave: the two carried guards (01,
02), the record fix (03), the clock (04) and schema (05) that feed the window
chain (06 → 08/09 → 10 → 11), the mock (07), and the eval suite (12). 01 goes
first on principle as well as dependency: Todd's deadline puts it before any
E2 read path, and building the guard while no E2 view exists is what makes
its red case honest — the same reasoning as E1-01. 02's deadline has the
same shape and is encoded the same way — as a dependency of 09 — so the
schedule itself, not a sentence in a ticket, is what stops the student
surface merging over an unfixed ingestion trigger.

## Exit criterion → the tickets that prove it

§14.3 E2's exit line has four clauses; E2-13 proves each against the stack.

| Clause | Rests on |
|---|---|
| a student submits a valid response | 05, 06, 08, 09, 10 |
| "it was okay" is bounced with immediate feedback | 07, 08, 10 |
| the invariant suite carries a §4.1 item 1 test that fails when a student-visible path returns another section's data | 01, 09 |
| the copy-inventory test exists and reads the survey surface's shipped strings | 10, 11 |

## Where the carried work landed

Every E2-owned entry of `carried-from-e1.md`, with the ticket that schedules
it. The entries' own done-whens govern; the tickets point at them.

| Item | Lands in |
|---|---|
| The `views_sql` exemption and the import guard disagree (deadline: before E2's first read path) | E2-01 |
| Org-sweep record fixes: statement-pin docstrings, the `authz.py` comment's stale count | E2-01 |
| M9 — the unscoped roster-ingestion trigger (deadline: before any roster-derived surface) | E2-02 |
| Roster low findings: cycle-cap prefix, `unpinned_hosts` docstring, the `DESC` index | E2-02 |
| The restore's raw constraint violation; the struck-precedent docstring | E2-03 |
| The three webfonts, decided against E2's first real screen | E2-10 |
| §4.1 item 1's assertion and the copy-inventory test (spec-owned to E2) | E2-09, E2-11 |
| The AI eval floors, the last CI tolerance (spec-owned to E2) | E2-12 |
| The denial-module sweep's inventory: **decided at breakdown** — the E2 boundary review re-affirms the two disclosed limits in writing | E2-13 |
| `PERSON_TABLES` standing review question, asked of the tables E2 adds | E2-05 (answered in its PR body) |
| Term-map re-derivation (E2 or E11 per ADR 0018/0021) | **E11** — Todd, 2026-08-31 |

Every other `carried-from-e1.md` entry passes through by being re-listed in
`carried-from-e2.md` at E2-13 — the completeness rule is *every entry not
closed inside E2, whoever owns it*: E3's signing-key custody and AGS token,
E4's reveal-subject guard with its deadline, E9's logout and the web-login
linkage, E11's squat repair and CSP write-time rejection, E13's structural
`PERSON_TABLES` source and local-account fallback, and the mock-conditional
pins. One entry has a floating owner and therefore a watch, not a pass:
the TypeScript 7 pair belongs to "whichever epic is running when
`typescript-eslint` admits 7.x" — E2-13 checks at exit whether that happened
on E2's watch.

## What E2 deliberately does not do

Named so scope creep has something to push against. Each item has an owner.

- **Term-map and term edits re-deriving sections or reconciling weeks** —
  E11's calendar editor, with ADR 0018's lengthening hazard and ADR 0021's
  re-derivation both recorded there. Todd ruled 2026-08-31. E2-06 tolerates a
  missing week loudly; it does not repair one.
- **Window-rhythm and threshold configuration surfaces** — §6.3, E11. The
  rhythm ships as cited constants.
- **Moderation, summaries, drafts, draft checks** — E6, E4, E7; their
  contracts exist and stay dormant. The mock (E2-07) grows their verdicts in
  those epics.
- **Grade passback reading validity state** — E3. E2-08 writes the state E3
  will read and nothing reads it yet — a fact the PR states rather than
  hides (the lesson of "a fix round creates the defect it appears to fix":
  a field nothing reads is a claim, not a behavior).
- **The student results view** — E8.
- **Validity-rate surfaces** — E4 (instructor and leadership only, §3.3).
- **A frontend unit-test runner** — not added; E2-13's e2e and the API tests
  carry the behavior. Cost: component-level regressions surface later, in a
  browser run instead of a unit run. Revisit when a screen's logic outgrows
  what e2e can pin cheaply.
- **Threat/self-harm eval set and floor value** — E10's; E2-12 builds the
  structure that refuses to silently pass a floored task with no set.
- **Notifications** of any kind — E12's, including the survey-open notice.

## How CI tightens in E2

One flip, the last one: the AI eval floors (E2-12). ADR 0002's own closing
line then binds — after this, a new tolerant gate is a smell, not a
precedent. The flip is proven by breaking (MISTAKES entries 9 and 36): the
planted floor breach runs red, the detect-probe planted-tree tests still
hold, and the lowered-floor review fixture still trips `prompt-eval`.

The eval job's path condition is **step-level**, per ADR 0002's amendment —
the aggregate treats a skipped job as failure, so the job always runs and its
steps decide. A job-level `if:` is the shape
`test_the_aggregate_ci_check_sees_an_upstream_failure.py` refuses.

## Notes on the decomposition

- **01 and 02 are inherited guards with deadlines, built before the surfaces
  that make them urgent exist.** Same principle as E1-01: the red case is
  honest while the temptation is still unbuildable.
- **04 before 06, and 06 written against 04 from the start.** Retrofitting a
  clock under scheduling logic that already calls `datetime.now` is how a
  site gets missed; the service exists first, so the window code never has a
  direct call to migrate.
- **05 is schema only.** The constraints land before any fixture or write
  path exists to violate them — the late-schema-rule lesson from E0-33's 41
  broken fixtures, taken forward.
- **07 exists so that 08's and 13's interesting paths are drivable.** Without
  a mock in the stack, the bounce clause of the exit line is only testable
  with real tokens or not at all, and the fail-open path needs a stall nobody
  can produce on demand.
- **08 and 09 split write from read.** The submit diff a reviewer walks is
  validation and gating, not view logic; the invariant test lands with the
  read path it polices.
- **12 is independent and can land any time.** It measures the E0-13 task as
  shipped; nothing in the survey chain changes the prompt or the contract.
  If a floor cannot be met by the shipped prompt, that is a finding for
  Todd, not a reason to hold the epic.
- **Every ticket that touches the seed** (05, 06, 07's env defaults) stays
  behind the development-environment guard (ADR 0063, 0064). The dev clock
  override is inert outside development by construction, and E2-04 asserts
  it.
