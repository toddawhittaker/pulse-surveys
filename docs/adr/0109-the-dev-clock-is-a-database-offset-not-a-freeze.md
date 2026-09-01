# 0109 — The development clock is a database offset, not a freeze

## Context

SPEC §3.1 makes everything E2 does wall-clock behaviour: a survey window opens
Friday 18:00 and closes Sunday 23:59:59 in the institution's timezone, and what a
student sees depends on which side of those boundaries the moment is. E2 has to be
testable by hand as well as by pytest — the stack is driven through a browser
during development, and waiting until Friday evening to see a Friday evening is
not a development loop.

Before E2-04 there was no clock abstraction at all. The scheduling-relevant reads
were three direct, byte-identical calls —
`datetime.now(ZoneInfo(settings.institution_timezone)).date()` — in
`services/provisioning.py` (which term contains a launch),
`services/roster_sync.py` (which day a member was first seen) and
`services/authz.py` (whether an enrollment is live today). Two of those carried a
docstring proposing a shared helper and declining to take it, because it moved a
function across a module boundary.

The spec says nothing about how a developer moves the clock, and the reasonable
options differ in ways that matter: a freeze against an offset, a process setting
against a row, and — the part with a security consequence — which clocks the
override is allowed to reach at all. E2-04's own security header states the last
one: "a movable clock on nonce, state, or token expiry checks would open the
replay window E1 closed."

## Decision

**One clock service, and a development-only override held as a database row
carrying an offset.**

Four parts, and each is a separate choice.

1. **`app.services.clock` is the one place scheduling and visibility code asks
   what time it is**, with two functions: `now(session, *, settings)` for the
   effective instant in UTC, and `today(session, *, settings)` for the effective
   date in `settings.institution_timezone`. `today` is derived from `now`, so an
   override moves both or neither. The three call sites above read it, and E2-06's
   window logic is written against it from the start.

2. **The override is a row, not a process setting.** `clock_override` holds at
   most one row — a unique index over `(true)`, the shape `institution` already
   uses (ADR 0072) — with `pretend_now` and `anchored_at`, both
   `AwareDateTime` (ADR 0019). The tool and the Celery worker are two processes,
   and E2-06's weekly scheduling runs in the worker: an override held in an
   environment variable, a module global or a per-process cache would move one and
   leave the other on real time, and the disagreement would be invisible until a
   window scheduled in one process was read in the other.

3. **The override is an offset and not a freeze.** The effective now is
   `real + (pretend_now - anchored_at)`, so time keeps running from wherever it was
   moved to. A freeze — storing an instant and answering it — is the shorter
   implementation and makes the feature useless for what it exists for: a stack
   frozen at Friday 18:00 never reaches Sunday 23:59:59, so no window ever closes
   and nothing that depends on elapsed time can be driven by hand.

4. **The override applies only where `is_development(settings)`, and the gate is
   in the service.** Nothing in the schema marks a row as development-only and no
   constraint could, so the environment is checked before the table is read at
   all: a deployment that acquired a row — a restored dump, a copied database —
   issues no statement about it and goes on reading the real clock. The `/dev`
   control that writes the row carries the console's own in-handler gate (ADR
   0079) and answers `404` — never `405` — to every method it does not serve,
   which is stricter than the console beside it (ADR 0087 kept `/dev`'s measured
   `405 Allow: GET`) because a page is a thing to read and a control is a thing to
   attack.

   **How "every method" is enforced, and how it was not.** Each clock path is one
   route that matches for *any* method, with the handler answering a method that is
   not `POST` with the same bare `404` the environment check gives — a
   `starlette.routing.Route` whose method restriction is cleared, because
   `APIRouter.api_route` requires a list and every route class FastAPI builds
   carries one. The first version instead *enumerated* the verbs it would answer,
   and the security round of 2026-09-01 measured what that misses: a method outside
   the list — `TRACE`, or any token nobody thought of — matches no route, so
   Starlette answers `405 Allow: POST` from the router before the handler runs, and
   an unauthenticated caller learns in one request both that this build carries a
   clock control and that `ENVIRONMENT` is not `development`. Adding the missing
   tokens would have been the third widening of a list that can always be stepped
   outside (`docs/MISTAKES.md` entry 35). The cost of the fix is the two paths'
   OpenAPI entries and their `Depends`, so they open their own session the way
   `app.main`'s framing middleware does; the walk that proves it is
   `test_the_dev_clock_control_answers_404_to_every_method_outside_development`,
   which drives the seven standard verbs plus `TRACE` plus an arbitrary token.

