# E0-31 — Review debt from E0-17

**ID:** E0-31
**Branch:** `e0/review-debt-e0-17`
**Depends on:** E0-17

## Context

What E0-17's two review passes found and could not close in place, plus the two
questions E0-17 deliberately raised rather than answered. What could be closed in
E0-17's own pull request was, and it is indexed at the bottom.

**One item blocks E0-18** and is the reason to read this before the exit smoke
test is built. The rest are a product decision about the design corpus, a
duplicated literal, and a docstring.

Read first: [ADR 0038](../../adr/0038-the-mock-platform-ships-in-the-base-compose-file.md),
[ADR 0064](../../adr/0064-the-demo-seed-is-idempotent-by-natural-key.md),
[ADR 0065](../../adr/0065-the-demo-institution-registers-a-fictional-platform.md),
SPEC §8 and §2.1.

## Scope

### 1. E0-18 needs an `lti_platform` row for the mock LMS, and nothing creates one

E0-17 seeds a **fictional** platform at `https://lms.pulse-demo.invalid` — a
reserved-TLD address that resolves nowhere and for which no key exists — precisely
so that ADR 0038's safety argument survives. That argument is that the mock
platform is safe in the base Compose file because it is trusted only by a row in
`lti_platform`, and no such row exists anywhere in the repository. A repository
grep still returns only the Compose file, the mock's own source, and ADR 0065's
sentence about it.

**E0-18 drives a real launch from the mock LMS, and that launch will be rejected**
until something registers the mock's issuer. Whoever adds that row closes ADR
0038's gap in the wrong direction unless the registration is unreachable from a
deployed environment, and ADR 0038 is amended to say what enforces that.

This is E0-17's criterion 2 arriving one ticket later, on the ticket that actually
needs the row. It cannot be settled by E0-17, because E0-17 correctly declined to
create a registration it did not need.

Done when: E0-18 can launch, the registration is unreachable from a deployment,
and ADR 0038 says what makes it so.

### 2. `design/`'s 27 course numbers all fail SPEC §8's bands

Every distinct course number written across `design/` is four digits and below
`8000`, which is the gap between the two bands: `BIOL 2150`, `CHEM 1210`,
`MATH 1610`, `PSYC 1010` and the rest. There is no survivor.

E0-17 picked its seed numbers against §8 and **deliberately did not reconcile
either side**, which was the right call for a seed ticket. The decision remains:
renumber the design corpus, or record that it stays as illustration and is not a
source of seedable data. SPEC §2.1's own two examples were renumbered when the
bands landed; `design/` was not, because it is a design deliverable rather than
schema.

Whoever decides this should note that E0-17's README section now describes a demo
institution whose numbers disagree with every screenshot, and that a developer
reading both will assume one of them is wrong.

### 3. `DEVELOPMENT_ENVIRONMENT` is spelled in two files

`backend/app/db.py` and `scripts/seed.py` both carry the literal. It belongs
beside the field in `backend/app/config.py`, imported by both. E0-17 did not do it
because it crosses a module boundary that ticket does not touch.

Two constants in two files with no test comparing them is the shape that produced
`docs/MISTAKES.md` entry 3's application-role incident — a fixture and a migration
naming the same role differently, where nothing noticed because each was internally
consistent.

### 4. An unreachable adoption path worth a sentence

`Institution.name` is matched unscoped, so a collision would be **adopted** rather
than refused — and three role assignments are scoped to `("institution",
INSTITUTION_NAME)`, so the blast radius would exceed the prefix case E0-17 fixed.

It is not reachable, because `Pulse Demo University` is not a name a real
institution uses, and that is the whole of the protection. The reviewer checked it
and deliberately did not report it as a finding. The rule ADR 0064 now carries —
every natural key is either scoped to a row the seed created, or a root matched by
a value this file invented — is what makes it safe, and the module docstring
should say which of the two `Institution.name` is relying on.

### 5. Two files outside `scripts/` that E0-17 touched

`backend/app/db.py` and `backend/app/config.py` were edited to correct citations
of SPEC §6.3 for something that section does not say — `ENVIRONMENT` and `healthz`
each appear zero times in the spec. The corrections are right and were made in
E0-17's pull request; they are recorded here only because they are outside that
ticket's stated scope, so a later reader of the diff is not left wondering.

## Out of scope

- Responses, comments, classifications and reports — the seed loads structure only.
- The admin console people editor and CSV import (E9, E11).
- Performance-scale data for the 500-section load test (E13).

## Acceptance criteria

- [ ] E0-18 can complete a launch from the mock LMS, and whatever registers the
      mock is unreachable from a deployed environment with ADR 0038 amended to
      say what enforces that.
- [ ] The `design/` question is decided one way and recorded, not left as two
      corpora that disagree.
- [ ] `DEVELOPMENT_ENVIRONMENT` has one definition, or a test asserts the two
      copies agree.
- [ ] `Institution.name`'s protection is stated where the loader is edited.

## Definition of done

**Tests apply** to item 3 if the literal is consolidated rather than asserted.

**Docs apply** to items 1, 2 and 4.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies and matters for item 1**, which is the one place where
closing a gap carelessly makes a deployed environment trust a mock platform.

## What E0-17's review did close

Three MED across two passes, plus a dispute escalated to Todd:

- **MED** — the seed adopted org rows it did not create. `prefix.code` is unique
  table-wide rather than per institution, so `make seed` against a database
  holding real org data re-pointed real prefixes at the demo institution,
  overwrote colliding course titles, and replaced real lead-faculty mappings with
  demo people. The yield was an authorization change, and the run exited 0.
  Reproduced by planting a real institution, fixed by refusing rather than
  adopting, and re-measured: exit 2, real rows untouched, no partial demo
  institution, because the refusal lands inside the one transaction.
- **MED** — the records said nine unmapped courses; the seed leaves eight. Also
  `README.md`'s "a second run writes nothing", true only of the empty-database
  case.
- **MED** — the reviewer gating table had no `scripts/` pattern, so a diff confined
  to `scripts/` fired conformance review alone — and `scripts/seed.py` connects as
  the bootstrap superuser and writes `user_identity`. `scripts/` added to
  `app-security`; `scripts/db-init/` and `scripts/seed.py` to `privacy-authz`.
- **LOW** — the prefix refusal shipping with no test, which was an orchestration
  gap rather than a code one: the tests existed and were uncommitted.

`docs/disputes/E0-17-01.md` records the environment-guard dispute, ruled outcome
three — the records did not decide it — and settled by Todd: the guard reads
resolved configuration, `.env` may supply the permission, and the residual gap
where an operator exports a production `DATABASE_URL` over a development checkout
is **accepted by decision rather than closed**.
