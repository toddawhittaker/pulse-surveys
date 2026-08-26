# Pulse Surveys

An LTI 1.3 / LTI Advantage tool that runs a brief, standardized weekly feedback
cycle in every enrolled course.

1. Students answer five questions each week inside the LMS.
2. Participation credit passes back to the gradebook automatically.
3. Every Monday, instructors get a report: rating distributions, workload data,
   de-identified comments, and an AI-generated summary.
4. Instructors publish a response (with advisory AI coaching); students see the
   aggregate results and that response, which closes the loop.
5. Academic leadership — lead faculty, chair, dean, VPAA — sees roll-up views
   across their span of oversight.

The design goal is trust. Students have to believe their responses are
confidential, and instructors have to believe the data is fair. Most of the
non-obvious requirements in the spec exist to protect one of those two beliefs.

## Status

Early, but no longer empty. The backend package exists — a FastAPI application
factory, the environment-driven settings object, a health endpoint, and a
database engine with a session per request — and it runs in a container
alongside a Celery worker, a Celery beat scheduler, Postgres, Redis, Mailpit,
and the two mocks described below — a fake LMS to launch from and a fake identity
provider to log in through, one for each of the two entry doors in SPEC §2. CI enforces lint, typing, the test suite,
migration drift, dependency audit, license compatibility, and that the stack
comes up healthy.

The schema is real now. Migrations create the containment hierarchy
(institution through section), the term calendar and start-letter map, the
identity tables with `user` split from `user_identity`, the LTI registration
tables, and role assignments with the supervision graph. What sits on top of it
does not exist yet: no read views, no authorization, and no HTTP routes beyond
`/healthz`. The frontend exists and is deliberately empty: React, TypeScript and
Vite, served by the application at `/app`, with one blank landing view per role
area and nothing behind any of them. The job runtime is wired but does no work — the
beat schedule is empty, and the only task is a `ping` that proves the round
trip. The AI side has its typed contracts and versioned prompt directory but no
gateway to call a provider with.

## Run it locally

Docker, and nothing else.

```sh
cp .env.example .env
make up             # docker compose up -d
make logs           # follow the logs
make down           # docker compose down -v — discards the database too
```

`GET http://localhost:8000/healthz` answers with the service name, the version,
and the environment it was configured with. The interactive API documentation is
at `/docs`, the captured mail is at <http://localhost:8025>, the mock LMS is at
<http://localhost:8080>, the mock IdP is at <http://localhost:8081>, and Postgres
and Redis are on their usual ports. All of them bind to `127.0.0.1` only.

The developer test console is at <http://localhost:8000/dev>. It lists the mock
IdP's web-login people as one-click "sign in as" links and links to the mock LMS
launcher, so both of Pulse's entry doors (SPEC §2) can be walked without typing
URLs. Like `/docs`, it is served **only** when `ENVIRONMENT` is `development` and
404s everywhere else.

`docker compose up` merges [`docker-compose.override.yml`](docker-compose.override.yml)
over the base file automatically, and that override is what publishes those
ports, mounts your checkout into the three application containers — `api`,
`worker` and `beat` — and turns on reload-on-edit for the API. Every other
deployment runs the base file alone, publishes nothing, and runs the code baked
into the image.

Copying `.env.example` is not optional: `docker-compose.yml` defaults no
credential, so a missing variable stops the stack with a message naming it.

## Background jobs

`make up` starts the job runtime along with everything else: `worker` runs the
Celery worker and `beat` runs the scheduler. Both run the API image over the
same configuration and, in development, over the same mounted checkout, so a
task is written once and reached the same way from an HTTP handler and from a
job.

**After editing anything under `backend/`, restart the two job containers.**

```sh
docker compose restart worker beat    # about three seconds; no rebuild
```

The API reloads itself and Celery does not, so without this the API runs your
edit while the worker runs the code it imported at startup. Neither one
complains. A task you have just added comes back as
`NotRegistered: app.jobs.tasks.your_task`, which at least names itself; a task
you have just *changed* comes back with the old answer and no error at all,
which is worse.

```sh
make logs                            # everything, interleaved
docker compose logs -f worker        # just the worker: tasks received and their results
docker compose logs -f beat          # just the scheduler: what it decided to fire, and when
docker compose exec api python -c "from app.jobs.tasks import ping; print(ping.delay().get(timeout=30))"
```

