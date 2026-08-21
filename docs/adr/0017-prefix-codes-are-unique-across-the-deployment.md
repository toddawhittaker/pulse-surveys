# 0017 — Prefix codes are unique across the deployment, not per institution

**Status:** Accepted — amended 2026-08-18, and again 2026-08-20
**Date:** 2026-08-14
**Tickets:** E0-05, E0-22

> **Amendment, 2026-08-18.** The assumption this record rests on became a
> rule. SPEC §8 now states that a deployment serves exactly one institution
> and requires a constraint permitting at most one `institution` row. The
> decision below is unchanged and its reasoning still holds — what changes
> is that the alternative rejected as "wider than E0-05" was the right one
> and has now been taken at the level that could take it.
>
> **Amendment, 2026-08-20.** The constraint is built. It is a unique index on
> a constant expression, `uq_institution_one_row`, and
> [ADR 0072](0072-one-institution-is-a-unique-index-on-a-constant.md) records
> why that shape and what `alembic check` does with it. The assumption below
> is no longer latent, and the consequence that depended on it is retired
> where it stands.

## Context

[SPEC §2.1](../SPEC.md) puts `prefix` under `department` and says a department
groups one or more prefixes — Math may hold MATH, STAT and MIS. It does not say
what makes a prefix code unique, and [§8](../SPEC.md) restates the containment
rule without settling it either.

E0-05 has to choose, because the constraint goes in the first migration and
changing a uniqueness rule after rows exist is a data migration rather than an
edit. Every sibling column in the same module is scoped to its parent —
`college.name` is unique per `institution_id`, `department.name` per
`college_id` — so a reader reasonably expects `prefix.code` to be scoped too,
and two independent reviewers read the original docstring as claiming it was.

## Decision

`prefix.code` is unique across the whole table. One `BIOL` exists in a
deployment, owned by one department.

The docstring says so plainly and names the assumption it rests on: a deployment
serves one institution. That assumption was **latent, not enforced** when this
was written, and this record did not pretend otherwise; the 2026-08-20 amendment
above is where it stopped being latent. `app.config.Settings` carrying a single
`INSTITUTION_TIMEZONE` was consistent with it and was never evidence for it — a
configuration default is not a statement that only one `institution` row may
exist, which is why it took a constraint to make one.

## Alternatives rejected

**Scope to the department — `UniqueConstraint("department_id", "code")`.** The
obvious parallel to `college.name` and `department.name`. Rejected because it
permits the thing the containment model exists to forbid: `BIOL` under two
departments makes `BIOL 215` ambiguous, and a course number is how every other
part of the product names a course. Scoping to the parent is right when the
parent disambiguates the child; here it does not, because nothing downstream
carries the department alongside the prefix.

**Enforce the single-institution assumption instead of leaving it latent** — a
constraint permitting at most one `institution` row, at which point global
uniqueness and institution-scoped uniqueness are the same rule and the
incoherence below disappears. This is the cheapest of the three and it was not
considered when the decision was first written, which is the gap this paragraph
exists to close. It was not taken **here** because it decides something wider
than E0-05: whether the product is single-tenant by construction is a statement
about what Pulse *is*, the spec did not make it, and a schema ticket should not
make it by side effect.

**It has since been taken, and built.** SPEC §8 says a deployment serves exactly
one institution and requires the constraint, decided 2026-08-18; E0-22 built it
as `uq_institution_one_row` on 2026-08-20
([ADR 0072](0072-one-institution-is-a-unique-index-on-a-constant.md)). So this is
no longer an alternative rejected — it is the answer, arrived at from the
document that governs rather than from a schema ticket, which is the process
working rather than the record being wrong.

**Scope to the institution — `UniqueConstraint("institution_id", "code")`.**
The literal reading of the original docstring, and the correct rule if a
deployment ever serves more than one institution. Rejected because `prefix` has
no `institution_id` and adding one is the second ancestor reference that
`backend/app/models/org.py`'s own module docstring argues against: a course
reaches a department by exactly one path, and a prefix should reach an
institution the same way. Denormalising the institution onto `prefix` to support
a case no deployment has would buy a hypothetical at the cost of the invariant.

## Consequences

**A second institution row broke prefix insertion, and did so unhelpfully.**
The schema permitted more than one `institution`, so nothing stopped a second
one being seeded, and its `BIOL` was refused by `uq_prefix_code` with an error
naming a constraint and no institution. That was the accepted cost of leaving
the assumption latent. **This consequence is retired as of 2026-08-20**: the
second `institution` row is now refused at the row that is actually wrong, by
`uq_institution_one_row`, and nothing reaches a prefix code to be confused by.

Multi-institution remains an unsupported configuration, and the day it becomes
one, this constraint, `uq_institution_one_row` and `INSTITUTION_TIMEZONE` all
have to move — which is the honest signal that the change is larger than a
schema edit.

**The asymmetry with `college.name` and `department.name` is deliberate.** A
reader who notices it and "fixes" it by scoping to the department reintroduces
the ambiguous-course-number case. The docstring at the constraint says why, so
that the reasoning is where the temptation is.
