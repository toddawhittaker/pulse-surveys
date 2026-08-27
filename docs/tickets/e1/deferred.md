# E1 — deferred items

Everything an E1 ticket deferred rather than fixed, in one place, so the end
of the epic gets a cleanup pass instead of an archaeology dig. Each entry
names the ticket and pull request it came from and keeps the "done when" that
governs it. An item leaves this file by being fixed (say where) or by being
handed to a named owner outside E1 (say whom); it is never silently dropped.

Every E1 pull request that defers something adds it here in the same PR.

## From E1-01 — view sweep closure (PR #92)

1. **The catalog whole-row rule misses the join form** (MEDIUM, deferred
   under the round's declared stopping rule). Postgres drops the whole-row
   dependency row (`refobjsubid = 0`) once a view also names any column of
   the same table, so
   `SELECT to_jsonb(u) FROM enrollment e JOIN "user" u ON u.id = e.user_id`
   is invisible to the catalog half. The file-text sweep catches every
   whole-row spelling the reviewer could write, and the catalog catches every
   column-grain one — complementary blindnesses whose union is total only
   because every live view must ship through a `views_sql/` file.
   **Done when** the catalog half flags a whole-row read of a guarded table
   in the presence of a join (compare the relation edge in `pg_depend`
   against the recorded column set, disambiguating via `pg_get_viewdef`),
   proved by the join-form planted control.

2. **`PERSON_TABLES` is a hand-written closed list.** Nothing guards that a
   future person table joins it. E1-05 and E1-11 are the tickets that could
   add one; their reviews must ask the question.
   **Done when** both reviews have asked it and recorded the answer, or a
   structural source for the list exists.
   *E1-05 asked it and the answer is no.* It adds one table,
   `tool_signing_key`, holding an `id` and a private key PEM. It carries no
   subject, no name and no address, nothing joins it to a person, and nothing
   reads it until E1-06 signs with it — so `PERSON_TABLES` is unchanged.
   Recorded in [ADR 0082](../../adr/0082-the-tools-signing-key-lives-in-the-database.md)
   and beside the model. E1-11 still owes its half.

3. **The two E0-34 planted-file tests have a not-load-bearing message
   check.** Pytest assertion rewriting satisfies the check without the
   message being real; E1-01 made the same one-line fix to its own control
   and left these two.
   **Done when** both tests get that one-line fix.

4. **`test_every_read_view_is_created_from_a_sql_file_under_views_sql` is
   not `invariant`-marked.** The text/catalog complementarity in item 1
   rests on it, but it runs only in the ordinary suite, not the isolated
   §4.1 pass.
   **Done when** it carries the marker and the isolated pass collects it.

## From E1-05 — registration owns its endpoints and its keys

1. **A non-development deployment has no way to supply the tool's signing key.**
   Custody is a `tool_signing_key` row
   ([ADR 0082](../../adr/0082-the-tools-signing-key-lives-in-the-database.md)),
   and the only thing that writes one is the demo seed, which refuses to run
   anywhere but development (ADR 0063). So a deployment has no key, and nothing
   deployed signs today — E1-06 and E1-11 both run against the mock platform in
   development — which is what makes the gap survivable for now rather than a
   hole. It is a deliberate omission, not an oversight: the alternative was a
   configuration variable holding a private key, which
   [ADR 0082](../../adr/0082-the-tools-signing-key-lives-in-the-database.md)
   rejects, and inventing a supply route before anything needs one would fix the
   shape of it in the wrong ticket.
   *E1-06 made the gap visible rather than closing it.* The tool publishes its
   key set at `GET /lti/jwks` now, and a deployment holding no row answers `503`
   there — loud at the point the key is missing, rather than an empty key set a
   platform would accept and store
   ([ADR 0085](../../adr/0085-the-tools-key-set-is-public-in-every-environment.md)).
   Nothing about the supply route changed.
   **Done when** a non-development deployment has a documented and tested way to
   put a signing key in that table — with the rotation question answered too,
   since the one-row rule forbids the two-key overlap a real rotation needs.
   **Owner:** the epic that first registers a real platform and therefore first
   needs a production signer.

2. **The address rules judge spellings, not addresses** (security review,
   LOW). Rules 3 and 4 of ADR 0081 accept `127.1`, bare-decimal and
   dotted-hex literals, and resolver-backed names (`metadata.google.internal`)
   for the exact addresses they refuse — ADR 0081's residue paragraph holds
   the measurements. Capped by rule 1 (cleartext off this machine is refused
   regardless of spelling) and by the seed being the only writer today.
   **Done when** the two helpers resolve the host and judge every returned
   address, or refuse integer/dotted-hex host literals, with test pairs on
   both sides — before E11's console becomes a second writer.

3. **The write-time chokepoint is a call convention** (security review,
   LOW). Nothing — mapper event, sweep, or grant — makes a future writer of
   `lti_platform` call `refuse_invalid_registration_addresses`; a writer
   going through SQLAlchemy without the call is as unjudged as the raw-SQL
   writer ADR 0081 records.
   **Done when** the call is structural (a `before_insert`/`before_update`
   event on `LtiPlatform`) or a sweep asserts every write site calls it —
   in the same change that adds the second writer, E11 at the latest.

## From E1-03 — TypeScript 7 with typescript-eslint, one change

1. **The TypeScript 7 pair did not move, because no released
   `typescript-eslint` accepts TypeScript 7.** The ticket's own escape clause
   was taken: nothing was pinned, nothing was forced, and the measurement is
   recorded under entry 3 of
   [`../deps-triage-2026-08-24.md`](../deps-triage-2026-08-24.md). The
   repository stays on `typescript` 6.0.3 with `typescript-eslint` 8.67.0, both
   exact-pinned and both green. Forcing the pair past npm's peer check installs
   and then fails the lint gate outright, so there is no partial move to take
   either.
   **Done when** `npm view typescript-eslint peerDependencies` reports a
   `typescript` range admitting 7.x, and the pair then lands in one change with
   `npm ci` resolving and the four Node-facing gates green — that is triage
   entry 3's "done when", unchanged.
   **Owner:** whichever epic is running when that range widens; it is no longer
   E1's to wait for.

## From E1-04 — frontend scaffold and the five empty landing views

1. **The three webfonts are declared and not loaded.** `design/tokens.css`
   names Literata, Schibsted Grotesk and Spline Sans Mono with system-safe
   fallbacks (`Georgia, serif`, `'Helvetica Neue', sans-serif`,
   `ui-monospace, monospace`), and nothing fetches the real faces — no
   `<link>` in `frontend/index.html`, no `@font-face`, no self-hosted files.
   The five landing views therefore render in the fallbacks today.

   This is E0-18's reasoning carried forward rather than a new one: Pulse
   renders inside somebody's LMS in an iframe, so a Google Fonts request from
   here is a third-party fetch made on a student's behalf from inside their
   institution's page, and choosing between self-hosting the files and going
   without is a decision that deserves a real screen to be judged against.
   `docs/DESIGN_BRIEF.md` treats the type contrast as load-bearing — "how the
   tool reads as its own considered thing inside the host" — so going without
   is a real cost and not the safe default it looks like.

   **Done when** the strategy is decided (self-host the four faces in the
   bundle, or ship the fallbacks and say so in the brief) and built, with
   E2's first real screen, where there is something to look at while
   deciding. Whichever way it goes, `design/tokens.css` stays the place the
   families are named.

2. **The application sends no security response headers.** No route sets
   `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, or
   a framing policy; `backend/app/main.py` carries no header middleware at
   all. This is pre-existing and app-wide rather than this ticket's doing —
   E1-04 is simply the first ticket to serve real HTML and JavaScript from
   the app factory, which is what makes the absence worth recording.

   The header set has to be designed rather than copied from a hardening
   checklist: Pulse renders inside an LMS iframe, so the usual first move —
   refuse framing outright — would break every launch. `frame-ancestors` has
   to admit the platforms that may frame the app, and the CSP has to allow
   what the bundle legitimately loads while still refusing inline script.

   **Done when** the app factory attaches a deliberate header set to every
   response — a CSP, `X-Content-Type-Options: nosniff`, a `Referrer-Policy`,
   and a `frame-ancestors` directive naming who may frame the app — with a
   test pinning each header. Scheduled before E2 puts real survey content in
   the SPA.

## From E1-06 — the mock learns the client-credentials grant

1. **The mock's token endpoint does not track `jti`.** A tool-signed assertion
   can be replayed for a second token anywhere inside its 300-second life; the
   ticket's six refusals do not include replay, and refusing one needs state
   the endpoint deliberately does not keep yet. Named by the implementer
   rather than found by review.
   **Done when** the endpoint refuses a second request presenting an
   already-seen `jti` within the lifetime bound, proven by a pair (fresh
   `jti` granted, replayed `jti` refused) — at latest with E1-11, whose
   client's conformance claims otherwise rest on an endpoint that cannot
   notice a replay.

2. **The lifetime bound trusts the signer's own dates** (security review,
   LOW). `exp - iat` are both the assertion's claims, so a signer who dates
   both in the future mints an assertion that passes every check and stays
   spendable until its far-future `exp`. Exploiting it needs the tool's
   private key, and this is the development-only mock, which is what keeps it
   LOW; ADR 0084's decision 1 now states the measured boundary (the bound
   caps a leaked assertion, not a hostile signer).
   **Done when** the endpoint also refuses an assertion whose `exp` lies
   further than the bound plus a stated skew allowance beyond the platform's
   clock, proven by a pair on both sides of that line — in the same change as
   item 1, E1-11 at latest.

3. **The unpadded-spelling pin covers one key set of three.** The battery's
   survivor taught that decode-based assertions forgive how a JWK integer is
   spelled, and the fix pinned the strings — but only on the tool's
   `/lti/jwks`. The same encoder shape exists in `mock-lms/app/signing.py`
   and the mock IdP's copy, and both serve key sets this tool's launch
   verification parses; nothing asserts their `n` and `e` are unpadded.
   All three encoders are correct today (named by the implementer, the same
   defect one level out).
   **Done when** a test pins the unpadded base64url spelling of every served
   key set — the mock LMS's and the mock IdP's beside the tool's — owed with
   the first ticket that touches either mock's signing surface, E1-07 or
   E1-08, whichever lands first.
   *E1-07 closed the mock LMS's third*: `tests/integration/test_mock_lms_
   launch.py::test_the_published_keys_numbers_are_spelled_as_unpadded_
   base64url`, built the same way as the tool's own and proven against the
   same mutation (`.rstrip(b"=")` dropped from `mock-lms/app/signing.py`'s
   `base64url`) before being trusted. The mock IdP's copy is untouched by
   E1-07 and stays open, owed to whichever ticket next touches `mock-idp/app/
   signing.py`'s encoder.

## From E1-07 — the mock mints deliberately wrong launches

1. **The defect selector vocabulary is copied, not shared.** `?defect=<name>`
   answers to `app.wrong_launches.ALL_SELECTORS`, and nothing outside
   `mock-lms/` can import that tuple by name — `mock-lms/app` and
   `mock-idp/app` are both packages called `app` (SPEC §13), the collision
   ADR 0039 already records for mypy. `tests/integration/test_mock_lms_
   wrong_launches.py` therefore holds its own copy of all eighteen strings,
   and E1-08's Playwright spec (the ticket this vocabulary exists for) will
   need a third. A rename in `app.wrong_launches` with no matching rename
   in a copy fails loudly — the dispatcher's 400 names the value it did not
   recognise — but only once something actually calls it with the stale
   name. See ADR 0088's Consequences.
   **Done when** one source serves the vocabulary to every consumer that
   is not `mock-lms/` itself — a `/mock/defects` inspection route the mock
   serves its own selector list from, most likely, so a Playwright spec (or
   this suite) can assert against what the mock says it answers to rather
   than a copied literal — proven by a test that the served list and
   `ALL_SELECTORS` agree. Natural to build alongside E1-08, whose Playwright
   spec is the consumer this would most directly help.

## From E1-08 — the launch door on pylti1p3

1. **The algorithm pin is not proven load-bearing end-to-end.**
   `app.lti.launch._refuse_unpinned_algorithm` is ADR 0073's closing
   condition — the accepted algorithm is a hardcoded constant, refusing an
   `alg: none` or an HMAC-with-the-public-key confusion before the signature
   is checked. It is defence in depth: `pylti1p3`'s own key/algorithm matching
   independently refuses both today (`get_public_key` accepts only a key whose
   `alg` matches the header's, and the platform publishes RS256 keys), so
   mutating this pin alone leaves the launch green — the verifier's one
   survivor. Extracting it into its own helper lets a unit test call it
   directly and catch a break in *this* guard; what a unit test cannot show is
   that the pin is load-bearing *end-to-end* — that the whole door refuses a
   launch `pylti1p3`'s matching would otherwise accept — because there is no
   live forgery: both layers agree.
   **Done when** a mock platform variant publishes a permissive-algorithm key
   set — a JWK a confused verifier would accept an `alg: none` or HS256 token
   against — and an end-to-end refusal test drives a launch signed that way and
   asserts the door still refuses it, so the pin's removal turns a green launch
   red. Owed to the ticket that gives a mock platform a permissive-alg mint (a
   natural companion to E1-07's wrong-launch selectors).

## From E1-10 — launch-time provisioning and the sanctioned writer

1. **E1-11 must pick the platform to mint a token for off `section.lti_deployment_id`,
   and nothing yet makes it.** E1-10's round-3 security review gave `section` a
   binding — `(lti_deployment_id, lms_context_id)`, unique — because a section had
   no identity a copied course could not reproduce, and a launch from a copy
   repointed the original's stored roster address. The column that closed it is
   also the answer to a question E1-11 has to ask on every sync: *whose* client
   credentials does this section's roster get fetched with? A context identifier
   means nothing outside the registration that issued it, and a section's course
   and term say nothing about a registration at all — so a sync that resolved the
   platform any other way (the only registration it can find, the first one, one
   named in configuration) could present one institution's token to another
   institution's roster service, which is the same failure the binding closes,
   arriving an epic later. There is nothing structural stopping it: the sync will
   hold the section row and can read whatever column it likes.
   **Done when** E1-11's client resolves its registration from the section's own
   `lti_deployment_id` and a test drives two registered platforms, each with a
   section, and asserts each sync presents the assertion of its own platform —
   a test that fails against a resolver that takes whichever registration it
   finds first. Recorded in
   [ADR 0091](../../adr/0091-what-a-launch-provisions-and-what-it-writes-down-instead.md)'s
   consequences as well, because that is where a reader of the column will be.

2. **The launch day is UTC's day, not the institution's.**
   `app.services.provisioning` is handed a session and the launch's claims and no
   settings, so the term a new section belongs to is chosen against
   `datetime.now(UTC).date()`. A launch in the hours either side of a term
   boundary can be read into the neighbouring calendar day and land in the
   neighbouring term. E1-11's sync will want the same value and has the same
   problem.
   **Done when** the launch moment reaches the writer — the door has `Settings`
   in hand and the institution timezone is on it — and a test drives a launch at
   an hour that falls on different dates in UTC and in the institution's zone,
   asserting the term the institution's calendar names.

3. **Sections stored before the binding carry a synthetic context id.** The
   round-3 migration binds them to the one registered deployment under a
   `pre-binding-section-` identifier and refuses where there is no unambiguous
   registration. Nothing a platform ever issues looks like that, so no launch can
   reach one of those rows — which is right for rows no launch created, and the
   demo seed's eighteen sections are all of them today. The residue is that
   `lms_context_id` is not universally a value some platform issued.
   **Done when** either no such row exists in any database anybody keeps (a
   `make docker-build` and a re-seed is the whole of it for the demo stack), or a
   later ticket decides that a section with no real context is a state worth
   naming rather than a value worth inventing.
