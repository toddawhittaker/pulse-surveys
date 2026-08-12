# Pulse Surveys — operative constraints

Full detail lives in `docs/SPEC.md` and `docs/DESIGN_BRIEF.md`. This file lists
what must not be violated. Where the two documents disagree, the spec wins (it
is later); the brief still governs anything the spec does not restate. Process
rules are in `CONTRIBUTING.md`; the branch and pull request section below is the
operative summary.

## Branch and pull request discipline

`main` is protected. Never commit to it, never merge into it locally, never
force-push anything anywhere. Every change reaches `main` through a pull
request, and so does every change to an epic branch.

Three tiers. `main` holds reviewed work. One long-lived **epic branch** per
epic in SPEC §14.3, named `epic/e<N>-<kebab-title>` (`epic/e0-foundations`,
`epic/e1-entering-the-app`), cut from `main`. One short-lived **seam branch**
per ticket seam listed under that epic, named `e<N>/<kebab-seam>`
(`e0/compose-stack`, `e0/core-schema`, `e1/launch-flow`), cut from its epic
branch. Seam branches merge into their epic branch by pull request; epic
branches merge into `main` by pull request. No exceptions, no direct merges in
either direction. `CONTRIBUTING.md` has the full epic branch name table.

For every unit of work, in order:

1. Confirm which epic branch the work belongs to. Create it from `main` if it
   does not exist yet.
2. Cut a seam branch from that epic branch. Never work directly on the epic
   branch.
3. Commit in small, coherent steps. The subject line names the seam:
   `e1/launch-flow: validate state and nonce on LTI launch`.
4. Open a pull request into the epic branch when the seam is done. Use the
   template: state the seam, the §14.2 definition-of-done items covered (tests,
   AI evals, separate-agent security review, accessibility, docs), and anything
   deliberately deferred.
5. Stop and wait for Todd. Do not merge on your own judgment that the seam
   looks finished.

Merge authority splits by target branch. **Never merge an epic branch into
`main`** — that is Todd's call, always, without exception. You may merge a seam
pull request into its epic branch, but only after Todd has approved it in
writing in the conversation; his approval is the trigger, never your own
assessment. Never use an admin override to bypass a protection rule. Never
merge anything while CI is failing. Never retarget a pull request across
epics — close it and re-cut the branch.

## CI and build discipline

CI is what makes the §14.2 definition of done enforceable instead of
aspirational. Treat a red pipeline as information, never as an obstacle.

**Never merge or mark a pull request ready with red CI.** Not "it's unrelated,"
not "it passes locally." Run `make ci` before pushing; it runs the same gates in
the same order as `.github/workflows/ci.yml`. When the two disagree, the
workflow is right and the Makefile is the bug.

**Never skip, xfail, mark flaky, or delete a failing test to make CI pass.** A
failing test is either finding a real defect or is itself wrong. If the test is
wrong, fix the test in its own commit, separate from the change that provoked
it, and say in the pull request why the old assertion was incorrect. Deleting a
red test and reporting green is a false report about the state of the system.

**The §4.1 invariant suite may never be skipped.** CI runs it in an isolated
pass and treats a skip, an xfail, or an empty collection as a failure, because
in a green checkmark those are indistinguishable from a passing assertion.
`scripts/ci/check_invariants.py` enforces this.

**Never weaken an eval floor to get a gate to pass.** Precision and recall
floors move only in a deliberate pull request whose subject is moving them and
whose body says why the new number is right. The threat and self-harm recall
floor is the strictest in the suite (§9.3) and is a hard gate: a false negative
there is a student in danger whose comment reached nobody. Lowering it is a
safety decision, not a build fix, and it is Todd's call, never yours.

**Every pull request gets `/security-review` in a separate session before it is
marked ready** (§14.2 item 3). Record what it found and how each finding was
resolved in the pull request body. On a ⚠ epic (E1, E9, E10, E13) that review
supplements line-by-line human review of the security-relevant diff; it never
replaces it.

**Pin dependency versions and commit lockfiles.** No floating ranges, no
unpinned tool versions in CI. Dependabot proposes upgrades as pull requests that
go through the same gates as anything else.

**Do not weaken a gate to get past it.** Adding an ignore rule, an exclusion, a
`continue-on-error`, or a raised budget is a change to what the project
guarantees. Any of them belongs in its own pull request that says what coverage
was given up and why. The tolerance flags in `ci.yml` exist only because the
tree is still empty: each one names the seam that removes it, and that seam
removes it.

## Architecture decision records

When a construction decision is **not answered by `docs/SPEC.md`** and a
reasonable engineer might choose differently, write
`docs/adr/NNNN-slug.md` **in the same pull request as the decision**. Four
sections, under a page: context, decision, alternatives rejected and why,
consequences.

- **Never write an ADR restating something the spec already decides.** Link to
  the spec section instead. An ADR that paraphrases §7.4 is noise that makes the
  real ones harder to find.
