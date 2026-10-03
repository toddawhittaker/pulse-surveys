# E5-11 — Students never see a benchmark, asserted

**ID:** E5-11
**Branch:** `e5/student-benchmark-exclusion`
**Depends on:** E5-05
**Lane:** heavy
**Security-relevant:** the epic's student-facing confidentiality guarantee.
§4.1 item 1 tests join the invariant suite (the isolated pass CI may never
skip); `privacy-authz` fires.

## Context

§4.1 item 1 has been asserted since E2 — students never see other
sections. E5 gives it a new class to refuse: benchmark data now exists and
flows to instructors, so the exclusion must be proven **non-vacuous** — the
same world that shows an instructor three lines shows the student two,
which is the exit's word "provably".

The structural half (the README sketch's third rule): the student payload
schemas carry **no** benchmark member — not suppressed, absent. A member
that exists-but-empty is one route bug away from filled; a member the type
system never admits is not.

Read first: SPEC §4.1 item 1 (its full sentence: charts, text, tooltips,
exports, aria labels), §5.4; the existing item-1 invariant tests (what
this extends and their naming conventions); `backend/app/schemas/` student
schemas; `scripts/ci/check_invariants.py` (the isolated pass this joins);
the carried denial-inventory entry (a new invariant module must land
inside the pass, marked — the E4 boundary paid for names that matched no
shape).

## Scope

- Invariant tests, in the isolated pass, marked per convention:
  - the student payload schemas structurally admit no benchmark member
    (a planted member fails schema construction — asserted as the
    forbidden state, MISTAKES entry 2);
  - every student route's response in the benchmark-bearing world carries
    no benchmark-shaped key at any depth, swept generically (key-name
    sweep over the serialized payload, so a future member has to defeat a
    sweep rather than an enumeration — entry 53's lesson);
  - the positive control: the instructor route in the same world carries
    them.
- The e2e half of "provably": in E5-10's benchmark-bearing world, every
  student surface that exists renders no benchmark text/tooltip/aria
  trace — the DOM swept for the legend vocabulary, with a canary (the
  instructor page's DOM, where the sweep must hit). The literal two-line
  student chart is TrendDuo on E8's results view (breakdown decision 9):
  if it exists when this ticket builds, the sweep covers it; if not, the
  structural and route proofs are the guarantee and the exit records the
  rest.
- The frontend components' absent-prop states (E5-07 criterion 6, E5-08
  criterion 3) cited, not retested.

## Acceptance criteria

1. The schema-structural test fails when a benchmark member is planted on
   a student schema — mutation-proven in review, per the battery.
2. The route sweep covers every student route (enumerated from the app's
   route table, not hand-listed — entry 53), refuses a planted
   benchmark key, and passes the real payloads.
3. The instructor positive control in the same world — without it, an
   empty world satisfies everything (MISTAKES entry 3).
4. The DOM sweep with canary: student surfaces clean, instructor surface
   hits (the canary proves the sweep can see).
5. All backend tests marked into the §4.1 isolated pass; the pass's
   collection grows and the growth is stated in the PR (the
   denial-inventory carried entry's discipline).

## Known traps

- **Vacuous exclusion** — every negative beside its positive, throughout.
- **The sweep's own blindness** — the DOM sweep needs its canary run
  every time, not once at authoring (entry 3's canary rule verbatim).
- **Sequence, not just payload** (entry 51) — a student paging across
  weeks in the benchmark world sees two lines every week; assert over the
  paging path, not one response.

## Out of scope

- New student surfaces — E8.
- The instructor payload's correctness — E5-05.
- Aggregate-language copy — E5-13.
