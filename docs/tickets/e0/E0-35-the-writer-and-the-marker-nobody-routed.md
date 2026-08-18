# E0-35 — The writer nobody routed, and the column nobody marked

**ID:** E0-35
**Branch:** `e0/writer-and-marker-sweeps`
**Depends on:** E0-07, E0-11

## Context

Three findings from three tickets, batched because they are three instances of
one sentence: **a rule that holds today, stated in a docstring, with nothing that
would notice when a new piece of code stops holding it.** They were tracked as
[E0-21](E0-21-review-debt.md) item 1, [E0-24](E0-24-review-debt-from-e0-07-and-e0-08.md)
item 2, and [E0-27](E0-27-review-debt-from-e0-11.md) item 1.

The three rules:

1. **An LMS-owned column carries an `lms_` prefix** ([ADR 0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)).
   Walking `Base.metadata` asserts that every column E0-05 named is prefixed and
   that no Pulse-owned table carries the prefix. It cannot assert the direction
   that matters — that a *new* LMS-owned column has its marker — because once the
   prefix is missing, nothing distinguishes the column from a Pulse-owned one.
   `course.canvas_id` sails through every test in the suite.
2. **`length_weeks`, `start_date`, `end_date` and `modality` are set by exactly
   one path.** Two tests catch a second writer that *disagrees* with
   `apply_section_code`. One that *agrees* is invisible. E0-08's security review
   grepped and found no bypass, so it is true — and it is convention, not
   enforcement, which [ADR 0021](../../adr/0021-a-sections-derived-calendar-has-one-writer.md)
   records deliberately.
3. **Every application write path calls `guard_write` before it writes.** Nothing
   calls it. That is correct in E0 — no write path exists — and it means the rule
   rests on a sentence in `services/authz.py`'s docstring. All eight tests call
   `guard_write` directly, so they assert it answers correctly when asked; none
   can notice a write path that never asks.

**Why this is one ticket and not three.** The read side already has the shape all
three want: `tests/unit/test_no_service_reads_an_identity_table_directly.py`
fails when a service module reaches an identity table, whether or not anyone
remembered a rule. Each item here is that sweep pointed at a different subject.
Build the mechanism once.

**E1 is the deadline.** E1's roster sync is the first code that writes `course`,
`section`, `enrollment` and the `INSTRUCTOR` `role_assignment` row — every
relation the guard names, all four in one module — and it is also the only code
that sees both which field came from the platform and which column it went into.
If it lands without calling `guard_write`, nothing fails, and ADR 0045's rule
becomes a description of something the codebase used to intend.

Read first: [ADR 0045](../../adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md),
ADR 0014, ADR 0021, SPEC §2.1, and `docs/MISTAKES.md` entries 2 and 3.

## Decide first: sweep the source, or refuse the write

This is the decision the three source tickets each declined to make, and making
it once is most of the reason to batch them.

**A static sweep over the source.** Ask whether a module that writes those
relations also names the guard. Cheap, matches the read-side sweep already in the
tree, no runtime cost, and it can be written today against modules that do not
exist yet. It is syntactic: it sees the shape of a call, never where the value
came from, so a write reached through a helper or an ORM cascade is invisible.
[ADR 0062](../../adr/0062-a-request-is-parsed-once-at-the-edge.md) states that
limit for the mock-idp gate and the same three sentences apply here.

**A session-level hook that refuses an unguarded flush.** Catches the call a
sweep would miss, including the indirect ones. Costs a hook on every write in the
system from now on, and the failure mode when it is wrong is a refused legitimate
write in production rather than a red test.

E0-27 says plainly that neither is obviously right. **The choice affects item 3
directly and items 1 and 2 by analogy**, so decide it once and apply it
consistently rather than picking per item.

Note that items 1 and 3 are the two halves of one seam and closing either does
not close the other: item 1 is a column nobody marked, item 3 is a writer nobody
routed. E0-21 recorded a third option for item 1 — assert the prefixed set
matches an explicit list — which **does not work and is not on the table**:
adding `course.canvas_id` leaves the prefixed set unchanged.

## Out of scope

- **Constraining `jwks_url`.** E0-24 item 1, which wants E1's launch flow and is
  carried out of this epic; see the README's deferral table.
- **Re-deriving a section when its term's start-letter map is edited.** E0-24
  item 3, owned by E2/E11.
- The transitive purview union, which is E9's.

## Acceptance criteria

- [ ] Adding an LMS-owned column with no `lms_` prefix fails something. The test
      demonstrates it by adding one and watching it go red, not by asserting
      against a list of columns that already exist.
- [ ] A module that writes `course`, `section`, `enrollment` or an `INSTRUCTOR`
      `role_assignment` row without calling `guard_write` fails something. Same
      rule: demonstrate by adding such a writer, not by asserting against the
      modules that exist today.
- [ ] A second assignment site for any of the four derived section columns fails
      something, **or** ADR 0021 is amended to say plainly that this is
      unenforced and why that is acceptable. Do not leave E0-07's "exactly one
      path" wording standing with nothing behind it.
- [ ] The sweep-versus-hook decision is recorded where the rule lives, with what
      the chosen one cannot see.
- [ ] All three verified by mutation, and the mutation set includes the nearest
      passing case rather than only the obvious failure.

## Definition of done

**Tests apply**, and they are most of the ticket.

**Docs apply.** ADR 0014 gains a line if item 1 is closed at table grain — the
marker stops being the enforcement mechanism and becomes documentation, which
retires one of the two reasons that ADR gives for a name prefix over an `info={}`
dict. ADR 0021 gains a line either way. If the session hook wins, that is its own
ADR.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies.** Every item is a guard on a write path over LMS-owned
data, which is the surface SPEC §2.1's "read-only in Pulse" protects.
