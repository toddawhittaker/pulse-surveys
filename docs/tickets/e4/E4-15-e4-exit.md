# E4-15 — E4 exit

**ID:** E4-15
**Branch:** `e4/e4-exit`
**Depends on:** everything
**Lane:** heavy
**Security-relevant:** the boundary reviews are the point; and the seed work
touches `scripts/seed.py`, a heavy row.

## Context

§14.3 E4's exit clause — **an instructor opens a real Monday report for a
seeded section with a diverging two-stream story** — driven against the
running stack, plus the epic-boundary obligations §14.2 item 6 names and the
record-keeping E3's exit set the precedent for.

"Diverging two-stream story" is the demo the product exists for: a section
where the instructor stream trends up while the course stream trends down
(or the reverse), across enough weeks that the stacked pair shows it — which
the current seed does not contain and this ticket adds.

E3's closing lesson governs the review roster: reconcile it against the
review skill's own trigger list rather than a memory of it, and re-resolve
by id every CI run the epic's records cite. E3's retroactive finding — that
`privacy-authz` never fired during the epic that should have tripped it most
— must not repeat in the epic built almost entirely of read paths: this exit
runs `privacy-authz` over the epic diff whole, whatever the per-PR
triggering did.

Read first: SPEC §14.2 item 6, §14.3's E4 entry and exit line; §5.1 whole
(the exit drive asserts its clauses); `docs/tickets/e3/E3-08-e3-exit.md` and
`../e3/boundary-review.md` (the shape of the record this produces);
`carried-from-e3.md` whole, one last time.

## Scope

- **The seed's diverging story:** multi-week responses for a seeded section
  producing the two-stream divergence, plus a below-threshold week and a
  section that crosses the cumulative release threshold — the exit drive's
  raw material, behind the development guard as always.
- **The exit drive:** a Playwright spec (its own project, ordered last, the
  E3-08 shape) driving instructor launch → report → the diverging pair →
  both groups led by summaries → a small-N week's concealment → week
  navigation, against the seeded stack on the dev clock, using E3-07's
  trigger precedent for anything the beat schedule makes undrivable.
- **The boundary reviews:** epic-exit, invariant-coverage (did the §4.1
  suite grow over every read path E4 added — items 3, 6 and 7 all moved
  this epic), adr-docs-completeness, a11y-copy (the first epic with enough
  UI to make it earn its standing mandate), data-model over the epic's
  migrations, prompt-eval over the summary task, lti-oidc if the exit
  drive's launch path changed anything, and the whole-epic `privacy-authz`
  pass named above. Findings become the epic's final batch, never E5's
  inheritance.
- **The de-anonymization statement verified:** E4-04's ADR made the written
  statement; this ticket re-reads it against what actually shipped
  (including E4-12's copy and the release presentation as built) and
  records the verification in the boundary review — the carried entry's
  done-when for E4's half.
- **The records:** `../e5/carried-from-e4.md` under E3's completeness rule
  (every open `carried-from-e3.md` entry re-listed or closed with what
  closed it, every E4 deferral with owner and done-when); `deferred.md`'s
  cleanup pass; the build-order table's Merged column filled; the
  session-read sweep re-affirmed over the new report modules;
  `PERSON_TABLES` re-asked of E4-02's tables; the TypeScript 7 check
  re-dated.

## Acceptance criteria

1. The exit drive passes against the seeded stack, asserting §5.1's
   substance: the divergence is visible in the DOM's data, both summaries
   render with their counts, the small-N week's network response contains
   no suppressed comment, and navigation reaches every published week.
2. Every boundary review above has run, its findings are triaged, and the
   fixes landed inside the epic — with the review roster reconciled against
   the skill's trigger table in the boundary record.
3. The whole-epic `privacy-authz` pass has run over the epic diff and its
   verdict is in the boundary record.
4. `carried-from-e4.md` satisfies the completeness rule, demonstrated the
   E3 way: a ledger naming every source entry and its disposition.
5. Every CI run cited in the epic's records re-resolved by id with
   `conclusion == success` (MISTAKES 42's rule).
6. The de-anonymization verification is recorded (scope item above).
7. The epic's PR into `main` is opened only after all of it, and waits for
   written approval — the standing rule, restated where it binds.

## Known traps

- **The invariant pass has no collection-count floor** — the carried
  denial-module entry's sharpest fact. The boundary record states the
  invariant count before and after E4 so a silent shrink has a named
  baseline, even though the structural floor remains carried.
- **Seed identifiers partition like everything else** — the NURS-prefix
  lesson (MISTAKES 48): new seed entities take names that collide with
  nothing existing tests assert about.
- **A drive on the dev clock crosses currencies** — ADR 0142 before any
  clock arithmetic in the spec's fixtures.
- **The review-fixture worry is real at boundaries** — reviewers can leave
  the repo on another branch and the stack in another state; the memory's
  checklist (branch, stray files, tools still present) runs after every
  review session.

## Out of scope

- Anything a boundary review finds that is E5's by nature — it goes to
  `carried-from-e4.md` with an owner, per the review-debt rule, only if it
  cannot land here; the default is it lands here.
