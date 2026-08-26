# 0090 — A sanctioned writer passes the chokepoint by being in a catalog

## Context

[ADR 0045](0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)
gave `guard_write` a rule — refuse a write to `course`, `section`, `enrollment`,
`user`, or an `INSTRUCTOR` `role_assignment` row — and then named two write paths
that have to be allowed through it anyway: "the launch path that creates a `user`
row, and E1's roster sync for the other three, as sanctioned writers". It could
not say what that meant operationally, and said so: "`guard_write(table='course')`
refuses unconditionally, with no argument, context or flag that makes it return."
[ADR 0069](0069-three-rules-held-by-a-docstring-are-swept-out-of-the-source.md)
carried the same gap with a "done when", on Todd's decision of 2026-08-19: write
it down and leave the mechanism to E1, which arrives with a real writer to design
against rather than a guess about one.

E1-10 is that ticket. `app.services.provisioning` writes `course`, `section` and
`user` from a verified launch, so the question is no longer hypothetical: either
that module calls the guard and something about the call distinguishes it from an
unsanctioned caller, or ADR 0045 has to record why a sanctioned writer does not
call the chokepoint at all.

SPEC §8 decides the rule ("LMS-owned data is never hand-edited in Pulse") and
decides nothing about the mechanism, and a reasonable engineer would choose
differently between at least four of them — so this record exists.

## Decision

**A sanctioned writer still calls `guard_write`, and passes a `WriteSanction`
that a catalog in the same module has to back.** Three pieces, all in
`app/services/authz.py`:

- `SANCTIONED_WRITERS: Mapping[str, frozenset[str]]` — the catalog, today exactly
  `{"launch_provisioning": {"course", "section", "user"}}`.
- `WriteSanction(writer, tables)` — a **frozen** dataclass, obtained from
  `sanction_for(writer)`, which raises `UnknownSanctionedWriterError` for a name
  the catalog does not hold.
- `guard_write(*, table, assignment_role=None, sanction=None)` — with no
  sanction, exactly today's behaviour, unconditional refusal on the guarded set.
  With one, the write passes only when `sanction.writer` is in the catalog **and**
  `table` is in that writer's set.

**The catalog is the authority and the sanction is only a claim of identity.**
`guard_write` never reads `sanction.tables`. A caller can build a `WriteSanction`
naming any writer and any tables it likes — the constructor is public — and both
forgeries are refused: an uncatalogued writer because the catalog has no entry for
it, and a widened table set because the catalog's entry is what is consulted. That
is the whole difference between a sanction and a `please=True` flag.

**The teaching-instructor row is outside the mechanism.** §2.1's fifth owned item
is a purview grant rather than a stale attribute, and no catalogued writer is
granted `role_assignment`, so a sanction never reaches that branch. E1-11 adds the
`INSTRUCTOR` write it needs by adding an entry, deliberately, in the pull request
that needs it.

**The inventory lives in a test file, not in the guarded module**
(`docs/MISTAKES.md` entry 35). `tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py`
compares `SANCTIONED_WRITERS` against a hand-written copy as an equality, in the
shape `RUNTIME_BASE_TABLE_PRIVILEGES` uses for grants, so widening what may write
LMS-owned data is a visible diff in a test rather than a line added to a module
nobody re-reads.

**ADR 0069's rule is unchanged and gains no exclusion list.** "The module names
the guard" is exactly as true of the launch writer as of anything else — it calls
`guard_write` before each table's write, with a sanction the catalog grants — so
E0-35's sweep keeps its subject and finally has one.

## Alternatives rejected

**An exclusion list in the sweep** — name `provisioning.py` as allowed to write
without naming the guard. It moves the decision into a test, leaves the
application with a write path that passes no chokepoint at all, and the next
module added to the list is a one-line diff nobody reads as an authorization
change. ADR 0069 rejected it in advance.

**A context flag** — `guard_write(table="course", sanctioned=True)`. Every caller
can set it, which makes it the bypass ADR 0045 names, and the pinning test above
would go on passing because no catalog ever changes.

**Trusting the `WriteSanction` the caller holds** — read `sanction.tables` rather
than the catalog. Nearer the mark, and defeated by the same forgery: a caller
constructs the sanction it wants. It also makes the value the authority, so a
sanction that leaks out of one module authorizes whoever holds it.

**A call-stack or module-name check** — decide from the caller's `__module__`.
Implicit, unreadable at the call site, and it makes a refactor that moves a
function an authorization change with nothing recording it.

**Doing it in the database instead** — refuse `pulse_app` the writes outright.
That is ADR 0045's own preferred instrument and it is not available: the launch
path and E1-11's sync are the same connection, so a grant cannot tell them apart.
E1-10 spends the narrowest grant its writer needs
(`launch_provisioning_grants_v001.sql`) *as well as* this mechanism. The two are
different instruments — the guard knows which writer is asking and the database
does not; the database holds for callers that never ask the guard — and neither
replaces the other.

## Consequences

**ADR 0069's open half is closed, and ADR 0045's is closed in the same shape.**
Both records get an amendment paragraph pointing here. The sweep's rule is
restated in its own module docstring, in the same pull request, as that "done
when" requires.

**A sanction is process-wide, not request-scoped.** Nothing here knows who is
launching or which request is running; a sanction says which *code* is writing.
That is the grain ADR 0045 chose for the guard and this follows it, but it means
a module holding a sanction can write those tables from any code path in it. The
E0-35 sweep's own stated limit — the grain is the module, not the path — is
unchanged and is the same limit.

**One entry is a small enough catalog that the test is the record.** With two or
three entries this stays readable; past that, the equality test's failure message
is the thing to invest in, not the mechanism.

**E1-11 follows this rather than redesigning it.** If the roster sync finds the
mechanism wrong, that is a dispute and an amendment here — not a second mechanism
beside it, which would leave two answers to "how does a writer pass the guard"
and no way to tell which one a module used.