**What the readout shows.** `/dev` renders the effective now as ISO 8601 in the
institution's timezone with its offset and to the second — `2026-09-04T18:30:00-04:00`.
The zone because SPEC §3.1 makes it the one every window is expressed in and so
the one a developer setting a clock is thinking in; the offset because the reading
sits beside a table of derived dates and would otherwise be ambiguous; the seconds
because the whole point of part 3 is only visible if the clock is seen running.
The form field is an HTML `datetime-local` value — a wall time with no offset —
read in that same zone.

### The clocks this service does not touch

Explicit, because the alternative is each ticket deciding again:

- **Launch validation** (`app/lti/launch.py`) — nonce and state expiry, an
  `id_token`'s own `exp` and `iat`, clock skew. This is the one with a
  behavioural pin: a platform signs on real time, so a tool validating against a
  clock five years ahead refuses every honest launch, and one validating against a
  clock five years *behind* accepts a token that expired. Both directions are the
  replay window E1 closed.
- **Session expiry** — the same argument one door along.
- **Audit timestamps**, and every `func.now()` column default. An audit record
  says when something happened, and a record that says otherwise is worse than no
  record.
- **The NRPS debounce window and the `nrps_call` log**
  (`services/roster_sync.py`, which keeps its two `datetime.now(UTC)` reads).
  Protocol and observability instants, not calendar ones: a debounce measured
  against a moved clock would fire a sync on every launch or on none.
- **Celery beat's own firing schedule.** The hourly sync fires on real time; what
  it *computes* uses the service.

### One column named now, so two tickets cannot each leave it to the other

**`response`'s submission timestamp is written by the application through this
service** (E2-08 does the writing), and not by a server-side default. A window is
judged against the effective clock, so a submission accepted inside an overridden
window and then stamped with `func.now()` would be a row whose own timestamp sits
outside the window that accepted it — and E3's participation formula counts
exactly those rows. The two readings have to be the same reading.

### The sweep, stated as a review rule rather than built

A new direct `datetime.now` in scheduling or visibility code is the thing a review
looks for. That is written down here, in `app/services/clock.py`'s docstring, and
in the roster sync's comment beside its two remaining real-time reads — and it is
*not* a sweep. A test that forbade `datetime.now` outside this module would have to
carry an exemption for every clock in the list above, which is most of them; the
list is short, the exemptions would outnumber the catches, and an inventory that
size is the shape `docs/MISTAKES.md` entry 35 is about.

## Alternatives rejected

- **A frozen clock** (store an instant, answer it). Simpler, and it is the
  implementation that passes a single-reading test. Rejected: no window it opens
  ever closes, so the one thing E2 needs to drive by hand — a cycle — is exactly
  what it cannot do.
- **An environment variable or a module global.** No migration, no grant, no
  table. Rejected: it moves one process. The worker is where E2-06 runs, and two
  processes disagreeing about what time it is fails in the place hardest to see
  it.
- **`freezegun` / `time-machine`.** Named out of scope by the ticket, and the
  reason holds here: they patch a process, so they answer neither the two-process
  problem nor the browser one, and adding a dependency needs a reason that an
  injectable service removes.
- **Faking time in the browser.** The backend decides what is open and the page
  renders what the API answers; a clock moved only in the browser would show a
  student a window the server would refuse.
