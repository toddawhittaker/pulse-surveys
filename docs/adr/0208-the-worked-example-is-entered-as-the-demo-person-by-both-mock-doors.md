# 0208 — The worked example is entered as the demo person, by both mock doors

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-13](../tickets/e9/E9-13-e9-exit.md)

## Context

SPEC §14.3's E9 exit asks that the assistant-dean worked example of
[SPEC §2.1](../SPEC.md) resolve the same from either door. The worked example is
the demo institution's assistant dean in `scripts/seed.py`: two chairs report to
their assignment, and they lead PSYC 110. Neither development door reached that
person. The mock provider's `assistant-dean` subject was linked to a separate
mock-world person with no supervision edges, and the mock platform had no
assistant dean at all. [ADR 0097](0097-the-identity-a-verified-subject-resolves-to.md)
made the mock world's people new persons, never a demo person re-linked, and
pinned the mock platform's launchable subjects as an inventory of two.

## Decision

- The mock platform gains `mock-lms-user-assistant-dean`, enrolled in
  `MATH-140-E1FF` alone with the learner claim, as the dean is.
- The demo assistant dean's `user` is that subject on the mock platform's
  registration, instead of a user on the fictional platform (a person has one
  `user`, ADR 0024). The provider's `mock-idp-user-assistant-dean` subject is
  linked to the same person. The mock-world copy is no longer seeded.
- A database seeded earlier is moved over: the person is re-pointed at the new
  `user` and the linkage moved, so no second assistant dean is written.
- The launchable inventory in `tests/integration/test_demo_seed_script.py`
  names the third subject.

## Alternatives rejected

- **A mock-world copy with the same shape.** The worked example is the
  assistant dean's edges, and a chair's assignment reports to one assignment
  only, so a copy cannot hold them.
- **Driving the worked example from the integration suite only.** The exit
  asks for both doors on a running stack.

## Consequences

- Anyone who can reach the mock containers on a development box can enter as
  the demo assistant dean and read their purview (Mathematics, Biology and PSYC
  110). It is ADR 0097's trade made once more; the data is fictional and the
  seed runs in development only (ADR 0063).
- `MATH-140-E1FF`'s mock roster holds nine members, still one full page and a
  short one. The new subject's enrolment is what gives the launch door a
  student view to switch to.