- **If a decision contradicts the spec, an ADR is not sufficient.** Raise it,
  and update the spec. A record of having gone around the spec is not the same
  as the spec being right.
- The test is both halves together: the spec is silent, *and* the choice is
  genuinely contestable. Picking a JSON library needs no ADR. Picking how
  identity separation is enforced does.
- Number sequentially, never reuse a number, and do not renumber. A superseded
  ADR stays in place with a line at the top pointing at the one that replaced
  it.

## Secrets

Never create, read, modify, or echo a repository secret or an environment
secret. Never add a secret reference to a workflow without asking first — that
includes a new `secrets.*` expression, a new environment binding, and widening
an existing one. Ask, then wait for an answer; do not add it provisionally.

Local secrets live in `.env`, which is gitignored and must stay that way.
`.env.example` is the committed counterpart: it carries variable *names* and
obviously-fake placeholder values, never a real credential, and never a value
copied from a working `.env`. When a seam adds a configuration variable, add
its name to `.env.example` in the same pull request.

Do not print the contents of `.env`, paste a credential into a commit message
or a pull request body, or write one into a test fixture, a seed script, or a
log line. If a real secret is needed to run something, say what is needed and
let Todd supply it.

## Confidentiality invariants (SPEC §4.1)

These are automated assertions in the test suite, not conventions. Every read
path must satisfy them, and a change that weakens one is a defect regardless of
how it improves anything else.

1. Students never see comparables, benchmarks, university averages, or other
   sections — not in charts, text, tooltips, exports, or aria labels.
2. A Lead Faculty assignment never grants a sibling lead's courses, at any point
   in the purview union computation.
3. Below the n-threshold (default 5 responses in a reporting week), raw comments
   are hidden from instructors and students alike.
4. Aggregate language counts sections, never instructors. Say "needs attention,"
   never "underperforming." No ranking, no composite scores, no score-sorting
   anywhere.
5. Confidentiality copy appears exactly once per surface (on the survey: in the
   submit bar), in plain words, with no shield or lock iconography.
6. No view may ever widen a student's visibility relative to these rules.

Supporting rules that make the above hold:

- Responses are keyed to the LMS user ID. Identity is never displayed to any
  instructor or leadership role, in any view, including CSV export.
- Re-identification is possible only through the Care queue, only by the Care
  role, and is automatically audit-logged (actor, timestamp, case). Admin and
  VPAA cannot read flagged comment content or reach identity.
- **A reveal that touches the revealer's own purview is flagged as a conflict of
  interest** (SPEC §6.2). A Care staffer revealing a student in a section they
  themselves teach is the case that matters. Never block the reveal — a student
  at risk does not wait on a governance check — but mark the audit entry, and
  surface it distinctly in the Admin access log and to the periodic outside
  review. This is the detective control that makes the permitted overlap between
  a Care assignment and a reporting assignment visible rather than merely
  tolerated. Any audit schema must be able to carry this flag.
- Instructor and leadership read paths go through identity-separated SQL views
  that structurally cannot join to identity columns. Enforce this in migrations
  (`backend/app/views_sql/`), not only in application code.
- Comment display order is randomized; timestamps are never shown with comments.
- Small-N comments are not discarded — they feed AI summaries and are released
  as raw text in a batch once cumulative term volume crosses the threshold, so
  release timing cannot identify an author.
- Threat and self-harm content appears only in the Care queue. Below small-N,
  flagged comments are concealed from the instructor entirely (no chip, no
  count, no flag-type hint) while routing to the reviewer immediately.

## Roles and purview (SPEC §2.1)

- People are not roles. A person holds one or more *role assignments*, each
  scoped to an org node. Every view resolves from an assignment or a union of
  assignments, never from a person "type."
- Two decoupled structures, neither derived from the other:
  **containment** (Institution → College → Department → Prefix → Course →
  Section) drives navigation and aggregation; the **supervision graph** drives
  purview and escalation.
- `reportsTo` edges connect **assignments**, never people and never org nodes.
  The graph is a forest/DAG over assignments; assignment-level cycles are
  rejected at write time, person-level cycles are legal and expected.
- Purview(assignment) = own grant ∪ purviews of all assignments transitively
  reporting to it, with the own grant restricted by role grain (a lead's grant
  is only their led courses; a chair's the department subtree; a dean's the
  college). The assistant dean — led courses ∪ every supervised chair's
  department — is the case that proves purview cannot come from containment.
- Lead Faculty get the hierarchy view only, never a by-lead-faculty pivot. Chair
  and above additionally get the by-lead pivot over their purview.
- Care is deliberately not composable with any reporting role: a Care assignment
  grants no reporting purview, and no reporting assignment grants Care. Its only
  power is the threat queue. One *person* may nonetheless hold both — a Care
  staffer who also teaches a section is unlikely but legitimate — so the two are
  separate capabilities on the same person, never a union. Do not add a
  constraint forbidding the combination; it is an accepted risk, governed by the
  ethical obligations of the Office of Community Standards and by the identity
  -access audit log.
