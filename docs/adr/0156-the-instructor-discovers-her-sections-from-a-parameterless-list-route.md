# 0156 — The instructor discovers her sections from a parameterless list route

## Context

E4-07 shipped the instructor's Monday report as two reads: the report for one
section and one course week, and the list of course weeks a reader may page to.
Every one of them takes a section key in the path.

Nothing a client holds supplies one. The launch redirect carries the role and the
session and no section; the session claims carry keys — the subject, the launch's
`user` row, the person — and never a section; and until now the API listed
nothing. E4-11's build stopped on this in September 2026: the report page can
render a report for a section, and has no way to name a section.

The student surface has never had the problem. `GET /student/survey` is a
parameterless read that answers the reader's own enrollments, so a student page
starts from what the session already is rather than from something a client had to
be told. The instructor surface had no equal.

The owner's ruling of 2026-09-07 settles the shape — the student pattern, one more
route in `app.api.instructor` — and what stays open is why that shape rather than
the two alternatives below, both of which were live when the gap was found.

## Decision

`GET /instructor/sections` answers the sections the session's person holds the
teaching-instructor grant over, one entry each carrying the section key, the LMS
section code and FIX-01 item 2's governed course label, ordered by the label, then
the code, then the key.

Four things follow from it, and each is a choice rather than a detail:

- **The scope is derived through `app.services.authz`**, by a set reader beside
  the single-section predicate the report already asks. The list and the report
  therefore answer one rule asked two ways and cannot disagree about what a reader
  may see. `public.assignment_scope` is read through that module and nowhere else
  (E0-41), so a join in the reporting service was never available anyway; what the
  decision adds is that the *list* is a grant question rather than a catalog query
  with a filter on it.
- **It takes no parameter, so it has no refusal pair.** The two routes above
  answer a section outside the reader's teaching set and a section that does not
  exist with one identical 404, because a reader who can tell those apart can
  enumerate the institution's sections one key at a time. Nothing here can be asked
  about somebody else's section, so that reasoning does not transfer and no 404 is
  invented by analogy.
- **An empty list is an ordinary answer with a 200** — for a person who teaches
  nothing, and for a session naming nobody. The student analog is a reader between
  terms. A refusal would turn a new instructor's first Monday into an error page.
- **The label is composed once**, by the report's own composer, so the section a
  reader picks from the list is named exactly as the report she opens names it.

## Alternatives rejected

**The launch door forwards its context's section.** A launch already resolves a
section, and the redirect could carry it. It answers a smaller question than the
one asked: it names the one course she launched from, not the sections she
teaches, so a page built on it cannot offer the second one at all — and an
instructor teaching four sections would have to launch four times to see four
reports. It also gives nothing at the web door, where there is no LTI context to
forward and where E1's own work put an equal front door on purpose. And it widens
what the doors do: the launch path is the most security-sensitive surface in the
product, and adding a payload to its redirect for a page's convenience is a change
to that surface rather than to a read route.

**A client-side workaround.** The page could hold section keys itself — in local
storage, or in a configured list. There is no data to hold: nothing has ever told
the client what a section key is, so the first read would still have to come from
somewhere. This is not a cheaper version of the decision; it is the decision with
the source of truth moved into a browser.

**A leadership-shaped route that takes a person.** Answering "which sections does
*this person* teach" would serve E9's drill-down as well. It is refused because it
turns a read of the reader's own scope into a read across people, which is exactly
the widening SPEC §4.1's chokepoint rule exists to prevent, and it would ship that
widening before the purview computation that governs it.

## Consequences

E4-11 depends on this route: the report page reads the list first, and every later
call is a key the list handed it.

E9's leadership read attaches where ADR 0155 already says it does —
`app.services.reporting._readable_section` — and not here. This route answers the
session's own person and has no place to put somebody else's, which keeps the
leadership widening a single decision in a single function.

The list carries every section she holds the grant over, past terms included,
because `role_assignment` has no validity window (E0-09). That is the same set the
report routes already serve, and narrowing it here alone would let a reader page to
a section the report then refuses. When end-dating arrives, the set reader gains it
with its three siblings, which are named together in `app.services.authz`.

`app.api.instructor` is now three routes rather than two, and the sweeps that walk
the module by dependency walk all three. The two that describe a request's section
parameter shape only the two that have one.
