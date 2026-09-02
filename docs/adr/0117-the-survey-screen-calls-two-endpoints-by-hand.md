# 0117 — The survey screen calls its two endpoints by hand

**Status:** Accepted
**Date:** 2026-09-02
**Tickets:** E2-10

## Context

SPEC §13's repository tree draws `frontend/src/api/` as "generated client from
backend OpenAPI + TanStack Query hooks". That is a sentence in a directory
listing rather than a requirement in a numbered section, and E1-04 read it that
way and left the question open in as many words: `frontend/src/main.tsx` says
"there is no data fetching, no client generated from the OpenAPI schema and no
query cache: E1 has nothing to fetch, and the ticket says so. What goes here when
there is something is **E2's decision to make against a real screen**."

E2-10 is that screen, and it is the first thing in this repository that fetches
anything. It makes two calls: `GET /student/survey` and
`POST /student/submissions`.

The spec's tree names one answer, the ticket that wrote the tree's frontend
deferred the choice to this ticket, and a reasonable engineer would take either —
so this is a record rather than a link to §13.

## Decision

**Two `fetch` calls, written by hand, in `frontend/src/api/student.ts`.** No
OpenAPI generator, no generated client checked in or built, and no query cache.
The module holds the wire types transcribed from `app.schemas.student` and
`app.schemas.survey`, the two calls, and the translation of this route's status
table into four named outcomes. The screen holds its own loading state in
`useState`.

**The types are the wire's spelling**, snake case and all, and the two decimal
columns are typed `string` because pydantic writes a decimal to JSON as a string.
A shape of the frontend's own choosing here would be a translation layer nobody
asked for between two contracts that already agree.

**The answer is cast, not re-validated field by field, with one bounded check**:
`sections` must be an array, because that is the member every render walks. What
a shape mismatch needs is to be loud, not to be parsed twice.

## Alternatives rejected

**Generate a client from `/openapi.json`.** The option §13's tree names. It buys
type agreement between the two sides that today is a transcription somebody has
to keep right, and for a wide API surface it is clearly correct. Rejected for
this one: it is a generator, its output, a build step and a check that the output
is current, added for **two calls** — and the generated client would still need
this module's outcome mapping, because the interesting part of this route is not
the happy path but which of `app.copy`'s sentences a status carries. The day a
third epic's screens make it twenty calls, the argument reverses; what changes
then is this file, not the screens.

**Add TanStack Query.** A cache, retries, request deduplication and invalidation
for one screen that reads once on mount and posts once on a button. It is a
dependency in a bundle with a stated budget and a product reason for it — "a slow
first paint is a response-rate problem" — bought for behaviour this screen does
not have. The router is already TanStack's, which makes it the tempting choice
and does not make it a smaller one.

**Fetch in the route's loader** rather than in the component. TanStack Router can
load before render, which removes the loading state. Rejected because a loader
that throws on a refusal turns a 401 into an error boundary, and the honest
answer to a request with no session is a calm screen rather than an error page —
so the branch has to exist somewhere, and it reads better beside the states it is
one of.

**Re-derive the contract at the seam with a schema library** (zod or similar).
The safe-looking option. It is a third dependency and a second statement of a
shape the server already publishes, and the failure it prevents — the server
answering something else — is one this application cannot recover from anyway.
The bounded check on `sections` is what turns that failure into a message rather
than a blank screen.

## Consequences

**The wire types are a transcription and nothing checks them.** If
`app.schemas.student` grows a member or renames one, this file goes stale
silently: `tsc` sees a type that says what this file says. What catches it is the
end-to-end spec, which drives the real endpoints in a real browser, and the fact
that a renamed member arrives `undefined` and renders as an empty field rather
than as a crash. That is the cost of this decision and it is the reason to
revisit it when the surface grows.

**There is no request cache, so a navigation back to this screen refetches.**
Correct for a survey — the window may have closed, or another tab may have
submitted — and worth knowing before somebody adds a cache for a different
screen and expects this one to use it.

**A second screen that needs the same read will copy this module's shape.** The
right response then is to look at the count of calls again rather than to grow a
fourth copy of a fetch helper; this record is what that decision argues with.

**The bundle stays free of a data layer.** The gzipped initial payload after this
ticket is 93,572 bytes against a 163,840-byte budget, and none of it is a client
or a cache. That headroom was reserved for SPEC §7.6's component inventory, not
for infrastructure.
