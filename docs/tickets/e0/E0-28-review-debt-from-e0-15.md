# E0-28 — Review debt from E0-15

**ID:** E0-28
**Branch:** `e0/review-debt-e0-15`
**Depends on:** E0-15

## Context

What E0-15's review found and could not close in place, collected the way E0-21
collects E0-05's, E0-24 collects E0-07's and E0-08's, E0-25 collects E0-09's,
E0-12's and E0-14's, E0-26 collects E0-10's and E0-27 collects E0-11's. What
E0-15's own pull request closed is indexed at the bottom, so this file is a
record of the whole round rather than a list of what was skipped.

**Nothing here blocks anything in E0, and every item is the same kind of thing:
the mock platform is more forgiving, or more uniform, than the platforms it
stands in for.** SPEC §7.3 names NRPS paging and AGS score semantics as the two
places platforms deviate, and the reason this mock exists is to make a tool meet
those deviations in a test rather than in a deployment. Where the mock is
smoother than reality, a later epic writes code that passes here and fails
against Canvas, Moodle, D2L or Blackboard — and passes *silently*, which is the
part that makes these worth a ticket rather than a comment.

**E1 and E3 are the deadlines.** Items 1, 2 and 6 mislead E1's roster sync;
items 3, 4 and 5 mislead E3's grade passback. Neither epic can discover any of
them from its own tests, because its own tests will run against this mock.

Read first: SPEC §7.3 and §9.2, [ADR
0047](../../adr/0047-the-posted-score-readback-is-a-mock-only-route.md), [ADR
0048](../../adr/0048-enrollment-windows-ride-on-a-namespaced-nrps-extension.md),
and PR #31's review comment, which carries the reproduction for every item here.

## Scope

### 1. Every seeded member carries an enrollment window, so no fixture exercises a platform that supplies none

**The gap.** E0-15 puts enrollment windows on a namespaced NRPS member extension
(ADR 0048), and its criteria require `start` on **every** member. That is a
deliberate ruling and it is not being reopened here. What follows from it is that
no seeded roster shows E1 the case it will actually meet: no mainstream platform
supplies enrollment dates through NRPS at all.

So E1 writes `member[EXTENSION]["start"]`, passes every test here, and against a
real platform either raises `KeyError` or falls through to a denominator of zero
— which SPEC §3.4 makes a participation score, not an error, so the failure is a
wrong number rather than a crash.

**Done when** one seeded member somewhere carries no enrollment extension at all,
in a section away from the add-and-drop assertions, and a test asserts that the
mock serves that member without one. This contradicts E0-15's "every member"
criterion as written, so that criterion moves in the same pull request — and the
question worth settling while moving it is whether the *fallback* is E1's to
choose, as the titleless-course fallback was, or whether it belongs in the spec.

This is the exact shape of the empty-title fixture that E0-15 withdrew, one
epic earlier and with the same consequence, which is why it is first.

### 2. The roster ignores NRPS's own query parameters

`memberships` accepts its own `page` and ignores `role`, `limit` and `rlid`. A
request filtered to `#Instructor` returns every member of the page.

The harm is bounded — a tool has to filter client-side anyway, because a platform
may ignore these — so what is lost is an untested code path rather than a wrong
roster. **Done when** the three parameters either work or are refused, rather
than accepted and disregarded.

### 3. The line item id cannot carry a query string

Every line item id this platform mints is a bare path, so a tool can build its
score endpoint as `id + "/scores"` and be right forever here. Moodle's line item
ids carry a query — `.../lineitems/3/lineitem?type_id=1` — and the `/scores`
segment goes *before* it. SPEC §7.3 names AGS score semantics as a deviation this
mock exists to expose, and this is the one it does not.

**Done when** at least one line item id carries a query parameter and a test
asserts that a client assembling the scores URL handles it, so that E3 cannot
ship the naive concatenation with a green suite.

### 4. The results container does not page and ignores `limit`

E0-15 closed the per-user result route and the `user_id` filter. What is left is
paging: a real platform pages results, and a 200-student section on a platform
paging at 50 reads back 50 results and 150 apparent non-submitters. The NRPS side
of the same pull request pages properly, and `nrps.py` is the model to copy.

**Done when** the results container pages with a `Link` header and honours
`limit`, and a test walks it the way the roster walk does.

### 5. A single-page roster sends no `Link` header at all

`link_header` returns `None` when a roster fits on one page. That is right about
`next` — advertising one where no next page exists is the defect the seed's
five-member section exists to catch — and under-realistic about the rest: real
platforms still send `first`, `last` and `current` on a one-page container. A
client written against "read `last` to learn the extent" finds nothing here.

**Done when** a single-page container carries the relations that do apply, with
`next` still absent.

### 6. The client-credentials grant is deferred, and the deferral changes four things at once

E0-15 leaves NRPS and AGS unauthenticated, deliberately and with the reasons in
its out-of-scope list. `app-security` reviewed that and agrees it is safe for
this mock as deployed. This item is not about the risk; it is about the fact that
**E1 cannot build a conformant client against the current surface at all**, and
so will build an unauthenticated one and rewrite it.

