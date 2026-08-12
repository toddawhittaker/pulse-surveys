# 0003 — Deferred authorization seams fail closed by raising

**Status:** Accepted
**Date:** 2026-08-12
**Tickets:** E0-11

## Context

E0-11 builds the authorization chokepoint in `services/authz.py`, but the
transitive purview union over the assignment DAG — the computation
[SPEC §2.1](../SPEC.md) defines and the assistant-dean case exercises — is
deferred to E9 per [§14.3](../SPEC.md). Something has to occupy that seam for
the length of E0 through E8.

The spec defines what purview *is*. It does not say what an unimplemented
purview computation should return, and the plausible answers differ sharply in
how they fail.

## Decision

The deferred union raises `NotImplementedError`, named and documented, pointing
at E9. It does not return an empty set, a partial result, or a permissive
default.

This generalizes: **any deferred authorization seam fails closed by raising**,
not by returning a value that a caller could mistake for an answer.

## Alternatives rejected

**Return an empty set.** The dangerous one, and the reason this record exists.
An empty purview is a legitimate state — a lead faculty member with no reports
has one — so nothing about it looks wrong. Callers would work, tests would pass,
and a dean would silently see nothing. The likely repair is worse than the bug:
someone diagnoses "the dean sees no data" as a scoping problem and widens access
somewhere else to compensate, which is how a confidentiality invariant gets
broken by a well-intentioned fix.

**Return the own grant only, as a partial union.** Rejected for the same reason
in a subtler form. A dean would see their own college but not the departments
reached through a supervised assistant dean. Under-reporting reads as a data
problem — a missing sync, an unmapped course — rather than as a missing feature,
so it invites investigation of the wrong thing.

**A feature flag defaulting to off.** Rejected as the empty-set behavior with
extra machinery, plus a flag that someone will eventually flip in an environment
where the code behind it still does not exist.

**Implement the union now, in E0.** Rejected because it contradicts the epic
decomposition for a real reason, not a bureaucratic one: the union needs
Hypothesis property tests over generated supervision graphs (§9.1) to be
trustworthy, and that is a substantial slice of E9. A union without those tests
would be worse than no union, because it would look finished.

**Return the full institution.** Never. Widening a user's visibility is the one
direction §4.1 forbids absolutely, and a fail-open default in the authorization
layer is the highest-severity defect this product can have.

## Consequences

- **Any code path that reaches the union crashes loudly** in development and in
  CI rather than returning a wrong answer quietly. That is the intent, and it is
  the whole benefit.
- **E0-18's smoke tests must not traverse the union.** Leadership landing views
  are empty by design in E0. If a smoke test does hit the raise, that is a signal
  the test asserts more than E0 delivers — fix the test, do not soften the seam.
- **E9 must add user-facing handling when it lands the real computation.** No
  production deployment exists before then, so an unhandled raise costs nothing
  today; a raise reaching a user later would be a 500. This is a check for E9,
  recorded here so it is not discovered in production.
- The stub is a place a future contributor may be tempted to "fix" by returning
  something. The module docstring required by E0-11 has to say why it raises, or
  this decision has a short life.
