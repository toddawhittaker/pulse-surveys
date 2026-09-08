# E4-18 — The instructor's section list

**ID:** E4-18
**Branch:** `e4/instructor-sections`
**Depends on:** E4-07
**Lane:** heavy — `backend/app/api/` is a named row.
**Security-relevant:** a new instructor-facing read route. It enumerates
sections for the session's own person and must never name anybody else's.

## Context

E4-11's build stopped on a contract gap, found 2026-09-07 and resolved by
the owner's ruling the same day. The report page must call E4-07's routes,
and every one of them takes a `section_id` — but nothing the client holds
supplies one. The launch redirect carries only the role and the session,
the session claims carry keys and never sections, and the API lists
nothing. The student surface answers the same question with a parameterless
read (`GET /student/survey` returns the reader's own enrollments); the
instructor surface had no equal.

The ruled fix is the student pattern: one more route in
`backend/app/api/instructor.py` answering the session's own taught
sections. The rejected alternative — the launch door forwarding its
context's section — is recorded in this ticket's ADR.

## The public interface

`GET /instructor/sections`, behind the same `require_instructor` session
dependency the two existing routes carry, answering:

```json
{
  "sections": [
    {
      "section_id": "8f1c2c1e-…-a uuid",
      "code": "R3WW",
      "course_label": "MATH 140 E1FF — College Algebra, Fall 2026"
    }
  ]
}
```

- The entries are exactly the sections the session's person holds the
  teaching-instructor grant over — the same teaching set the report routes
  serve, derived through the same authorization chokepoint, so the list and
  the report can never disagree about what she may read.
- `course_label` is the governed full label, the same form the report's
  `section.course_label` and the student survey serve (FIX-01 item 2).
- Order is deterministic: by `course_label`, then `code`, then
  `section_id`, so the page renders stably and nothing about submission or
  creation order leaks into it.
- A person teaching nothing answers `{"sections": []}` with a 200 — and so
  does a session naming no person. An empty teaching set is an ordinary
  state (the student analog: an empty list is between terms), and there is
  no parameter in this request to refuse, so this route has no 404.
- A session that is not an instructor's gets the same 401 the two existing
  routes answer.
- `Cache-Control: no-store`, like every answer this module serves.

## Scope

- The route, in `app.api.instructor` (§13's instructor-facing API module;
  the module docstring's "two routes and no others" sentence is corrected
  in the same change).
- The response schema beside the report's, in `app.schemas.report`.
- The service read in `app.services.reporting`, composing the label with
  that module's existing composer. The section-set query lives in
  `app.services.authz`, because `public.assignment_scope` is read through
  that module and nowhere else.
- The scope assertion, `invariant`-marked and in the isolated §4.1 pass:
  the list never contains a section without the requester's own grant.
- The ADR for the section-discovery decision, including the rejected
  redirect alternative.

## Acceptance criteria

1. An instructor with two seeded sections reads exactly those two entries,
   each carrying the id, the code and the governed label; a third section
   taught by somebody else is planted and absent. The absence assertion is
   `invariant`-marked and runs in the isolated §4.1 pass.
2. A student session and a request with no session get the module's 401,
   and the body names no section.
3. A person with no teaching grant, and a session naming no person, each
   get 200 and an empty list.
4. The order is the declared one, proven against sections seeded in a
   different order.
5. Both existing routes answer exactly as before; the route-inventory
   sweep covers all three routes, and the dependency sweep proves the new
   route carries the session dependency.
6. The answer carries `Cache-Control: no-store`.
7. The ADR is in the pull request, and the records this change falsifies
   (the module docstring, E4-11's dependency rows) are corrected in the
   same pull request.

## Known traps

- `tests/fixtures/report_api.py::instructor_route_objects` **fails the
  report suites unless the module has exactly two GET routes.** The count
  and its message move to three on the tests-first side of the wall
  (MISTAKES entry 22: the repair lives in `tests/`, where the implementer
  cannot reach).
- `public.assignment_scope` may be read only through `app.services.authz`
  (`tests/unit/test_the_org_views_are_read_only_through_the_grant.py`). A
  join written in the reporting service is the widening that sweep exists
  to refuse.
- The org-views prose sweep (MISTAKES entry 43) reads non-docstring
  strings: a `Field(description=…)` naming `section` after a comma or
  `from` can red it. Reword the prose; never widen the guard.
- `role_assignment` has no validity window (E0-09), so the list is every
  section she holds the grant over, past terms included — the same set the
  report routes already serve. Narrowing the list here and not there would
  make the two disagree; neither narrows in this ticket.
- The refusal-pair reasoning of the two existing routes does not transfer:
  there is no id in this request to enumerate with. Do not invent a 404.

## Out of scope

- Any frontend — E4-11 consumes this route.
- Leadership's read of anybody's section list — E9.
- Pagination or term filtering: the set is one instructor's own sections.