That last line is the whole round trip — the API container enqueues, the worker
executes, the result comes back through Redis — and it prints `pong`. Raise the
detail in both services with `LOG_LEVEL=DEBUG` in your `.env`; the worker and
beat commands read it.

To run a worker outside Docker, against the containerized Redis:

```sh
make up
celery --app app.jobs.celery_app worker --loglevel INFO
```

That needs `REDIS_URL` pointed at `localhost` in your own `.env`, for the same
reason the section below gives about `DATABASE_URL`.

The beat schedule ([`backend/app/jobs/schedules.py`](backend/app/jobs/schedules.py))
is deliberately empty: every scheduled job — window open and close, the Monday
report, roster sync, retention — belongs to a later epic. Beat keeps its
schedule file on a named volume, so the last-run times survive a restart and a
job that has already fired is not fired again when one of those entries lands.

## The AI provider

Three variables configure it, and `.env.example` documents all three:
`AI_PROVIDER_BASE_URL` is any OpenAI-compatible endpoint, `AI_MODEL_NAME` is the
model to ask for, and `AI_PROVIDER_API_KEY` is the credential — a secret, so a
real one belongs in your `.env` or in the deployment's secret store and nowhere
else.

**You can run without a key.** Leave `AI_PROVIDER_API_KEY` empty and the request
carries an inert placeholder bearer token instead of a real one, which a local
server such as vLLM or Ollama ignores:

```sh
# in your own .env
AI_PROVIDER_BASE_URL=http://localhost:11434/v1
AI_MODEL_NAME=llama3.1
AI_PROVIDER_API_KEY=
```

**Off this machine means `https`, key or no key.** The base URL may be plain
`http` only when it names this machine, as the example above does; anywhere else
startup refuses it rather than put a student's comment — and any key sent with
it — on the wire in the clear. A model reached over plain `http` inside a private
network or a cluster is not an exception: terminate TLS at the model, or run the
model alongside this application, where the local case above already covers it.

The test suite never reaches a real endpoint whatever those hold: it points the
base URL at a stub on `127.0.0.1` and asserts, with a guard under the call, that
nothing connects off this machine.

Everything a model produces enters through `backend/app/ai/`: `gateway.py` is the
only module that talks to a provider, `tasks.py` holds one function per SPEC §7.4
task, and `prompts/` holds the versioned prompt files. Today one task is wired —
comment validity — and it stores what it decided in `classification`, with the
prompt version and the model ID that produced it.

**When the endpoint does not answer, a comment is judged by its length.** SPEC
§3.3 accepts the submission rather than blocking a student on somebody else's
outage, and the row it stores says so: its prompt version reads `character-floor`
and its model ID reads `no-model`, so a verdict a model produced and a verdict a
character count produced are never confused for one another.

## The mock LMS

Pulse is launched from a learning management system over LTI 1.3, and nobody has
a spare Canvas. So the stack brings its own platform to launch from: `mock-lms`,
a small FastAPI application in [`mock-lms/`](mock-lms/) that does the platform
half of a launch — it signs the `id_token` that Pulse will one day validate
(SPEC §9.2). It is development and test only. Nothing in Pulse trusts it unless a
row in `lti_platform` says so.

`make up` starts it with everything else. Open <http://localhost:8080>, choose a
seeded user and a placement, and press **Launch**: the page posts a
third-party-initiated login request at the tool, exactly as a real platform
would. Until E1 builds the tool's side of the launch, that post lands on a 404 —
which is the honest state of a platform whose tool does not exist yet.

To register it with Pulse, take the values from
<http://localhost:8080/registration>. The keys are the column names they go into,
so `issuer`, `client_id`, `jwks_url` and `deployment_id` fill in `lti_platform`
and `lti_deployment` without translation. The same block is on the launch page.

Two things about it are worth knowing before debugging anything:

- **Its issuer key is generated per process, and never written down.** Restart
  the container and it is a different platform with a different key set, so
  anything that cached the old key set stops verifying. That is deliberate: SPEC
  §9.1 asks for issuer keys generated per test run rather than fixtures checked
  into the repository, and no private key is committed anywhere in this
  repository — a test sweeps the tree to make sure.
- **It has no reload.** The development override mounts your checkout into the
  three application containers and not into this one, so editing `mock-lms/`
  means `docker compose up -d --build mock-lms`.

