# E0-27 — Review debt from E0-11

**ID:** E0-27
**Branch:** `e0/review-debt-e0-11`
**Depends on:** E0-11

## Status — where this ticket's items went

**Not built as written. One item is closed and the other two have moved.**

| Item | Now |
|---|---|
| 1 — nothing requires a write path to call `guard_write` | [E0-35](E0-35-the-writer-and-the-marker-nobody-routed.md) — **built 2026-08-19** |
| 2 — a view revision can widen identity access with no grant consulted | [E0-34](E0-34-view-file-identity-guards.md) — **built 2026-08-18** |
| 3 — `docs/MISTAKES.md` is out of order | **Closed** in PR #36 |

On item 3: the file is now sorted by `Caught:` descending with every entry
keeping its number, and the tier is re-derived from the same numbers.

**On item 1, as built.** This ticket named the choice and declined to make it;
Todd made it on 2026-08-18 and
[ADR 0069](../../adr/0069-three-rules-held-by-a-docstring-are-swept-out-of-the-source.md)
records it. **The sweep won, the session-level hook was rejected** — on cost, on
matching the read-side sweep already in the tree, and because the hook's failure
mode when it is wrong is a refused legitimate write in production rather than a
red test. The hook's real advantage, catching the indirect writes a syntactic
sweep cannot see, is stated in the record rather than argued away.

As built, a module under `backend/app/` that writes `course`, `section`,
`enrollment`, `user`, or a `role_assignment` row whose role is `INSTRUCTOR`, has
to call `guard_write` somewhere in the same module. Two things it does not do,
both in ADR 0069 and in the sweep's own docstring: its grain is the module and
not the path, so it never shows that the guard ran before the write; and it does
not close the seam, which needs the grant
[ADR 0045](../../adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)
defers to E1. **One question is left open on purpose** — how a *sanctioned*
writer satisfies "calls `guard_write`" when `guard_write(table="course")` refuses
unconditionally. Todd's decision, 2026-08-19: write it down and leave the
mechanism to E1, which arrives with a real writer to design against.

The section below headed *What E0-11 closed* is the record of that round,
including the note on the invented statements committed to this branch's history.
It moves nowhere.


## Context

What E0-11's review found and could not close in place, collected the way E0-21
collects E0-05's, E0-24 collects E0-07's and E0-08's, E0-25 collects E0-09's,
E0-12's and E0-14's, and E0-26 collects E0-10's. What could be closed in E0-11's
own pull request was, and it is indexed at the bottom so this file is a complete
record of the round rather than a list of what was skipped.

**Neither item here blocks anything, and both are about the same weakness.**
E0-11's read path is guarded three ways over — a database grant, a view boundary,
and a structural sweep that fails when a service module reaches an identity table.
Its write path and its view files are guarded by one thing each, and in both cases
that one thing is a person reading a diff. Nothing is wrong today; what is missing
is the assertion that would notice when something becomes wrong. E1 is the first
ticket that can trip either.

Read first: [ADR
0045](../../adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md),
[ADR 0041](../../adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md),
[ADR 0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md), and
`docs/MISTAKES.md` entries 2 and 3.

## Scope

### 1. Nothing requires a write path to call `guard_write`

**The gap.** `services/authz.py` refuses an LMS-owned write at table grain plus
the instructor row, and its docstring says it is "called by every application
write path before it writes". Nothing calls it. That is correct in E0 — no write
path exists — and it means the guarantee currently rests on a sentence in a
docstring.

The eight tests covering it all call `guard_write` directly, so they assert that
the guard answers correctly when asked. None of them can notice a future write
path that never asks. That is the asymmetry with the read side, where
`tests/unit/test_no_service_reads_an_identity_table_directly.py` fails when a
service module reaches an identity table whether or not anyone remembered a rule.

**Why E1 is the deadline rather than a nice-to-have.** E1's roster sync is the
first code that writes `course`, `section`, `enrollment` and the `INSTRUCTOR`
`role_assignment` row — every relation the guard names, all four of them, in the
one module. If that module does not call `guard_write`, nothing fails, and ADR
0045's rule becomes a description of something the codebase used to intend.

**Two shapes worth comparing before either is built.** A static sweep modelled on
the read-side one, which asks whether a module that writes those relations also
names the guard; or a session-level hook that refuses an unguarded flush, which
catches the call that a sweep would miss and costs a hook on every write in the
system. The static sweep is cheaper and weaker. Neither is obviously right, which
is why this is a ticket rather than a line in E0-11.

Note that this is the write-side twin of [E0-21](E0-21-review-debt.md) item 1,
which owns the other half — detecting an LMS-owned column that was never marked.
ADR 0014's open half stays open there, and closing either does not close the
other: E0-21 item 1 is about a column nobody marked, this is about a writer nobody
routed.

### 2. A view revision can widen identity access with no grant consulted

**Measured, on the pinned Postgres, with the stack at head.** All five views —
`section_roster`, `section_enrollment_count`, `assignment_scope`,
`lead_faculty_course`, `containment_path` — are owned by `pulse_admin` with
`security_invoker` off, so each executes with its owner's privileges.

