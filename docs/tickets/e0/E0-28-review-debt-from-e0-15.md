# E0-28 — Review debt from E0-15 (Batch E: mock LMS conformance)

**ID:** E0-28
**Branch:** `e0/review-debt-e0-15`
**Depends on:** E0-15

## Status — what is left here

**Eight of the ten items are one batch in `mock-lms/app/`**, and every one was
re-verified against the epic branch on 2026-08-21 — file and line references
below are current. PR #31's review comment carries a reproduction for each.

| Item | Now |
|---|---|
| 1, 2, 3, 4, 5, 7, 9, 10 | **This ticket** — build them together, in the order below |
| 6 — the client-credentials grant is deferred | **Decided 2026-08-18: not built here.** Deliverable: its four moving parts written into `docs/tickets/e1/carried-from-e0.md` (create the file; E0-18 writes into it too). |
| 8 — `make docker-build` waits on fewer services than CI | **Closed** — the Makefile now waits on `api worker beat mock-lms mock-idp` |

## Context

What E0-15's review found and could not close in place. What its own pull
request did close is indexed at the bottom, so this file is a record of the
whole round rather than a list of what was skipped.

**Nothing here blocks anything in E0, and every item is the same kind of
thing: the mock platform is more forgiving, or more uniform, than the
platforms it stands in for.** SPEC §7.3 names NRPS paging and AGS score
semantics as the two places platforms deviate, and this mock exists to make a
tool meet those deviations in a test rather than in a deployment. Where the
mock is smoother than reality, a later epic writes code that passes here and
fails against Canvas, Moodle, D2L or Blackboard — and passes *silently*, which
is what makes these a ticket rather than a comment.

**E1 and E3 are the deadlines.** Items 1, 2 and 6 mislead E1's roster sync;
items 3, 4, 5 and 10 mislead E3's grade passback. Neither epic can discover
any of them from its own tests, because its own tests run against this mock.
This batch can land any time after E0-18; nothing in it and nothing in E0-18
touches the other.

Read first: SPEC §7.3 and §9.2, [ADR
0047](../../adr/0047-the-posted-score-readback-is-a-mock-only-route.md), [ADR
0048](../../adr/0048-enrollment-windows-ride-on-a-namespaced-nrps-extension.md),
and PR #31's review comment.

## Build order, and why it is this order

Three clusters, one commit or few per cluster, tests failing first throughout:

1. **Item 1 alone, first** — it amends an E0-15 acceptance criterion in the
   same change, and the seed edit it makes ripples into the fixtures every
   other item's tests read. Land the seed's new shape before building tests on
   top of it.
2. **The paging cluster: items 4, 5, 10, then 2.** All four live in
   `paging.py`, `nrps.py`, `ags.py` and the `memberships`/`list_line_items`/
   `read_results` handlers in `main.py`, and 4 explicitly copies the NRPS
   paging model. Doing them together means one coherent change to how
   containers page instead of four patches to the same functions.
3. **The URL cluster: items 3 and 9, then the item-7 decision.** Both are
   about what a line-item or result URL may look like; 7 is a one-paragraph
   ruling on a route the URL work already touches.

Then the item-6 paragraph into `docs/tickets/e1/carried-from-e0.md`, last, so
the file states what the finished batch actually leaves for E1.

Verification discipline (this repo has learned it the hard way — see
`docs/MISTAKES.md`): every behavioural item below is verified by mutation with
the *near-miss*, not only the obvious break; commit before running the
battery; confirm each mutation landed before believing a green suite.

## Scope

### 1. Every seeded member carries an enrollment window, so no fixture exercises a platform that supplies none

**The gap.** E0-15 puts enrollment windows on a namespaced NRPS member
extension (`mock-lms/app/nrps.py::ENROLLMENT_EXTENSION`, ADR 0048), and its
criteria require `start` on **every** member. That ruling is not reopened
here. What follows from it: no seeded roster shows E1 the case it will
actually meet — no mainstream platform supplies enrollment dates through NRPS
at all. E1 writes `member[EXTENSION]["start"]`, passes every test here, and
against a real platform either raises `KeyError` or falls through to a
denominator of zero — which SPEC §3.4 makes a wrong participation score, not a
crash.

**Done when** one seeded member somewhere carries no enrollment extension at
all, in a section away from the add-and-drop assertions, and a test asserts
the mock serves that member without one. This contradicts E0-15's
"every member" criterion as written, so that criterion moves in the same pull
request — and while moving it, settle whether the *fallback* is E1's to choose
(as the titleless-course fallback was) or belongs in the spec. If it belongs
in the spec, that is a question for Todd, raised in the PR, not answered by
this ticket.