### What it is seeded with

Three sections in one term, each with a roster of its own. Small on purpose: the
full demo institution is E0-17's and lives in Pulse's own database.

| Section | Course | Modality | Roster |
|---|---|---|---|
| `BIOL-215-R3WW` | Cell Biology | online, 12 weeks | 12 members — three pages |
| `MATH-140-E1FF` | College Algebra | face-to-face, 6 weeks | 7 members — two pages |
| `NURS-8100-Q2FF` | Doctoral Practice Inquiry | face-to-face, 12 weeks | 5 members — one page |

Course numbers are picked against SPEC §8's bands rather than from the prototype
screens in `design/`, every one of which is invalid under them. The section codes
are §2.2's `{startLetter}{ordinal}{modality}`, and they use more than one start
letter and both modalities so that E0-07's parser has real input.

**Who to launch as.** The launch page offers the two people enrolled in every
section, so any combination of its two selectors is a launch that works:

| Launch as | Role | What they are for |
|---|---|---|
| `mock-lms-user-instructor` | Instructor | every instructor surface |
| `mock-lms-user-learner` | Learner | every student surface |

Everybody else is a student who takes one section, and they exist so that a
roster pages and so that E3 has its edge cases. Three of them are not ordinary.
In `BIOL-215-R3WW`, student 04 enrolls three weeks after their classmates and
student 07 drops six weeks in — reported `Inactive`, with an enrollment `end`,
and still on the roster, because SPEC §3.4 has the tool learn about a drop from
the roster rather than from an absence. And in `NURS-8100-Q2FF`, student 03
carries **no enrollment extension at all** — the key is absent rather than empty,
which is what a platform supplying no enrollment dates serves, and that is every
mainstream platform. What a sync should do with that member is E1's question; the
seed exists so E1 meets it in a test.

Nobody has a name. Every person carries an email address and nothing else
personal, and every address is at a domain RFC 2606 reserves so that it can never
be delivered to. See [ADR 0050](docs/adr/0050-the-mock-roster-exposes-an-address-and-no-name.md).

### The roster and grade services

The platform serves LTI Advantage as well as the launch, and a tool finds both
services the way a real tool does — out of the two service claims inside the
`id_token`, never from a path it assembled. Nothing here is authenticated: a real
platform puts these behind an OAuth 2.0 client-credentials grant, and whichever
of E1 and E3 needs a token first is where that belongs.

- **NRPS 2.0** serves one section's roster five members at a time, and says where
  the next page is in an RFC 8288 `Link` header — never in the body. Every page
  carries `first`, `last` and `current`, including the only page of a section
  that fits on one; `prev` appears from page two and `next` only where a next
  page exists. `page` is the one query parameter the container implements: NRPS's
  own `role`, `limit` and `rlid` are **refused with a 400 naming the parameter**,
  because a platform may ignore them and a tool must filter client-side, and
  accepted-and-disregarded is the one state a tool cannot tell from a filter that
  worked. Enrollment windows ride on a namespaced member extension, because NRPS
  defines no date on a member at all
  ([ADR 0048](docs/adr/0048-enrollment-windows-ride-on-a-namespaced-nrps-extension.md)) —
  and one seeded student carries **no such extension at all**, which is what
  every mainstream platform serves.
- **AGS 2.0** creates line items, lists them filtered by `resource_link_id`,
  `resource_id` or `tag` and paged the same way the roster is, and takes scores.
  Nothing is seeded: §3.4 has the tool create "Pulse Participation" on first
  launch, so what the container answers is only what a tool put there. **Every
  line item id carries a query string** (`?type_id=<n>`, which is Moodle's own
  parameter), so a tool that builds its Score URL as `id + "/scores"` is wrong
  here rather than only against Moodle — the segment goes into the path, before
  the query.
- **What the Score service refuses** is as much of the contract as what it takes,
  because a score this mock accepts is a score a tool learns to send. A
  `scoreGiven` with no `scoreMaximum`, a negative one, a non-positive maximum, a
  `userId` that is not a string, `true` where a number belongs, an
  `activityProgress` or `gradingProgress` outside AGS's two fixed vocabularies,
  and a `timestamp` that is not RFC 3339 are all refused. A score *above* the
  maximum is taken, because AGS permits it and Canvas records it as extra credit.
  A score older than the one already held for that student on that line item is
  `409`; one at the *same* instant is taken, because a passback that times out
  re-sends an identical body and a `409` there would say the retry failed
  ([ADR 0052](docs/adr/0052-an-equal-score-timestamp-is-accepted-as-a-retry.md)).
  And a `scoreMaximum` that disagrees with the line item's own is refused rather
  than rescaled — stricter than AGS, deliberately, so that posting against the
  line item's maximum is the habit E3 forms
  ([ADR 0051](docs/adr/0051-a-disagreeing-score-maximum-is-refused-rather-than-rescaled.md)).
