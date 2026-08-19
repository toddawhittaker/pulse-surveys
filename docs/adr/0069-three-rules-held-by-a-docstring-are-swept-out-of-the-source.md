# 0069 — Three rules held by a docstring are swept out of the source, not hooked into the session

**Status:** Accepted
**Date:** 2026-08-18
**Tickets:** E0-35

## Context

Three review rounds left three findings that are the same sentence: **a rule that
holds today, stated in a docstring, with nothing that would notice when a new
piece of code stops holding it.** They were
[E0-21](../tickets/e0/E0-21-review-debt.md) item 1,
[E0-24](../tickets/e0/E0-24-review-debt-from-e0-07-and-e0-08.md) item 2 and
[E0-27](../tickets/e0/E0-27-review-debt-from-e0-11.md) item 1.

- **An LMS-owned column carries an `lms_` prefix** ([ADR 0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md)).
  Walking `Base.metadata` cannot assert the direction that matters, because once
  the prefix is missing nothing distinguishes the column from a Pulse-owned one.
  `course.canvas_id` sails through every test in the suite.
- **A section's derived calendar has exactly one writer** ([ADR 0021](0021-a-sections-derived-calendar-has-one-writer.md)).
  Two tests catch a second writer that *disagrees* with `apply_section_code`. One
  that agrees is invisible.
- **Every application write path calls `guard_write` before it writes** ([ADR 0045](0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)).
  Nothing calls it. All eight tests call it directly, so they assert it answers
  correctly when asked; none can notice a write path that never asks.

`docs/MISTAKES.md` entry 2 is that shape, and it is the entry with the highest
catch count in the file. SPEC §2.1 and §2.2 say what the rules are and say
nothing about what holds them up, and a reasonable engineer would weigh a runtime
guard against a static check differently, so the choice is this record's.

Each source ticket declined to make it, which is most of the reason E0-35 batched
them: the mechanism is one decision applied three times, not three decisions.

## Decision

**Todd settled it on 2026-08-18: build a static sweep over the source.** One
mechanism, in the shape `tests/unit/test_no_service_reads_an_identity_table_directly.py`
already uses on the read side, pointed at three subjects:

| Rule | Sweep | The question it asks |
|---|---|---|
| 1 | `test_no_lms_owned_table_carries_an_unmarked_column.py` | on a table in the guarded set, is every column marked, structural, unwritable, or recorded? |
| 2 | `test_a_sections_derived_calendar_has_one_assignment_site.py` | is every assignment of the four derived columns inside `backend/app/services/section_codes.py`? |
| 3 | `test_every_writer_of_an_lms_owned_relation_names_the_guard.py` | does a module that writes an LMS-owned relation call `guard_write` somewhere in the same module? |

Three properties of that mechanism are part of the decision rather than of the
implementation.

**The guarded set is discovered and floored, not listed.** Rules 1 and 3 take
`authz.LMS_OWNED_TABLES` unioned with a floor of `course`, `section`,
`enrollment` and `user`. Reading the guard's own set means the sweep grows when
the guard grows — and E0-35's own criterion, written by hand, names three tables
and was already one short. Reading the floor means the sweep cannot be shrunk by
an edit to the module it guards, which is `docs/MISTAKES.md` entry 35.

**The floor has two authorities and they are not the same one.** `course`,
`section` and `enrollment` come from SPEC §2.1's ownership sentence. `user`
comes from **ADR 0045**, which put it in the guard's set because
`user.lms_user_id` is the `sub` claim verbatim and §4 keys every response to it;
§2.1 does not name it. The constant is `GUARDED_TABLE_FLOOR` rather than
`SPEC_…` for exactly that reason — a name claiming the spec's authority over a
table the spec does not name is the false record this project keeps catching.

**The floor alone was not enough, and the first version of this record said it
was.** An earlier draft of this paragraph claimed the floor stopped the guarded
set being shrunk by an edit to the module under guard. That was true of the
spec's three and was stated as though it covered all four: `user` was in the
swept set *only* through `authz.LMS_OWNED_TABLES`, so deleting it there left the
union answering three tables and both sweeps quietly narrowed. The claim was
never executed against the case it described, which is `docs/MISTAKES.md` entry
9, and an independent security review measured it on PR #44. What holds it up
now is a direct assertion —
`test_the_guard_names_every_table_in_the_floor_this_sweep_may_not_fall_below` —
that `LMS_OWNED_TABLES` is a superset of the floor, so a removed table fails
loudly and names itself instead of shrinking the sweep. The guard may still
**grow** freely; only shrinking below the floor is refused. Editing the floor to
match a narrowed guard turns the assertion back into what it replaced, and the
failure message says so.

**The subject is the syntax tree, not the file text.** A correct module is very
likely to *say* "this never inserts into `course`" in a docstring, and a text
search would turn that sentence into a failure and teach the next person to
delete the comment. Docstrings are subtracted by name.

