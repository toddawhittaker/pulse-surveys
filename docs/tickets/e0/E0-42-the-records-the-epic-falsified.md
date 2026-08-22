# E0-42 — The records the epic falsified (Batch I)

**ID:** E0-42
**Branch:** `e0/boundary-docs-sweep`
**Depends on:** nothing unmerged; written from the 2026-08-22 epic-boundary
reviews (adr-docs-completeness, threat-model, epic-exit).

Documentation only. No file under `backend/`, `tests/`, `scripts/`,
`mock-lms/`, `mock-idp/`, or `.github/` changes in this ticket.

## Scope — every item is a record that asserts something the tree contradicts

1. **`docs/tickets/e0/README.md`**: the batch index rows for E0-18, 19, 28,
   30, 33, 34, 36 carry no merged marker while 35 and 38 do; the narrative
   ("18 is next", "all four batches land before the epic merges") describes
   2026-08-20. Bring the index and narrative to the truth at HEAD: every
   batch A–H and E0-18 merged, with PR numbers (18=#57/#61/#62, F=#56,
   E=#64, G=#65, H=#66). Add rows for Batch I: E0-39 (`e0/mock-idp-default-trust`),
   E0-40 (`e0/gate-fidelity`), E0-41 (`e0/invariant-coverage-gaps`), E0-42
   (this ticket), each one line, built 2026-08-22 from the epic-boundary
   reviews.
2. **`docs/adr/README.md`**: row 0048 still calls the no-window denominator
   open ("left to E1") after PR #64 settled it in SPEC §3.4 — correct the
   row. Rows 0025 and 0044 repeat spec-silence claims their sections below
   fix. Add rows for 0077, 0078, 0079 (0077 is written by E0-39 in a sibling
   worktree; its row reads: "0077 — the web door's identity provider is
   named explicitly, and a mock address is refused outside development;
   supersedes 0075 in part").
3. **ADR 0025** context ("the spec's column name describes a table that does
   not exist") and **ADR 0044** context ("It says nothing about whether two
   assignments in the same role may report to one another"): both were
   falsified when the spec was edited to agree with them (`58064c4`,
   `fd703bb`). Amend each with a dated paragraph: the spec now states the
   rule, link the section, keep the genuinely spec-silent remainder clearly
   separated. Do not renumber, do not rewrite history — amend.
4. **ADR 0074**: the link `0063-the-seed-refuses-outside-development.md` is
   broken (the file is `0063-the-demo-seed-runs-only-in-a-development-environment.md`);
   its line ~64 cites "CLAUDE.md's rule about knobs" and **ADR 0037** line
   ~41 cites a rule "CLAUDE.md says not to build" — neither rule is in
   CLAUDE.md since the process-only restructure. Point each citation at
   where the rule actually lives (the design-defaults live in Todd's global
   instructions and the spec; if no in-repo home exists, cite the principle
   without the false attribution).
5. **`CONTRIBUTING.md`**, three divergences from CLAUDE.md (CLAUDE.md wins):
   the `process/<kebab-slug>` tier is missing and "no exceptions" is stated
   flatly (seven process/* branches merged in E0); the Playwright e2e job is
   described as tolerant ("waits for E0-18") after PR #61 made it enforcing;
   the Compose-health list omits `mock-idp`. Do NOT touch its npm-audit row:
   E0-40 makes that row true — note the dependency in the PR body.
6. **`docs/MISTAKES.md`**: add a gap note for the missing entry 32 (mirror
   the numbering-gap note style `docs/adr/README.md` uses) so the next
   author neither reuses 32 nor assumes a deletion; and record the measured
   recurrence of entry 36 (the frontend-gate probes, found 2026-08-22, fixed
   by E0-40) in whatever per-entry form entry 36's file uses. **Date the
   paragraphs from git before editing — entries order instances
   differently** (some oldest-first, at least one newest-first).
7. **SPEC §13**: add the module-placement sentence CLAUDE.md's read-first
   table already attributes to it ("use an existing module; add one only when
   nothing fits" — the rule two E0-18 modules justify themselves against).
   **This is a spec edit: flag it in its own commit and at the top of the PR
   body for Todd's explicit approval.**
8. **ADR 0078 — the login-state cookie** (number reserved): the decision PR
   #57 recorded only in `backend/app/api/deps.py`'s docstring. Four sections
   from that docstring plus the PR: signed HS256 JWT cookie for
   `state`/`nonce`/PKCE across both doors; per-process `secrets.token_bytes(32)`
   key; 300-second lifetime; `SameSite=Lax`; `Secure` keyed on environment.
   Consequences must state plainly: the per-process secret means two `api`
   replicas cannot serve one login flow — scaling past one replica requires
   a shared or configured secret first.
9. **ADR 0079 — the dev console** (number reserved): `GET /dev` exists (PR
   #62, no ticket, no ADR), lists the mock provider's web-login people and
   offers each as a one-click sign-in link through the ordinary web door, and
   its gate is a handler-level 404 keyed on `ENVIRONMENT` — deliberately a
   different mechanism from ADR 0074's route-removal. Record context,
   decision, the 0074 contrast (so a future route-gating refactor does not
   miss it), and consequences. *(Corrected 2026-08-22 during this ticket's
   security review: this item said the console "signs a session as any seeded
   identity", which `backend/app/api/dev.py` does not do — it mints nothing and
   renders links. The overstatement had been copied into ADR 0079's index row
   before it was caught.)*
10. **`docs/tickets/e1/carried-from-e0.md`**, new entries, each with a "done
    when", from the threat-model and coverage reviews (source wording is in
    the PR-body notes I will attach to the dispatch):
    - The two-hat reveal composition: `ActorScope` carries `holds_care`
      beside the purview, and `section_roster` hands instructor-scoped code
      the exact `user_id` the reveal consumes; an E1/E4 report surface
      calling `reveal_identity` with a roster row's id passes every actor
      check. Done when the capability is separated from the read scope (or
      an equivalent guard) with a test that fails on the composition, before
      any instructor-facing surface renders roster rows.
    - `own_grant`/`resolve_scope` verify no caller: the rule "a request may
      only resolve the scope of its own authenticated subject" must land
      with E9's purview walk, with a test that fails on resolving another
      person's id. Done when that test exists and `transitive_purview` no
      longer raises.
    - Hypothesis coverage of purview: sibling-lead disjointness over
      generated supervision forests, deferred to E9's purview service.
    - `/healthz` returns `settings.environment` to unauthenticated callers,
      which discloses the value every environment-keyed guard rests on.
      Recorded as an open decision: drop the field, gate it, or accept it
      deliberately.
    - §4.1 items 4 and 5 (no comparative framing, confidentiality-copy
      count) are enforced by review only; no copy test reads any shipped
      surface against them. Done when either a copy-inventory test exists or
      §4.1's preamble records the deferral beside items 1 and 7.
11. **Raised, not fixed — top of the PR body, for Todd**: ADR 0028 decides
    that a student holds no role assignment while SPEC §2 still reads the
    other way. CLAUDE.md's own rule says an ADR is not sufficient where it
    contradicts the spec; the fix is a spec edit only Todd can approve, and
    E1's role-resolution ticket is blocked on the answer.

## Acceptance

- Every named record matches the tree at HEAD; every claim this ticket adds
  is greppable against the repository (the sweep-last rule: this PR's last
  commit re-checks its own claims).
- All relative links under `docs/` resolve.
- ADRs 0078/0079: four sections, under a page, no restating of spec-decided
  content.
- The full test suite still passes (docs-only, but run it — at least one
  test asserts docs content).

## File ownership (parallel-build boundary — do not cross)

This ticket may touch only files under `docs/`, plus `CONTRIBUTING.md` and
this ticket file. Never `.env.example`, never `docs/adr/0075-*.md` or
`docs/adr/0077-*.md` (E0-39 owns those), never anything under `tests/`,
`backend/`, `.github/`, or the repo root configs. `docs/adr/README.md` is
owned by THIS ticket alone.