- **The conformant `Result`** is served per line item, filtered by `user_id`, and
  at its own URL — which is also the `resultUrl` a score post answers with, so a
  tool can follow what the platform just handed it. The container **pages**, five
  results at a time, with the same `Link` header the roster uses and the same cap
  of 100 on a `limit` a tool asks for; the filter survives into every relation the
  page advertises. A `userId` containing a slash routes rather than composing a
  URL the platform cannot serve, and a `userId` that merely *looks* like an
  encoding stays a different student. A score only becomes a `Result` if it is a
  grade: `gradingProgress` of `FullyGraded` or `PendingManual` produces one, and
  `NotReady`, `Failed` or `Pending` does not, because those say the grading
  process has not produced a grade yet.
- **`GET /mock/posted-scores`** answers with every score the platform has been
  sent, verbatim and in arrival order. It is outside the AGS namespace on
  purpose — a conformant `Result` has no timestamp and no progress fields, so
  this is the only place what the tool sent can be read back, and a tool that
  learned this route would have learned something no real platform serves
  ([ADR 0047](docs/adr/0047-the-posted-score-readback-is-a-mock-only-route.md)).

All of that is per-process and in memory: restart the container and the line
items and the posted scores are gone
([ADR 0049](docs/adr/0049-the-mock-gradebook-is-per-application-state-in-memory.md)).

## The mock IdP

Pulse has two entry doors (SPEC §2). Instructors and students arrive by LTI
launch, which is what the mock LMS above stands in for. Everybody else —
leadership, Care and Admin — logs in over OpenID Connect, because an LTI launch
requires being enrolled in some course and they are not. Nobody has a spare Entra
ID tenant either, so the stack brings its own provider: `mock-idp`, a small
FastAPI application in [`mock-idp/`](mock-idp/) serving discovery, an
authorization endpoint, a token endpoint and a JWKS (SPEC §9.2). It is
development and test only, and nothing in Pulse trusts it unless Pulse's own
configuration says so.

`make up` starts it with everything else. Open <http://localhost:8081> to see the
registered client and the seeded identities; the same values are JSON at
<http://localhost:8081/mock/registration>, which is what E1's login work and the
end-to-end specs read
([ADR 0058](docs/adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md)).

A login **starts at the client**, not on that page: send an authorization request
to `/oidc/authorize` with a PKCE challenge, pick an identity on the form that
comes back, and redeem the code at `/oidc/token` with the verifier. Until E1
builds the tool's side, the redirect at the end lands on a 404 — the honest state
of a provider whose client does not exist yet.

Four things about it are worth knowing before debugging anything:

- **It has no passwords.** The form offers the seeded people and signs in
  whichever one is posted. Which people it offers is not a list: a person may use
  this door when they hold an assignment whose role is not instructor or student,
  which is SPEC §2's rule computed rather than copied
  ([ADR 0060](docs/adr/0060-the-mock-provider-authenticates-a-seeded-subject.md)).
- **It is strict where a real provider is strict, and a little stricter.** PKCE is
  required and S256 only; `state` and `nonce` are required; an authorization code
  is good once, for sixty seconds, and a failed exchange spends it too; a
  `redirect_uri` that is not the registered one is refused with a page rather than
  a redirect; a parameter sent twice — in the query, in the body, or once in each
  — is refused rather than resolved last-wins; a scope it does not serve is
  refused rather than quietly dropped, and one whose tokens are separated by
  anything but a single space is refused rather than split into tokens the client
  never sent. A mock that shrugged at any of those would teach the tool side to
  shrug too.
- **Nothing a client sends is trimmed, and that is load-bearing.** Values are
  checked exactly as they arrived and refused, never repaired: a `code_verifier`
  wrapped in whitespace — which is what `base64.encodebytes()` produces — is
  `invalid_grant` here as it is at Keycloak, Okta and Auth0, and `state` and
  `nonce` come back byte for byte, because a client compares both against what it
  sent.