### 2. The roster ignores NRPS's own query parameters

`memberships` (`main.py:350`) accepts its own `page` and nothing else: `role`,
`limit` and `rlid` are not even parameters, so a request filtered to
`#Instructor` returns every member of the page. Bounded harm — a tool must
filter client-side anyway, because a platform may ignore these — so what is
lost is an untested code path rather than a wrong roster. **Done when** the
three parameters either work or are refused, rather than accepted by FastAPI's
default tolerance and disregarded. Refusing is the smaller change and matches
the strictness argument in E0-30 item 4; implementing `role` at least is more
realistic. Either is acceptable; say which in the PR.

### 3. The line item id cannot carry a query string

Every line item id this platform mints is a bare path, so a tool can build its
score endpoint as `id + "/scores"` and be right forever here. Moodle's line
item ids carry a query — `.../lineitems/3/lineitem?type_id=1` — and the
`/scores` segment goes *before* it. **Done when** at least one line item id
carries a query parameter and a test asserts that a client assembling the
scores URL handles it, so E3 cannot ship the naive concatenation with a green
suite. The mock's own routes must accept the querified id they mint.

### 4. The results container does not page and ignores `limit`

`read_results` (`main.py:456`) says so in its own docstring, citing this item.
A real platform pages results; a 200-student section on a platform paging at
50 reads back 50 results and 150 apparent non-submitters. **Done when** the
results container pages with a `Link` header and honours `limit`, and a test
walks it the way the roster walk does. `nrps.py` and `paging.py` are the model
to copy — same helper, same header discipline.

### 5. A single-page roster sends no `Link` header at all

`paging.py::link_header` (line 79) returns `None` when a container fits on one
page. Right about `next` — advertising one that does not exist is the defect
the five-member section exists to catch — and under-realistic about the rest:
real platforms still send `first`, `last` and `current` on a one-page
container. A client written against "read `last` to learn the extent" finds
nothing here. **Done when** a single-page container carries the relations that
do apply, with `next` still absent.

### 6. The client-credentials grant is deferred, and the deferral changes four things at once

E0-15 leaves NRPS and AGS unauthenticated, deliberately; `app-security`
reviewed the deferral and agrees it is safe for this mock as deployed. The
problem is not risk — it is that **E1 cannot build a conformant client against
the current surface at all**, so it would build an unauthenticated one and
rewrite it. `pylti1p3`'s `ServiceConnector` issues no NRPS or AGS request
without an `auth_token_url` and a tool-signed `client_assertion`. Today
discovery advertises `scopes_supported: ["openid"]` and no `token_endpoint`,
`/registration` publishes no `auth_token_url`, and `LtiPlatform` has no column
for one or for the tool's key pair.

Four things therefore move together whenever this lands: the token endpoint in
discovery, the AGS and NRPS scopes in `scopes_supported`, `auth_token_url` in
`/registration` and in `lti_platform`, and somewhere for the platform to fetch
the tool's JWKS. **Done when** that paragraph — the four parts, and why they
move together — is in `docs/tickets/e1/carried-from-e0.md`, so whoever builds
the roster sync meets it before writing the client rather than after. Create
the file if E0-18 has not already; it is the one home for everything E0
decided E1 must know (E0-18's identity-merge assertion and E0-35's
sanctioned-writer question belong there too — add pointers, do not rewrite
their content).

### 7. `read_line_item` is a route no ticket asked for

`GET <lineitem>` (`main.py:428`) is served and nothing drives it. AGS 2.0
defines it, so it is not a conformance defect — it is scope that arrived
without a criterion. **Done when** it has a test naming what it is for, or it
is gone. Recommendation: keep it and give it the querified-id test from item 3
to carry — E3's line-item reconciliation will want the route, and deleting a
conformant route to re-add it one epic later is churn.

### 8. `make docker-build` waits on fewer services than CI does

**Closed.** The Makefile's health wait now matches CI's list. Kept as a row so
the item numbering the code cites stays stable.

### 9. A `sub` containing a slash makes a result URL the platform cannot route

