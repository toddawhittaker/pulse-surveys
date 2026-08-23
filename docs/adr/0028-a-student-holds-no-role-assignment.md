# 0028 — A student holds no role assignment

**Status:** Accepted — **context amended 2026-08-23**; the decision is unchanged
and the spec now agrees with it
**Date:** 2026-08-16
**Tickets:** E0-09

## Context

> **Amended 2026-08-23.** The paragraphs below describe a spec this record
> disagreed with. **It no longer reads that way.** On 2026-08-23 Todd decided
> the disagreement by editing the spec to agree with this record:
> §2.1's "People are not roles" sentence now reads "A person acting in any role
> but Student holds one or more *role assignments*", and a note under the table
> states that students hold no role assignment, that the Student row describes
> what a student can see rather than an assignment record, and that a student's
> access is resolved from enrollment. So the contradiction raised at the top of
> PR #68 — an ADR deciding one thing while the spec still read the other way,
> which `CLAUDE.md` says an ADR alone may never settle — is resolved, and the
> resolution is in the spec rather than here. The reading below is kept because
> the choice this record made is only intelligible against the sentence that
> forced it, and because the spec's new note states the rule without the
> reasoning: what stays this record's own is the enum, the constraint that makes
> a student row unwritable, and the alternatives rejected below.

[SPEC §2.1](../SPEC.md)'s table has nine rows, and Student is one of them: entry
point "LTI launch", scope attachment "Own responses; aggregate results +
instructor response for own sections". So the spec names Student as a role, and
the natural reading of "a person holds one or more role assignments" is that a
student holds one too.

But the same table gives every other role a **node** to attach to, and gives the
student a *sentence* instead. There is no containment level whose rows are "own
responses", and §2.1's scope grain — the rule this ticket enforces in the
database — has no answer for a student. E0-09's scope enumerates the grains it
means ("a chair scoped to a department, a dean to a college, a lead to a course,
Care and Admin to the institution") and does not mention students.

A student's access is also derived from something the graph does not hold. §4
keys responses to the LMS user ID from the launch, and §3.1 shows a student
exactly one open survey per section they are enrolled in. Enrollment is E0-08's
table, LMS-owned and synced hourly, and it already answers "which sections may
this person act in".

## Decision

`AssignmentRole` enumerates eight roles and **not** `STUDENT`. A student holds no
`role_assignment` row, and one cannot be written: the enum has no label for it,
and the scope grain constraint's `CASE` has no arm that would admit it.

A student's access is resolved from `enrollment` — the row that says this user
was in this section during this window — rather than from the supervision graph.

## Alternatives rejected

**A `STUDENT` label with `section_id` as its grain**, mirroring the instructor.
The tidiest-looking option: nine roles for nine table rows. Rejected because it
duplicates `enrollment` and immediately disagrees with it. E3's participation
figures are enrollment-*windowed* — a student who drops in week 3 and re-adds in
week 8 has two rows that do not touch ([ADR
0023](0023-overlapping-enrollments-are-refused-by-an-exclusion-constraint.md)) —
and a role assignment carries no window. Two answers to "may this person answer
this week's survey", one of them stale, is the shape §4's confidentiality rules
can least afford, and the stale one would be the Pulse-owned copy that no roster
sync corrects.

**A `STUDENT` label with `institution_id` as its grain**, meaning "a student
somewhere". Rejected because it grants nothing and states nothing: every check
would still go to `enrollment`, and the row would exist only so that the enum
matches the table in the spec. A row that no query reads is a row that drifts.

**Making `scope_node` nullable for students.** Rejected because it unpicks the
constraint that is this ticket's point. `num_nonnulls(...) = 1` is what stops an
assignment naming two nodes or none; an exemption for one role turns "exactly
one" into "exactly one, unless", and the unless is the row nobody checks.

## Consequences

**The supervision graph contains only people with oversight of somebody else's
data**, which makes it exactly the set §2.1 computes purview over. Nothing in the
graph can widen a student's visibility, because students are not in it — a
structural version of §4.1 invariant 6.

**E0-11's authorization resolver must ask two questions, not one**: what
assignments does this actor hold, and what is this actor enrolled in. That is the
real cost, and it is where a later reader is most likely to want this record.
`services/authz.py` is the one chokepoint where both are asked.

**A student who is also staff is unaffected.** They hold assignments for their
staff hats and enrollments for their student sections, and the two do not
interact — which is the same separation §2.1 relies on for two-hat leadership
and, in the other direction, for the Care staffer who also teaches.

**If a later epic needs a student-scoped grant** — a student representative on a
committee, say — this is a migration adding an enum label and a `CASE` arm, and
this record is what it should argue against. It is not a decision that has to
hold forever; it is a decision that the spec's ninth table row does not by itself
justify a ninth enum label.
