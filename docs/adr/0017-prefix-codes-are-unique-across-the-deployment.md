# 0017 — Prefix codes are unique across the deployment, not per institution

**Status:** Accepted
**Date:** 2026-08-14
**Tickets:** E0-05

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
serves one institution. `app.config.Settings` already carries
`INSTITUTION_TIMEZONE` as a single deployment-level value, which is the same
assumption stated elsewhere.

## Alternatives rejected

**Scope to the department — `UniqueConstraint("department_id", "code")`.** The
obvious parallel to `college.name` and `department.name`. Rejected because it
permits the thing the containment model exists to forbid: `BIOL` under two
departments makes `BIOL 215` ambiguous, and a course number is how every other
part of the product names a course. Scoping to the parent is right when the
parent disambiguates the child; here it does not, because nothing downstream
carries the department alongside the prefix.

**Scope to the institution — `UniqueConstraint("institution_id", "code")`.**
The literal reading of the original docstring, and the correct rule if a
deployment ever serves more than one institution. Rejected because `prefix` has
no `institution_id` and adding one is the second ancestor reference that
`backend/app/models/org.py`'s own module docstring argues against: a course
reaches a department by exactly one path, and a prefix should reach an
institution the same way. Denormalising the institution onto `prefix` to support
a case no deployment has would buy a hypothetical at the cost of the invariant.

## Consequences

**A second institution row breaks prefix insertion, and does so unhelpfully.**
The schema permits more than one `institution` — `college` is unique per
`institution_id` — so nothing stops a second one being seeded. Its `BIOL` is
then refused by `uq_prefix_code` with an error naming a constraint and no
institution. This is the accepted cost, and it is recorded here rather than
discovered: multi-institution is not a supported configuration, and the day it
becomes one, this constraint and `INSTITUTION_TIMEZONE` both have to move, which
is the honest signal that the change is larger than a schema edit.

**The asymmetry with `college.name` and `department.name` is deliberate.** A
reader who notices it and "fixes" it by scoping to the department reintroduces
the ambiguous-course-number case. The docstring at the constraint says why, so
that the reasoning is where the temptation is.