- **A `singleton boolean` column with `UNIQUE` and `CHECK` for the one-row rule.**
  Measured and rejected in ADR 0072 for `institution`; the same argument applies —
  three schema objects to say what one index says, and a column with no meaning in
  the table.
- **Putting the override in `models/term.py`.** The nearest existing home, and the
  wrong one: `term` is the institution's configured calendar, which an
  administrator sets and the product reads. This is a scaffold a developer sets
  and no deployment has.
- **A third service function for "is an override standing".** The `/dev` readout
  needs it and nothing else does; it is answered by a direct read in the console,
  where the sections table already reads models directly. A question with one
  caller does not belong in the module every scheduling read passes through.

## Consequences

- **`pulse_app` holds `SELECT, INSERT, DELETE` on `clock_override`**, and
  `UPDATE` is withheld — the pair of instants is written together, and an anchor
  rewritten alone gives a clock running at the right rate from the wrong origin.
  This is a widening of what the application connection can reach, deliberately
  recorded: the grants file carries the sentence for each verb, and
  `RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py`
  is the record it is measured against. The table carries two timestamps and no
  person, joins to nothing, and has no view over it, so SPEC §4.1's read-path
  rules do not reach it.
- **The gate is behavioural in two places and structural in none.** Nothing in the
  schema stops a `clock_override` row existing on a deployment; what stops it
  mattering is the service's environment check, and what stops it being *created*
  is the two routes' 404. Both are asserted in both directions.
- **The `/dev` control is unauthenticated, like the console it sits on.** It has no
  session and no CSRF token, because `/dev` has neither — which is precisely why
  the environment gate is the whole of its safety, and why the method probe is
  answered more tightly here than on the page.

  **Accepted residue, named rather than left to be found.** The two controls take a
  simple form — `application/x-www-form-urlencoded`, no token, no `SameSite` cookie
  to lean on because there is no cookie at all — so any page a developer visits
  while their stack is up can auto-submit a cross-site form to
  `http://localhost:8000/dev/clock` and move that stack's clock. Nothing comes back
  to the attacker: the answer is a `303` the attacking page cannot read, so this is
  a write and not a read.

  Two things already narrow it, and neither is a reason to stop reading here.
  `docker-compose.override.yml` publishes the API as `127.0.0.1:8000:8000`, so a
  host on the same network cannot post directly — the request has to come through a
  browser running on the developer's own machine. And browsers have begun
  restricting requests from a public page into loopback, which E2-13 already records
  hitting from the other side ("Chromium's Local Network Access rules around the
  synthetic-iframe wrapper"). That is a moving target and belongs to the browser
  rather than to this design, so it is written down as context and relied on for
  nothing.

  The residue is accepted as development-only, beside the console's own much larger
  exposure: `/dev` offers one-click sign-in as *any* seeded identity, and a
  cross-site `GET` to one of those links is the same class of attack with a bigger
  prize. The gate for both is the same and it is the one that matters — the
  exact-equality environment check (ADR 0063, ADR 0079) that runs before every
  write, so none of this reaches a deployment. What it costs on a developer's laptop
  is a confusing clock, which the console's own effective-now readout exists to
  explain.

  One cheap hardening was considered and not taken: **an `Origin` or
  `Sec-Fetch-Site` check on the two POSTs**, which would refuse the cross-site form
  specifically. It is not taken here because it would put a second gate on this
  surface for whoever next has to keep the two agreeing, while the console beside
  it — the larger hole, and the one an attacker would actually aim at — would still
  have none. If it is taken, it should be taken for `/dev` as a whole and in its own
  change, so that the page and the control are refused on the same rule.
- **A stack left overridden stays overridden**, across restarts of both processes,
  because the row survives them. That is the point, and it is also the cost: the
  console shows the effective clock beside the sections table so that an
  overridden stack is never mistaken for a live one, and the browser spec that
  drives the control clears the row in a `finally`.
- **E2-06 has a seam to write against** and does not need to invent one, and
  E2-08's `response` timestamp has a rule it can be held to rather than a
  question.
