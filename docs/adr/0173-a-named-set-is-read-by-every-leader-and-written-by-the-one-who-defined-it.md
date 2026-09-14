# 0173 — A named set is read by every leader and written only by the one who defined it

## Context

SPEC §5.1 gives leadership the power to define named comparison sets:

> The default comparison set is the same Lead Faculty's courses filtered to
> matching length+level; leadership can define named sets, and set-definition UI
> makes invalid combinations impossible rather than erroring on them.

It says who defines a set. It does not say who may *change* one, and E5-06 is
the ticket that has to answer that, because it is the first surface on which two
leaders can reach each other's rows. §2.1 describes five leadership roles that
differ in purview — the part of the institution each one supervises — and E5's
breakdown puts the computation of purview over the supervision graph in E9,
where the reads that need it live.

So E5-06 could scope its writes three ways: by the supervision graph (a leader
may change any set whose member courses fall inside their purview), by creator
(a leader may change the sets they defined), or not at all (any leadership
session may change any set). The first needs machinery that does not exist and
that a later epic owns; the third makes the institution's benchmark definitions
editable by anybody who holds any leadership assignment.

The same question has a second half that is easy to miss: whether *reading* a
set is scoped the same way as writing one.

Where the write and scope code lives is the third question here, and it is one
decision with the other two: SPEC §13 says to use an existing module and add one
only when nothing fits.

## Decision

**Writes are scoped by the set's creator.** A `PUT` or a `DELETE` on a set is
allowed when `comparison_set.created_by_person_id` is the `person` the session
was resolved to at the door, and refused with 403 otherwise. The creator column
is E5-01's and already exists (ADR 0164); nothing new is stored to hold this.

**Reads are not scoped at all — every leadership session reads every set in the
institution.** The list, the read of one set and the preview answer for any set,
whoever defined it. §5.1's set-definition surface is one institution-wide list:
two leaders who each saw half of it would define the same cohort twice under two
names, and the second one would not know the first existed. What a set discloses
is its name, its declared length and level, a list of course keys and two
counts — no student, no subject, no figure. The creator key resolves to nobody
through the application connection in any case, which holds `SELECT (id)` on
`public."user"` and no read of a person's name at all.

**`editable` on the list says which is which**, so the management UI offers an
edit control exactly where one will be accepted rather than discovering the
refusal by pressing it.

**The write and scope code is a new module, `app/services/comparison_sets.py`.**
Neither existing candidate fits. `app/services/benchmarks.py` is the read and
figure module and its own docstring says nothing in it writes; `app/services/
authz.py` is SPEC §13's single authorization chokepoint, and putting a write
path inside it would make the module where permission is decided also the module
where rows change.

## Alternatives rejected

**Purview scoping now — a leader may change any set whose courses fall inside
the part of the institution they supervise.** It is the answer §2.1 points at
and it is almost certainly where this ends up. It is rejected here for cost and
for ownership: the supervision-graph computation is E9's, building a second one
in E5 would leave two answers to "what does this leader supervise" for the two
to disagree about, and the disagreement would be a widening nobody could see. A
set is not an object a purview can be read off in any case — a set naming courses
from three departments has no single supervisor — so purview scoping needs a
rule about *partial* coverage that nothing in the spec settles yet.

**No scoping — any leadership session writes any set.** Cheapest, and it makes
the whole ticket's second acceptance criterion vacuous. A named set is the
cohort every instructor in a college is measured against; a benchmark that
changes without anybody deciding it is what ADR 0164 calls the serious outcome
on this data, and "leadership is a small, trusted group" is an argument that
holds until the day it does not and leaves no record of who changed what.

**Scoping the reads by creator too.** Symmetrical and simpler to explain, and
wrong for the reason above: it turns one institution-wide list into a private
list per leader, which is the opposite of what a shared definition surface is
for. It would also make the preview useless as a check on duplication.

**Putting the writes in `benchmarks.py` anyway**, on the grounds that everything
about a comparison set belongs together. Rejected because that module's whole
guarantee is that it computes figures and seals them, and a reader asking "can
this module change what a benchmark is computed over" should be able to answer
no by reading its first paragraph.

## Consequences

A leader who defines a set and leaves the institution leaves a set nobody can
edit or delete — the `RESTRICT` on the creator key means the `person` row cannot
be deleted either, so the set stays and stays uneditable. That is a real gap and
it is E9's to close, in the change that computes purview; until then the answer
is that somebody else defines a replacement set and the old one is left.

`editable` is a second statement of the same rule, on the wire, and the two can
drift: a summary that said `true` for a set the service will refuse hands the UI
a control that 403s. They are computed from one comparison in one module for
that reason, and the API suite asserts both directions of each.

E9 will widen this rather than replace it: a purview-scoped write is a second
way to be entitled to a set, not a different answer to who defined it. The
creator column stays either way, because it is also the record of who defined a
set — ADR 0174 records that it is the *only* such record this ticket writes.