**Each sweep carries a positive-control battery it has to find.** All three have
an empty subject set on today's tree — E0 ships no application write path at all
— so a sweep that reported nothing would have reported nothing about nothing. Each
write shape is proven detectable against a sample carried beside it, and the
near-miss beside that sample is proven to be allowed.

`INSTRUCTOR` is matched in both spellings, the string `"INSTRUCTOR"` and
`AssignmentRole.INSTRUCTOR`, over the enclosing statement rather than the call,
because the model and the role routinely sit in different calls of one statement.

## Alternatives rejected

**A session-level hook that refuses an unguarded flush.** The genuine competitor,
and it has the advantage the sweep cannot buy: it catches the **indirect** writes
— a write through a helper in another module, an ORM cascade off a relationship,
a relation named by a variable — because it sees the flush rather than the
source. E0-27 said plainly that neither option is obviously right.

It lost on cost and on precedent. It costs a hook on every write in the system
from now on, and its failure mode when it is wrong is **a refused legitimate write
in production**, where the sweep's failure mode when it is wrong is a red test on
a branch. The sweep also matches the read-side check already in the tree, so it
adds a subject to a mechanism this codebase already maintains rather than a
second mechanism to keep in step with the first.

**Asserting that the set of `lms_`-prefixed columns matches an explicit list**
(rule 1 only). Recorded because E0-21 offered it and it must not be re-proposed:
it does not work. Adding `course.canvas_id` leaves the prefixed set unchanged, so
the assertion stays green while the gap opens.

**Amending ADR 0021 to say the rule is unenforced** (rule 2 only). E0-35 offered
this as the alternative to building the check, and it is the honest answer if the
sweep cannot see the sanctioned writer. The sweep does see it, so the branch does
not apply — but the control that proves it does is load-bearing, and a red control
there is this decision to re-make rather than a line to adjust.

**Nothing but the docstring and review.** What the three source tickets each left
in place. `docs/MISTAKES.md` entry 2 is the measurement of how well that works.

## Consequences

**Three limits travel with every one of these sweeps, and an ADR claiming a gate
covers more than it does is worse than one admitting it covers nothing.**

- **It is syntactic, not dataflow.** It sees the shape of a call or an
  assignment, never where the value came from. `setattr(row, name, value)` with a
  computed name, a bulk update built from a dict assembled at run time, or a
  helper taking the column name as an argument are all invisible.
- **It reads the source rather than the running application.** A write through a
  helper in another module, an ORM cascade, a mapper event, or a relation named
  by a variable is invisible to it.
- **The grain for rule 3 is "the module names the guard", not "the guard ran
  before this write on this path".** A module that guards one function and writes
  in another passes. Proving the second thing is what the rejected hook was for.

**This does not close the seam it guards.** It is a tripwire on the obvious way
to write the wrong thing, and it is worth having for that: the obvious way is how
the failure actually arrives. The proof-shaped instrument is a grant — refusing
the application role `INSERT` and `UPDATE` on these tables — and ADR 0045 already
records why that is not available until E1, when the roster sync arrives on the
same connection as the launch path and a sanctioned writer can be separated from
an unsanctioned one.

**Rule 1 changes what ADR 0014's marker is for.** Asking the question per *table*
instead of per column reaches the direction the marker could not assert, and the
prefix stops being the enforcement mechanism and becomes documentation. ADR 0014
carries that line. The trade is that the sweep speaks only about the tables in the
guarded set: an LMS-owned column landing on a table nobody has put there is
outside it entirely, exactly as it is outside ADR 0045's chokepoint.

**Rule 2's control is the honest limit.** If the sweep ever cannot find
`apply_section_code`, then it cannot see the way this codebase sets those four
columns, and its silence about every other module is worth nothing. The failure
message says so.

**A recorded exception is a claim nobody re-checks.** Rule 1's
`PULSE_OWNED_COLUMNS` entries each assert that Pulse owns a value on a table the
LMS owns, taken from the record cited beside it. Entries are required to name
real columns, so an exception cannot outlive its column, but nothing checks that
the reason is still true.

**One thing this does not answer, and E1 has to.** ADR 0045 names the LTI launch
path that creates a `user` row, and E1's roster sync that writes the other three,
as **sanctioned** writers. Nothing records how a sanctioned writer satisfies
"calls `guard_write`", because `guard_write(table="course")` refuses
unconditionally — there is no argument, no context and no flag that makes it
return. Today the rule is satisfiable only because nothing writes at all: no
module under `backend/app/` calls `guard_write`, so no module is asked.

**Todd's decision, 2026-08-19: write it down and leave the mechanism to E1**,
which arrives with a real writer to design against rather than a guess about one.
No sanctioning mechanism is invented here, no exclusion list is added to the
sweep, and the rule is not softened. **Done when** E1's first sanctioned writer
lands: it either calls `guard_write` and something about that call distinguishes
it from an unsanctioned one, or ADR 0045 records why a sanctioned writer does not
call the chokepoint at all — and whichever it is, the sweep's rule is restated to
match, in the same pull request as the writer.