- **A session carries what the granted scopes cover.** `openid` alone gets the
  subject, the audience, the nonce and the Pulse roles claim, and **not** `email`
  or `preferred_username`: ask for `email` and `profile` if you want those, as you
  would at Azure AD, Okta or Google. The token response echoes the grant, so what
  it declares and what the ID token carries cannot disagree. The roles claim is
  not gated on any scope — it is namespaced rather than one of the registered
  claims OIDC Core §5.4's table governs, which is how Azure AD, Auth0 and Okta
  release role claims too.
- **Its signing key is generated per process, and never written down.** Restart
  the container and it is a different provider with a different key set, so
  anything that cached the old keys stops verifying. No private key is committed
  anywhere in this repository — a test sweeps the tree to make sure.
- **It has no reload.** Like the mock LMS, the development override mounts your
  checkout into the three application containers and not into this one, so
  editing `mock-idp/` means `docker compose up -d --build mock-idp`.

### Who it can sign in

Eight people, one per web-login role plus the person who holds two assignments.
Nobody has a name — Pulse owns person records (§2.1), so a fake IdP inventing one
would be inventing the half Pulse is responsible for — and every address is at a
domain RFC 2606 reserves.

| Sign in as | Roles the session states | Also holds |
|---|---|---|
| `mock-idp-user-vpaa` | `VP_ACADEMICS` | — |
| `mock-idp-user-dean` | `DEAN` | — |
| `mock-idp-user-assistant-dean` | `ASSISTANT_DEAN` | — |
| `mock-idp-user-chair` | `CHAIR` | — |
| `mock-idp-user-lead-faculty` | `LEAD_FACULTY` | — |
| `mock-idp-user-admin` | `ADMIN` | — |
| `mock-idp-user-care` | `CARE` | — |
| `mock-idp-user-care-who-teaches` | `CARE` | an `INSTRUCTOR` assignment, which uses the other door |

The last row is the one worth understanding. She really does teach a section, and
she really does work in the Office of Community Standards; she logs in here for
the second and launches from the mock LMS as `mock-lms-user-instructor` for the
first. Her session here states `CARE` and nothing else — not because anything
filters her teaching out, but because entry doors belong to the assignment rather
than to the person (SPEC §2), and an instructor assignment does not open this one.

A session carries who she is and which roles she may act under, and **no purview
of any kind** — no college, no department, no course, no supervision edge.
Purview is computed by Pulse from its own supervision graph (§2.1), so the roles
arrive in one namespaced claim and everything about what she can see is worked
out on this side of the door
([ADR 0061](docs/adr/0061-a-session-states-roles-in-a-namespaced-claim.md)).

## The demo institution

An empty Pulse is hard to develop against, so
[`scripts/seed.py`](scripts/seed.py) builds one to work in.

```sh
make up             # the database has to be running
make migrate        # and at head
make seed           # load the demo institution
```

`make seed` runs on your machine, not in a container, so it needs the same two
things `make migrate` needs — a database this machine can reach, and a
`DATABASE_URL` naming `localhost` rather than the Compose service `db` (the
section below says where to change it) — plus one of its own: **it refuses to run
unless `ENVIRONMENT` is `development`**
([ADR 0063](docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md)).
It reads `.env` itself, so nothing has to be exported.

**Running it again is safe.** Every row is matched on the natural key the schema
already enforces — an institution's name, a course's prefix and number, a
section's code within its course and term — and re-used where it is found, so a
second run over a database only the seed has written to changes nothing, and a
run interrupted half way is finished by the next one
([ADR 0064](docs/adr/0064-the-demo-seed-is-idempotent-by-natural-key.md)).

**It will not share a database with a real institution, and says so rather than
guessing.** Course prefixes are unique across the whole table rather than per
institution ([ADR 0017](docs/adr/0017-prefix-codes-are-unique-across-the-deployment.md)),
so a database that already holds a real `MATH` cannot also hold the demo's — and
seeding it anyway would take the real one over rather than add one. The seed
refuses, naming the prefix and the department that holds it. Give the demo a
database of its own.

### What it contains, and why it is shaped that way

It is small, and every awkward part of it is deliberate — a tidy institution lets
whole classes of bug look like correct answers.