- **Entry doors are a property of the assignment, not the person.** Every
  reporting role (instructor, lead faculty, chair, assistant dean, dean, VPAA)
  can enter by LTI launch. Every role except instructor and student can *also*
  enter by OIDC web login; leadership holds both doors, and Care and Admin are
  web login only. Students enter by launch only. A person holding two
  assignments uses whichever door fits the assignment they are acting under.
- Both doors resolve to the same identity and the same full purview. The launch
  context resolves which section a link points at; it never caps what a
  leadership user may see.
- LMS-owned data (courses, sections, section codes, enrollments, teaching
  instructors) is read-only in Pulse. Course level derives from the course
  number; section length and dates derive from the section code via the
  start-letter map. Nothing LMS-owned is hand-edited here.
- All authorization scoping goes through `backend/app/services/authz.py`. Every
  entry point — HTTP, Celery job, future MCP server — passes that chokepoint.

## Single-shot AI boundary (SPEC §7.4)

- The five gateway tasks (comment validity, moderation, weekly summary, response
  draft, draft check) are each **one call in, one validated Pydantic object
  out**. No tool use, no planning loop, no iterative retrieval. This protects
  the p95 < 2s validity budget, the CI precision/recall gates, and the
  auditability of a safety flag (a specific prompt version and model ID produced
  a specific classification for a specific comment).
- Every classification stores its prompt version and model ID. Prompts are
  versioned in-repo under `backend/app/ai/prompts/`.
- The output contract models in `ai/contracts.py` serve three roles at once —
  runtime contract, API schema, eval fixture. Do not fork them.
- Validity gating fails open: on provider timeout the character heuristic floor
  applies, the submission is accepted, and classification runs async. Never
  block a student on a provider outage.
- Agentic loops live in `backend/app/agents/` and consume the authz-scoped
  services; they never live inside the gateway, are read-only, and never touch
  the student-facing or grading paths. AI never publishes anything — a human
  presses publish.

## Repository structure (SPEC §13)

Monorepo, laid out as specified in §13. Two structural rules carry weight:

- `api/` routers stay thin. All domain logic lives in `services/`, so the HTTP
  API, Celery jobs, and the future MCP server share one implementation and one
  authorization chokepoint.
- Identity-separated read views ship as Alembic migrations in `views_sql/`, not
  as ORM convention, so confidentiality survives a future careless query.

Keep the top-level shape: `backend/`, `frontend/`, `mock-lms/`, `mock-idp/`,
`tests/{unit,integration,e2e,evals}`, `scripts/`, `docs/`, `design/`, with
Compose and the Makefile at the root. New backend code belongs in an existing
§13 module; add a new one only when nothing fits.

## Design rules (DESIGN_BRIEF)

The prototype in `design/` is the visual and interaction contract. The frontend
implements it; it does not reinterpret it.

- **Chart family.** TrendPair wherever benchmarks are present (instructor
  report, leadership). TrendDuo for the two-stream benchmark-free case (student
  results). Single-line for one-stream contexts. Section line is marigold,
  solid, 2.5px, with a dot on the current week; benchmark is mist dashed;
  university is mist 50% dotted. Course-level pages plot course week with a term
  week sub-label; aggregate pages plot the term axis with one line per start
  cohort.
- **Madder (`--madder`) is reserved** for flags, destructive actions, and the
  required state — it always means "attend to this." A conditional-required
  field warming up is an invitation, so it uses marigold, not madder. Nothing in
  this product shames: no shake, no red on a student who wrote too little.
- **Motion budget.** Micro-interactions 150–220ms ease-out. Exactly one 600ms
  signature moment per screen (the hero line drawing once per visit). All motion
  removed under `prefers-reduced-motion` via the global kill switch.
- **The Care queue has no motion at all.** Stillness is the design. It also
  carries a distinct quiet register, no search, no filters beyond
  Open/Resolved, no bulk actions — the UI must not imply triage at scale.
- One signature motif (the pulse line), zero other decoration. All color, type,
  spacing, radius, shadow, and focus values come from `design/tokens.css`; no
  raw hex in components. Focus ring is 2px marigold at 2px offset on every
  interactive element.
- Type: Literata (display), Schibsted Grotesk (body), Spline Sans Mono (all
  numbers). No Inter, Roboto, Arial, Lato, or system stacks. Never use Canvas
  blue (#0374B5) for interactive elements.
- Radius 4px inputs, 8px cards. Report and survey surfaces use a single ~720px
  reading column, not a dashboard grid; leadership may go two-pane and dense.
- Every prototype primitive becomes one React component with variants, never a
  per-screen copy.
- WCAG 2.2 AA is a floor: full keyboard operability inside the iframe, and every
  chart carries a data-table equivalent.