`pylti1p3`'s `ServiceConnector` issues no NRPS or AGS request without an
`auth_token_url` and a tool-signed `client_assertion`. Today discovery advertises
`scopes_supported: ["openid"]` and no `token_endpoint`, `/registration` publishes
no `auth_token_url`, and `LtiPlatform` has no column for one or for the tool's
key pair. Four things therefore move together whenever this lands: the token
endpoint in discovery, the AGS and NRPS scopes in `scopes_supported`,
`auth_token_url` in `/registration` and in `lti_platform`, and somewhere for the
platform to fetch the tool's JWKS.

**Done when** either the grant is built, or E1's ticket carries this paragraph so
that whoever builds the sync meets it before writing the client rather than
after. It is listed here rather than in E1 because E1's ticket does not exist yet.

### 7. `read_line_item` is a route no ticket asked for

`GET <lineitem>` is served and nothing drives it. AGS 2.0 does define it, so this
is not a conformance defect — it is scope that arrived without a criterion, and
the choice is to give it one or to remove it. **Done when** either is true.

### 8. `make docker-build` waits on fewer services than CI does

The Makefile's health wait covers `api worker beat`; `.github/workflows/ci.yml`
waits on `api worker beat mock-lms mock-idp`. Pre-existing, and not E0-15's
defect — raised there because it changes what "`make ci` is green" is evidence
for. **This belongs to [E0-20](E0-20-gate-fidelity.md)**, whose subject is
exactly a gate reporting green over something it does not look at, and it is
recorded here only so the finding is not lost between two tickets.

### 9. A `sub` containing a slash makes a result URL the platform cannot route

Found by the second review pass. `result_url` percent-encodes the user
identifier with `safe=''`, so a score posted for a `userId` of `a/b` answers 200
with a `resultUrl` of `…/results/a%2Fb` — and a `GET` of that URL is Starlette's
own 404, because ASGI hands the router the decoded path. The `Result` in the
container advertises the same dead `id`.

Rare while every `sub` is a UUID, and precisely the hazard the per-user results
route was added to close: a URL the platform composes and does not serve. **Done
when** either the route matches an identifier containing a slash, or such a
`userId` is refused at the score post with a message saying why — the second is a
narrowing of AGS and would need recording as one.

## Out of scope

- Reopening the "every member carries a window" ruling itself, or the "every
  seeded course carries a title" ruling. Item 1 adds a case beside the first; it
  does not withdraw it.
- Building E1's roster sync or E3's passback. Every item here is about what the
  *mock* shows them.

## Acceptance criteria

- [ ] One seeded member carries no enrollment extension, with a test, and
      E0-15's "every member" criterion is amended in the same pull request.
- [ ] NRPS's `role`, `limit` and `rlid` either work or are refused.
- [ ] At least one line item id carries a query string, with a test that a
      scores URL built from it is correct.
- [ ] The results container pages with a `Link` header and honours `limit`.
- [ ] A single-page roster carries the relations that apply to it.
- [ ] The client-credentials grant is built, or its four moving parts are
      written into the ticket that will build the roster sync.
- [ ] `read_line_item` has a criterion or is gone.
- [ ] A `userId` containing a slash either routes or is refused, and no result
      URL the platform hands out 404s.

## Definition of done

**Tests apply.** Every item above is a test that fails first — most of these
findings were proven by mutation on a clean tree, and the reproductions are in
PR #31's review comment.

**Docs apply, briefly.** `README.md`'s description of the two services changes
wherever this changes them.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light**, on the same terms as E0-15: the mock is
not a product surface. Item 6 is the one to look at, and `app-security` has
already reviewed the deferral once.

## What E0-15's own pull request closed

Indexed so this file is a record of the round rather than of its remainder. Four
HIGH, five MED and one LOW were fixed in place — the count is spelled out because
an index the next ticket trusts is worth more than a tidy sentence:

- A score carrying `scoreGiven` with no `scoreMaximum` was accepted (HIGH).
- A stale `timestamp` silently regressed a grade where AGS requires 409, and a
  `timestamp` that was not a timestamp was accepted (HIGH).
- The line-item container was unpaged and ignored every filter parameter (HIGH).
- The late-add test asserted only that two enrollment moments differed, so an
  *early* add passed it (HIGH).
- `activityProgress` and `gradingProgress` were checked for presence, not value
  (MED).
- The `resultUrl` the platform handed back 404'd (MED).
- A posted `scoreMaximum` differing from the line item's was silently dropped
  (MED).
- `"end": null` present-rather-than-omitted was unasserted, so a window emitted
  with no `end` key at all passed (MED).
- The roster walk's "no member is dropped" rested on a lower bound that both
  launch users satisfied, so a slice losing one member per page boundary passed
  (MED).
- "Two start letters" was wrong in four records; the seed uses three (LOW).

A second review pass over those fixes found one HIGH, seven MED and seven LOW,
and the same rule was applied again: the HIGH and the easy MED were fixed, and
what remains is in the scope above. Two of that pass's findings were about this
file and the pull request body rather than about the code, and both are corrected
rather than carried forward.