- **Two colleges**, five departments. With one college a dean's purview and the
  VP's are the same rows, and every scoping bug in the leadership roll-up looks
  right.
- **A department that groups three prefixes.** Mathematics holds `MATH`, `STAT`
  and `MIS`, which is SPEC §2.1's own example. Where every department holds
  exactly one prefix, a roll-up that aggregates by prefix and one that aggregates
  by department agree on every row, and the first is wrong.
- **Fifteen courses across all five level bands.** §5.1 compares a section only
  against others of the same length *and* level, so a level with no course is a
  comparison set nobody can build a fixture for.
- **Fall 2026, with §2.2's whole start-letter map** — twenty start positions,
  six of them digits — and eighteen sections spanning sixteen of them, seven
  different lengths and both modalities. Aggregate pages plot one line per start
  cohort, and a term with one cohort leaves that screen with nothing to select
  between.
- **An assistant dean between chairs and a dean.** Scoped to the same college
  node as the dean, with two chairs reporting through them, a third reporting
  straight to the dean, and a course of their own in the one department they do
  *not* supervise. That last detail is what makes §2.1's sentence true of these
  rows — "own led courses ∪ every supervised chair's department, a set no single
  containment node holds" — and without it a roll-up that just walked containment
  would produce the right numbers and be wrong.
- **A person wearing two hats.** The chair of Mathematics also leads a course,
  and that lead assignment reports to their own chair assignment. §2.1 calls it
  "legal and expected", and it is only expressible because a reporting edge joins
  *assignments* rather than people.
- **Three leads inside one prefix**, with courses that do not overlap, so §4.1
  invariant 2 — a lead never sees a sibling lead's course — is visible on screen
  and not only in a test.
- **Eight courses with no lead-faculty mapping**, so the path §2.1 describes as
  "a course with no mapping falls to its department chair" has something to
  exercise.

**Nobody here has a name.** Every seeded person is called what they do — `Demo
Chair of Mathematics`, `Demo Assistant Dean of Arts and Sciences` — and every
address is at an RFC 2606 `.invalid` domain that cannot receive mail. A demo seed
gets copied into staging environments by people in a hurry
([ADR 0066](docs/adr/0066-seeded-people-are-named-for-what-they-do.md)).

**The course numbers disagree with `design/`, on purpose.** SPEC §8 bands a
course level by its number — three digits in `000`–`799`, four digits in
`8000`–`9999` — and every course number drawn in the prototype is four digits
below `8000`, which is the gap between the two bands. None of them can be stored:
`course.level` is generated from the number and is `NOT NULL`, so a number in no
band is refused at write time. The seed picks its numbers against the spec.

**It seeds no survey data**, and no registration for the mock LMS. Responses,
comments and classifications arrive in E2 and E4; the platform question is
[ADR 0065](docs/adr/0065-the-demo-institution-registers-a-fictional-platform.md),
and the short version is that the demo's people belong to an invented platform at
an address that resolves nowhere, so that nothing in this repository trusts
`mock-lms` to sign a launch.

## Working on the backend without containers

Python 3.13 or newer (SPEC §7.1), and a virtual environment of your own making.

```sh
python3 -m venv .venv && source .venv/bin/activate
make tools          # the pinned CI tools: ruff, mypy, pip-audit, pip-licenses, pip-tools
make install        # the locked dependencies, plus this package, editable
cp .env.example .env
uvicorn app.main:create_app --factory --reload
```

One catch. `DATABASE_URL`, `CARE_DATABASE_URL` and `REDIS_URL` in `.env.example`
name the Compose services `db` and `redis`, because CI copies that file and
starts the stack from it, so it has to be a file the stack can actually start
from. Outside a container those names do not resolve. Either start the backing
services with `make up` and point the three URLs at `localhost`:

```sh
# in your own .env, replacing the three lines copied from .env.example
DATABASE_URL=postgresql+psycopg://${DB_APP_USER}:${DB_APP_PASSWORD}@localhost:5432/${DB_NAME}
CARE_DATABASE_URL=postgresql+psycopg://${DB_CARE_USER}:${DB_CARE_PASSWORD}@localhost:5432/${DB_NAME}
REDIS_URL=redis://localhost:6379/0
```

— or just use `make up`, which needs no such edit for the application. It is not
optional for migrations: `make migrate` and `make migration-check` run `alembic`
here on your machine, and `db` is a name only the Compose network resolves.