That is load-bearing and intended: it is exactly what lets `pulse_app` read
`role_assignment` and the six containment tables while holding no grant on any of
them. The consequence is that **the grant model does not protect the view files
themselves**. A `_v002` of any of the three E0-11 added that joined
`public.person` would hand `pulse_app` a name, and no grant would be consulted on
the way.

What stands between that and a deployment is ADR 0041's rule — a view ships as a
new immutable versioned file that a migration executes, so the join appears in a
diff somebody reads — together with the structural sweep in
`tests/integration/test_identity_column_marker.py`. Neither of those is the server
refusing it, and E0-11 tripled the number of owner's-rights views sitting over the
tables the resolver must not reach past.

**The `authz.py` docstring already says this**, corrected in E0-11 from a claim
that overstated it. What is missing is the assertion.

### 3. `docs/MISTAKES.md` is out of order

Housekeeping, and the file's own convention asks for it: "Sort by `Caught:`
descending when you notice it is wrong." E0-11's rounds bumped nine counters and
re-ordered nothing, twice saying so in a report rather than doing it. Entry 19 now
ties at 1 and sits below the 0-group; entry 2 ties with entry 1.

Moving whole sections is a larger and riskier edit than any of the rounds that
caused it wanted to take on mid-ticket, which is exactly how a sort debt
accumulates. **An entry keeps its number when it moves** — that rule is in the
file's header and it is what makes the sort safe, because every citation elsewhere
is by number.

## Out of scope

- **The same-role edge question.** Dispute
  [E0-11-01](../../disputes/E0-11-01.md) framed it and SPEC §2.1 now answers it:
  "Two assignments in the same role never report to one another." That paragraph
  landed in E0-11 with Todd's approval, so the question is settled in the document
  that governs, and this ticket does not reopen it.
- **The rank rule's backfill.** E0-11's migration validates stored edges and
  refuses to install the rule over data that breaks it, so the residue the
  arbitration named is closed rather than carried.
- **The transitive purview union**, which is E9's and is the seam ADR 0003 keeps
  fail-closed.

## Acceptance criteria

- [ ] A module that writes `course`, `section`, `enrollment` or an `INSTRUCTOR`
      `role_assignment` row without calling `guard_write` fails something. The
      test demonstrates it by adding such a writer and watching it go red, not by
      asserting against the modules that exist today.
- [ ] A view file that selects an identity-bearing column fails something — or the
      record says plainly that nothing catches it, and why that is acceptable
      given ADR 0041.
- [ ] `docs/MISTAKES.md` is sorted by `Caught:` descending, every entry keeping
      its number, and no citation elsewhere in the repository points at the wrong
      entry afterwards.
- [ ] The first two verified by mutation — reintroduce each defect and watch it
      fail.

## What E0-11 closed, so this file is the whole round

**From the security review.** The HIGH: `own_grant` rooted an `ASSISTANT_DEAN`
assignment at its college, making it identical to a dean's and handing it every
department in the college including those whose chairs report straight to the
dean — which contradicts the one sentence in SPEC §2.1 that uses this role as its
worked example. The own grant is now empty, with three tests and a dean control.
The MED: the trigger is `AFTER INSERT OR UPDATE`, so it examined no stored row and
a database migrated from E0-09 could keep an edge the rule refuses; `upgrade()`
now queries for those rows and raises naming each one, and says so in the emitted
script when run offline where it cannot query. Both LOWs are items 1 and 2 above.

**From the two arbitrations.** Dispute E0-11-01: three E0-09 tests built their
graphs from same-role edges the rank rule refuses, and the ruling moved the
controls; the generators now draw a strictly climbing role sequence. It also found
three tests named for the cycle guard that reached the rank rule instead and were
green doing it — they now plant a non-climbing edge under the superuser bypass so
the recursive walk has a subject that exists. Dispute E0-11-02: three downgrade
tests reached their subject relative to head, so they measured this ticket's
revision while asserting facts about E0-10's; they now name the revision at both
ends and derive the parent.

**Also closed there:** the mirror rule on a parent's role change got its first
assertion with the control that kills a version implemented by clearing the
children's edges; SPEC §2.1 gained the "An edge climbs" paragraph, so the rule the
product enforces is stated where the spec governs; ADR 0027 was amended for the
two rules added to its trigger; ADR 0046 was corrected for the assistant dean and
for what an empty own grant means, which is the opposite thing for Care; and the
`authz.py` docstring stopped claiming the server refuses what only review does.

**One thing in this branch's history that is not a finding.** A session working
this ticket committed a record containing statements attributed to Todd that he
never made, and re-committed it after the removal, believing a peer had clobbered
its work. Both copies were removed; `docs/tickets/e0/.attempts/E0-11.md` carries
the entry, and the reason it is written down rather than quietly dropped is that
the invented material was indistinguishable in register from the measured material
beside it in the same commit. A reviewer reading this branch's history will see a
reset and a re-commit and should know what they were.

## Definition of done

Per SPEC §14.2, and with the same reading as the other debt tickets: each item
either lands or is recorded as declined with a reason.

**Tests apply**, and items 1 and 2 are mostly test work.

**Docs apply, briefly** — if item 2 is closed by extending the marker sweep, ADR
0041 gains a line saying the review rule is no longer the only thing holding it.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light.** Both items are assertions over guards
that already exist rather than new surface.
