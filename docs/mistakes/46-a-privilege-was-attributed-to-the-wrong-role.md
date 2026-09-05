# 46. A privilege was attributed to the wrong role, and the ticket was built on it

## What happened

E3-06's work order settled the sweep's shape and, among its traps, stated a fact
about the database:

> `user.lms_user_id` is the AGS `userId` (pulse_app holds column-scoped SELECT on
> exactly id / lti_platform_id / lms_user_id).

The parenthesis is false of `pulse_app` and true of a different role. What
`pulse_app` holds on `user` is `SELECT (id)` and `INSERT (id, lti_platform_id,
lms_user_id)`; the triple `SELECT (id, lti_platform_id, lms_user_id)` belongs to
`pulse_resolve_definer`, the NOLOGIN owner of ADR 0094's point resolvers, and it
is spelled exactly that way in `RESOLVE_DEFINER_COLUMN_PRIVILEGES` in
`tests/integration/test_identity_grants.py`. Two roles, one triple, and the prose
named the wrong one.

The whole of E3-06 was built on it. An AGS Score names its student by the LTI
`sub`, which lives only in `user.lms_user_id`, so the read is not an incidental
detail of the design — it is the step without which nothing can be posted at all.

## The root cause

The claim was **transcribed rather than executed**. The triple is real, it is
written down in the file the work order's author was reading, and it sits three
lines under a comment about `pulse_app`. Nothing in the build ran `SELECT
lms_user_id FROM "user"` as `pulse_app` until the code that needed it existed.

The second half of the root cause is why it survived so long: the ticket's own
suite could not see it. Twenty-four of E3-06's twenty-five tests drive the service
with a session bound to the **migrating** engine, which holds every privilege, and
they all passed. The only test that drives the sweep the way production does — one
that calls the Celery task, which opens its own `SessionLocal` on the application
role — failed, and it failed on a savepoint's broad `except` that reported
`InsufficientPrivilege` without saying which statement.

E1-10's round-3 security review had revoked that column from `pulse_app` on
purpose: "a connection able to read it can enumerate every subject that ever
launched and join a response back to the person who gave it." A second guard says
the same thing on the application side —
`tests/unit/test_no_service_reads_an_identity_table_directly.py`, which is
`invariant`-marked and refuses any module under `app/services/` that turns `User`
into rows. Both fired. Neither was consulted before the decision was settled.

## The consequence

E3-06 shipped as a design that is fully demonstrated and cannot run in
production: the sweep computes, compares and composes correctly, and the step that
turns a `user` row into an AGS `userId` raises on the worker's own connection. The
repair is not a line of code — it is a `SECURITY DEFINER` resolver, a migration, a
sixth entry in an inventory the file itself calls "a new door into identity that
some later ticket opened without arguing for it", and a decision about whether the
reverse direction gives back what the revocation bought. That is an owner's
decision arriving at the end of a build rather than at the start of one.

## The rule

**A settled decision that rests on a privilege is a claim about a role, and the
role is the half that gets mistyped.** Before a work order fixes a design on "this
connection can read X", execute the read as that role and paste the result — the
grant files and the privilege inventories name several roles, and a triple of
column names is identical whichever one holds it.

**And a suite that drives a service through the migrating engine has not tested
the privilege at all.** Where a ticket's behaviour depends on a grant, at least
one test has to reach the code through the connection production uses; the
grant-shaped failure is invisible to every other test in the module and will pass
review as a green suite.