Configuration is entirely environment-driven and documented in
[`.env.example`](.env.example), which a unit test keeps in sync with
`app.config.Settings`. The deployment-specific variables have no default,
because a working default for such a value is a misconfiguration that starts
successfully: the application refuses to start without them and names the one it
is missing.

`CARE_DATABASE_URL` is the exception, and deliberately. It is the one credential
in the cluster that can re-identify a student, so `docker-compose.yml` hands it
to `api` alone and blanks it — with the `DB_CARE_USER` and `DB_CARE_PASSWORD`
parts it is built from — on `worker` and `beat`. Those two never serve the Care
queue, and `worker` is the process that ships comment text to a third-party
model provider. `Settings` is built the same way in all three processes, so the
field has to be optional for that to be expressible at all; a reveal attempted
in a process without it fails naming the variable. See
[ADR 0042](docs/adr/0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md),
whose reversal section is why.
The `DB_*` entries are in that file for Compose rather than for the application
— Compose cannot parse a URL, so the `db` service is handed the parts
`DATABASE_URL` is built from, and each password stays written once.

They describe three database roles, and the differences matter. `DB_SUPERUSER`
is the role Postgres creates on first start; it is the cluster superuser, and it
is what migrations and system-level tasks use. `DB_APP_USER` is created
alongside it by [`scripts/db-init`](scripts/db-init) and is granted only the
right to connect and to read the views in
[`backend/app/views_sql/`](backend/app/views_sql). It is what `DATABASE_URL`
points at, so an injection in application code cannot reach a shell in the
database container, read past a row-level security policy, or read a student's
name — it holds no privilege of any kind on `user_identity`. `DB_CARE_USER`
serves the Care queue (SPEC §6.2) and is the only role that can re-identify a
student, through two `SECURITY DEFINER` functions: one records that a reveal is
about to happen and returns the record's id, and the other returns the name only
against a record the caller has already **committed**. It holds no direct
`SELECT` on that table either, so every route to a name goes through those
functions, and a caller that rolls its own transaction back keeps neither the
record nor the name. That was a real gap until E0-26 — the rows are streamed
before the caller decides, so a rollback used to keep the name and discard the
audit row — and
[ADR 0071](docs/adr/0071-the-reveal-answers-only-a-committed-record.md) records
how it was closed and what the fix costs in both directions: a row means an
access was *authorised* rather than one that certainly happened, and — the half
that matters more — nothing limits a committed record to a single spend, so the
log under-records too. Closing that is E10's. Only the `api` process is given this
credential, which is a separate control and stays.

A fourth role, `pulse_reveal_definer`, appears in `\du` and in none of this
file. It owns both halves of the reveal and holds four grants, so that the only
code able to read a name runs with a readable list of privileges rather than
the migration identity's. It cannot log in, has no password anywhere, and needs
nothing from an operator —
[ADR 0043](docs/adr/0043-the-reveal-function-has-an-owner-of-its-own.md) is why
it exists and what it does not protect against.