`ags.py::result_url` (line 645) percent-encodes the user identifier with
`safe=''`, so a score posted for a `userId` of `a/b` answers 200 with a
`resultUrl` of `…/results/a%2Fb` — and a `GET` of that URL is Starlette's own
404, because ASGI hands the router the decoded path. The `Result` in the
container advertises the same dead `id`. Rare while every `sub` is a UUID, and
precisely the hazard the per-user results route exists to close: a URL the
platform composes and does not serve. **Done when** either the route matches
an identifier containing a slash (a `:path` converter, plus the test that a
posted-then-fetched slashed `userId` round-trips), or such a `userId` is
refused at the score post with a message saying why — the second narrows AGS
and needs recording as a narrowing if chosen.

### 10. The line-item cap is a number no test names

`ags.py::MAX_LINE_ITEM_LIMIT` is 100; `main.py:415` clamps `limit` to it,
which is right — but nothing asserts the clamp's *value*. Removing
`min(limit, MAX_LINE_ITEM_LIMIT)` leaves every test green (proven by mutation
during E0-15's third fix round), so a tool asking for a million line items is
served all of them in one page here, where Canvas would cap and page. Debt
rather than defect because no seeded context holds more than a handful of line
items — invisible today, visible exactly when E3 syncs an institution. **Done
when** a container holding more line items than the cap serves the cap and
advertises the rest — which needs a fixture context minted with `cap + 1`
items, built for this test rather than added to the seed.

## Out of scope

- Reopening the "every member carries a window" ruling itself, or the "every
  seeded course carries a title" ruling. Item 1 adds a case beside the first;
  it does not withdraw it.
- Building E1's roster sync or E3's passback. Every item here is about what
  the *mock* shows them.
- Building any part of the client-credentials grant (item 6 is a paragraph in
  a file, nothing more).

## Acceptance criteria

- [ ] One seeded member carries no enrollment extension, with a test, and
      E0-15's "every member" criterion is amended in the same pull request.
- [ ] NRPS's `role`, `limit` and `rlid` either work or are refused; the PR
      says which and why.
- [ ] At least one line item id carries a query string; a test proves a scores
      URL built from it is correct and that the mock serves the id it minted.
- [ ] The results container pages with a `Link` header and honours `limit`,
      and a walk-the-pages test loses no result at a page boundary.
- [ ] A single-page container carries `first`, `last` and `current`, and no
      `next`.
- [ ] `docs/tickets/e1/carried-from-e0.md` exists and carries item 6's four
      moving parts.
- [ ] `read_line_item` has a criterion or is gone.
- [ ] A `userId` containing a slash either routes or is refused, and no result
      URL the platform hands out 404s.
- [ ] A container over the line-item cap serves the cap and advertises the
      rest.
- [ ] Every behavioural item verified by mutation, near-miss included, with
      the battery run after the last content commit.

## Definition of done

**Tests apply.** Every item is a test that fails first; the reproductions are
in PR #31's review comment. **Docs apply, briefly:** `README.md`'s description
of the two services changes wherever this changes them. **AI evals and
accessibility do not apply.** **Security review applies but is light**, on the
same terms as E0-15: the mock is not a product surface. Item 6 is the one to
look at, and `app-security` has already reviewed the deferral once.

## What E0-15's own pull request closed

Indexed so this file is a record of the round rather than of its remainder.
Four HIGH, five MED and one LOW were fixed in place — the count is spelled out
because an index the next ticket trusts is worth more than a tidy sentence:

- A score carrying `scoreGiven` with no `scoreMaximum` was accepted (HIGH).
- A stale `timestamp` silently regressed a grade where AGS requires 409, and a
  `timestamp` that was not a timestamp was accepted (HIGH).
- The line-item container was unpaged and ignored every filter parameter
  (HIGH).
- The late-add test asserted only that two enrollment moments differed, so an
  *early* add passed it (HIGH).
- `activityProgress` and `gradingProgress` were checked for presence, not
  value (MED).
- The `resultUrl` the platform handed back 404'd (MED).
- A posted `scoreMaximum` differing from the line item's was silently dropped
  (MED).
- `"end": null` present-rather-than-omitted was unasserted, so a window
  emitted with no `end` key at all passed (MED).
- The roster walk's "no member is dropped" rested on a lower bound that both
  launch users satisfied, so a slice losing one member per page boundary
  passed (MED).
- "Two start letters" was wrong in four records; the seed uses three (LOW).

A second review pass over those fixes found one HIGH, seven MED and seven LOW,
and the same rule was applied again: the HIGH and the easy MED were fixed, and
what remains is in the scope above. Two of that pass's findings were about
this file and the pull request body rather than about the code, and both are
corrected rather than carried forward.