`DATABASE_URL` must never point at `DB_SUPERUSER`, and the Compose file keeps
that credential out of the application container entirely. See
[ADR 0009](docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
for which identity does what,
[ADR 0001](docs/adr/0001-identity-separation-by-database-role.md) for why the
runtime roles are scoped the way they are, and
[ADR 0042](docs/adr/0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md)
for why the Care queue gets a credential rather than a `SET ROLE`.

**Upgrading an existing stack past E0-10 needs `docker compose down -v`.**
`scripts/db-init` runs only against an empty data directory, so on a volume
created before this ticket `pulse_care` exists — the migration creates it — with
no password and no way to log in, and the Care connection fails to
authenticate.

```sh
make ci             # every gate, in the same order as CI
make lint           # ruff check + ruff format --check, eslint (root + frontend)
make typecheck      # mypy, strict over app/services/; tsc (root + frontend)
make test           # pytest with coverage
make frontend-build # the production build and the bundle budget
make migrate        # alembic upgrade head, against the running stack
make lock           # recompile the lockfiles after editing dependencies
```

`make ci` includes the Docker build gate, so it needs a running daemon, a free
port 8000, and a `.env`. It also includes the migration drift gate, so it needs a
database to migrate — `make up`, with `DATABASE_URL` pointed at `localhost` as
above.

`make ci` is the same set of gates as `.github/workflows/ci.yml`, so a green run
here should mean a green run there. Where the two disagree, the workflow is
right and the `Makefile` is the bug.

## Running the e2e suite locally

The end-to-end suite (`tests/e2e/`) drives a real browser through both entry
doors — an LTI launch from the mock LMS, and a web login through the mock IdP —
against the running Compose stack (SPEC §9.2). It needs the stack up, the
database migrated and seeded, and the Playwright browser installed.

```sh
# 1. Bring the stack up (Postgres is published on localhost:5432 by the override).
cp .env.example .env
make up
./scripts/ci/wait_for_health.sh api worker beat mock-lms mock-idp

# 2. Migrate and seed host-side, with DATABASE_URL pointed at localhost. The seed
#    registers the mock platform the launch door resolves against.
set -a; . ./.env; set +a
export DATABASE_URL="$(printf '%s' "$DATABASE_URL" | sed 's/@db:/@localhost:/')"
make migrate
make seed

# 3. Install the pinned Playwright browser (once per checkout), then run the suite.
npm ci
npx playwright install chromium
make e2e            # or: npx playwright test
```

The Node tooling — Playwright and the licence scanner — is pinned in the root
`package.json`, so `npm ci` installs from the committed `package-lock.json`; do
not `npx --yes playwright` (that resolves the latest version at run time).

To watch a flow in a real window while debugging, run it headed:

```sh
npx playwright test --headed                       # every spec, visibly
npx playwright test tests/e2e/web-login.spec.ts    # one spec
npx playwright test --debug                         # step through with the inspector
```

A failing run writes an HTML report to `playwright-report/`; open it with
`npx playwright show-report`. CI uploads that same report as an artifact when the
suite fails.

## How to create a migration

Every table in the schema is created by a migration, and the models are the
source those migrations are generated from. After editing anything under
[`backend/app/models/`](backend/app/models):

```sh
make up                                              # the database has to be running
cd backend
alembic revision --autogenerate -m "what you changed"
```

Read the generated file before committing it. Autogenerate is a good first
draft and not an answer: it does not see a rename (it emits a drop and an add,
which discards the data), and it cannot know what to backfill.

```sh
make migrate        # apply it: alembic upgrade head
make migration-check  # what CI runs: upgrade, then `alembic check`
```

**A model change with no migration behind it fails the build.** The
`migration-drift` job runs `alembic upgrade head && alembic check` against a
Postgres of its own, and `alembic check` exits non-zero when the tables the
models describe differ from the tables the migrations produce. That is a build
failure on the pull request rather than a surprise at deploy time, and it is why
the two commits belong together.

Two things worth knowing before writing one:

- **Migrations connect as `DB_SUPERUSER`, not as the role in `DATABASE_URL`.**
  That role is granted `CONNECT` and deliberately cannot create a table, so a
  migration run under it stops with `permission denied for schema public`. See
  [ADR 0009](docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
  and [ADR 0012](docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md).
- **A model module nobody imports is invisible to autogenerate.** Adding
  `backend/app/models/<aggregate>.py` means adding it to that package's
  `__init__.py` in the same change, or `alembic check` will cheerfully report no
  drift for a table that exists in no database.
- **`alembic check` sees tables, and nothing else this schema relies on.** It
  reads neither `pg_roles`, nor `pg_class` for views, nor `pg_proc`, so dropping
  a read view, a trigger, the Care reveal function, or a grant leaves the check
  green. A read view's SQL lives in
  [`backend/app/views_sql/`](backend/app/views_sql) as a versioned file a
  revision executes and never edits afterwards
  ([ADR 0041](docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)),
  and the integration tests are the only thing that notices when one changes.

## Documents

- [`docs/SPEC.md`](docs/SPEC.md) — product and technical specification.
- [`docs/DESIGN_BRIEF.md`](docs/DESIGN_BRIEF.md) — visual and interaction brief.
- [`design/`](design/) — exported prototype components, design tokens, and the
  data model for roles and reporting. This is the visual contract the frontend
  implements.
- [`CLAUDE.md`](CLAUDE.md) — the constraints that must not be violated,
  condensed from the two documents above.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the branch and pull request model.

## Deployment model

Single tenant, self-hosted.

## License

MIT. See [`LICENSE`](LICENSE).
