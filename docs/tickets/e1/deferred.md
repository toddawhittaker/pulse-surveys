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
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner E2, the first epic to add a view after the guard.

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
   and beside the model.
   *E1-12 was not one of the two tickets named, and it is the one that added a
   person table.* `web_login_subject` maps an identity provider's
   `(issuer, subject)` pair to a `person`, and the closed list still did not have
   to move: the table carries a foreign key to `person`, so the fixed-point walk
   in `test_identity_column_marker.py` reaches it with no name added to
   `PERSON_TABLES`, which two new tests at the foot of that module assert
   directly. The item's hazard is therefore untouched and stands as written. What
   E1-12 did meet is a second half of the same hazard that the item does not
   state: a table the walk reaches whose columns the **name-based** sweep can
   recognise none of. `idp_subject` matches no fragment in
   `IDENTITY_NAME_FRAGMENTS` and never will, so nothing in the repository would
   have gone red had that table shipped unmarked; the marker is a comment on the
   whole table (ADR 0022's third shape) and a test written for it is the only
   thing holding it.
   *E1-11 asked it and the answer is no.* It adds one table, `nrps_call`,
   holding a section reference, the URL called, an HTTP status, a count of
   members seen and a timestamp. It carries no subject, no name and no
   address, and its only foreign key is to `section` — nothing joins it to a
   person by any path — so `PERSON_TABLES` is unchanged. Recorded beside the
   model in `backend/app/models/lti.py`, and in the sentence
   `RUNTIME_BASE_TABLE_PRIVILEGES` carries for the table. Both tickets have
   now asked.
   **Done when**, for what stays open: a structural source for the list
   exists, and — E1-12's second half — the sweep reports a table it reached
   whose column names it recognises none of, rather than passing over it.
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; the per-table question is every epic's review, the structural
   source and the unrecognized-table report are E13's at the latest.

3. **The two E0-34 planted-file tests have a not-load-bearing message
   check.** Pytest assertion rewriting satisfies the check without the
   message being real; E1-01 made the same one-line fix to its own control
   and left these two.
   **Done when** both tests get that one-line fix.
   **Fixed by E1-15.** Both guards hoist their truth value
   (`clean = not offenders`), the idiom `agrees` in `test_identity_grants.py`
   measured, so the authored message is the whole of the text.

4. **`test_every_read_view_is_created_from_a_sql_file_under_views_sql` is
   not `invariant`-marked.** The text/catalog complementarity in item 1
   rests on it, but it runs only in the ordinary suite, not the isolated
   §4.1 pass.
   **Done when** it carries the marker and the isolated pass collects it.
   **Fixed by E1-15.** The marker is on and the isolated pass collects 112
   where it collected 111; the body already asserted, so nothing moved.

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
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; that epic is E3.

2. **The address rules judge spellings, not addresses** (security review,
   LOW). Rules 3 and 4 of ADR 0081 accept `127.1`, bare-decimal and
   dotted-hex literals, and resolver-backed names (`metadata.google.internal`)
   for the exact addresses they refuse — ADR 0081's residue paragraph holds
   the measurements. Capped by rule 1 (cleartext off this machine is refused
   regardless of spelling) and by the seed being the only writer today.
   **Done when** the two helpers resolve the host and judge every returned
   address, or refuse integer/dotted-hex host literals, with test pairs on
   both sides — before E11's console becomes a second writer.
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15, merged with E1-11 item 1 below into one entry; owner E11 at the
   latest.

3. **The write-time chokepoint is a call convention** (security review,
   LOW). Nothing — mapper event, sweep, or grant — makes a future writer of
   `lti_platform` call `refuse_invalid_registration_addresses`; a writer
   going through SQLAlchemy without the call is as unjudged as the raw-SQL
   writer ADR 0081 records.
   **Done when** the call is structural (a `before_insert`/`before_update`
   event on `LtiPlatform`) or a sweep asserts every write site calls it —
   in the same change that adds the second writer, E11 at the latest.
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner E11 at the latest.

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
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15, owner unchanged.

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

   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner E2.

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

   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner E2.

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
   **Fixed by E1-11.** `mock-lms/app/tokens.py` keeps a `SeenAssertions`
   store, pruned on the way in and holding an entry at least as long as the
   lifetime bound; a replayed `jti` inside that life is refused `400
   invalid_grant`. The check runs last, after the assertion has been proved to
   be this client's and to be inside both time bounds, so nothing can fill the
   store by posting junk. The pair is in
   `test_mock_lms_client_credentials_grant.py::test_an_assertion_presented_twice_is_refused_the_second_time`,
   and it is three requests rather than two: granted, replayed and refused,
   then a *fresh* assertion granted — which is what tells a `jti` store from an
   endpoint that grants exactly once. What the store deliberately does not
   survive is a restart, which is stated where it lives.

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
   **Fixed by E1-11**, in the same change. The stated allowance is thirty
   seconds (`ASSERTION_SKEW_ALLOWANCE_SECONDS` in `mock-lms/app/tokens.py`), so
   an `exp` beyond now + 300 + 30 on the platform's own clock is refused `400
   invalid_grant` however the assertion's own arithmetic reads.
   `test_an_assertion_dated_beyond_the_platforms_clock_and_the_stated_skew_is_refused`
   is the pair, one second either side of that line, with both halves stating a
   300-second lifetime so the clamp is the only thing being measured.

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
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15, owner unchanged.
   **Closed by E1 cleanup Batch B (item 4).** The third encoder now has the
   same test as the other two —
   `test_mock_idp_authorization_code_flow.py::test_the_published_keys_numbers_
   are_spelled_as_unpadded_base64url` — proven against the same mutation
   (`.rstrip(b"=")` dropped from `mock-idp/app/signing.py`'s `base64url`) by the
   battery. The encoder was already correct, so no code changed; the pin now
   covers all three served key sets and the carried entry is resolved.

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
   *E1-15's `exit-refused-launches.spec.ts` became that consumer, holding the
   two selector literals as its recorded cost.* **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner: the next ticket
   that adds a selector or a consumer.
   **Closed by E1 cleanup Batch B (item 3).** The mock serves its own list from
   a `GET /mock/defects` route (`MOCK_DEFECTS_PATH` in `mock-lms/app/config.py`),
   returning `{"selectors": list(ALL_SELECTORS)}` — the tuple itself, not a
   written-out copy. `test_mock_lms_wrong_launches.py::test_the_served_defect_
   vocabulary_is_the_platforms_own_all_selectors` pins the served list to
   `ALL_SELECTORS` in both directions, and each copied-literal consumer now
   checks itself against the served source (that suite's own copy, and this
   module's in `test_lti_launch_door.py`). The Playwright spec's two literals
   stay its own until E2 points the browser at the route; the served source they
   are owed is now in place.

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
   **Resolved in E1's cleanup Batch B, as an accepted survivor — the
   end-to-end proof the done-when asked for is impossible, and the reason is
   structural, settled from the library source, not a missing fixture.**
   `pylti1p3`'s `get_public_key` matches a published key by both `kid` and
   `alg`, then verifies the token against `export_to_pem()` of that matched key
   with `algorithms=[that key's alg]`. So an HS256-confusion launch can only be
   accepted if the door is handed a key whose PEM export equals the exact bytes
   the mock's mint keyed its HMAC with — and it never is: `jwcrypto` cannot
   PEM-export a symmetric (`oct`) key (it raises `InvalidJWKType`, which is not
   a `ValueError`/`TypeError` and so escapes even `get_public_key`'s own
   `except` clause), and an RSA key exported to PEM is not what the mock signed
   with — `hs256_confusion` keys its HMAC with the canonical RFC 7638 JWK JSON
   (`public_key_material`), and ADR 0035 bars this mock from producing a PEM to
   forge against. Removing `_refuse_unpinned_algorithm` therefore does *not*
   turn the launch green; `pylti1p3` and this construction refuse the confusion
   independently. The pin is genuinely redundant defence in depth, the
   verifier's survivor is a true redundancy rather than a test gap, and the
   end-to-end refusal is already asserted by the pre-existing parametrised
   `test_a_launch_carrying_one_e1_07_defect_is_refused_by_its_specific_guard`
   at `hs256_confusion`. Recorded the way Batch A recorded its measured
   survivor; nothing is built and nothing further is owed, so the E1-15 carry
   to E13 for this item is moot. (`alg: none` is not a second case: with no
   permissive key published there is no key its header would match, so it is
   refused at key selection and proves nothing about the pin.)

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
   **Fixed by E1-11.** `app.services.roster_sync._registration_for` resolves
   `section.lti_deployment_id → lti_deployment → lti_platform` and reads
   nothing else, and the `ServiceConnector` is built inside the per-section
   sync so that the scheduled walk cannot hoist one out of its loop.
   `test_the_roster_sync_is_a_conformant_service_client.py::test_each_section_is_synced_with_the_credentials_of_its_own_registered_platform`
   is the two-platform test, and it catches the failure in both places at once:
   the second platform's token endpoint sees no grant at all, and the token on
   the wire verifies against the wrong key set.
   `test_the_scheduled_walk_syncs_a_section_under_each_registered_platform`
   asks the same question of the hourly job, which the per-section test cannot
   see because it already calls the sync once per section.

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
   **Fixed by E1-11**, riding item 5's signature change.
   `_term_containing_the_launch_day(session, settings)` reads
   `datetime.now(ZoneInfo(settings.institution_timezone)).date()`, and
   `test_provisioning_reads_its_environment_and_its_day_from_settings.py::test_a_launch_lands_in_the_term_the_institutions_calendar_names`
   drives it, picking a zone at run time from two that bracket the clock so the
   question can be posed at any hour. E1-11's sync stamps its own `started_on`
   from the same setting rather than writing the same defect into a second
   module ([ADR 0095](../../adr/0095-the-roster-syncs-enrollment-windows-and-what-it-refuses.md)).

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
   **Closed by E1-15.** Measured 2026-08-28 on the development stack, the only
   database anybody keeps: `select count(*) from section where lms_context_id
   like 'pre-binding-section-%'` answers 0 — re-seeds since E1-10 cleared the
   bound rows, so no such row exists anywhere.

4. **A squatted binding is never reconciled or aged out** (round-3 security
   re-pass, MEDIUM). The binding makes `(course, term, lms_section_code)`
   first-writer-wins: the first context to provision a name holds it, and every
   later context whose label parses to that name is refused with a
   `context_collision`. The direction is deliberate — the alternative is the
   silent repointing round 3 closed — and the refusal is loud, so an
   administrator reading E11's surface sees a specific context being refused
   repeatedly with the identifiers to act on. What is missing is the acting.
   Somebody who copies a course and launches it *before* the genuine context
   takes the name, and the genuine instructor's launches are denied from then on,
   unbounded in time, with no path that rebinds or retires the squatted row. It
   needs an operator surface (E11's) and a rule about who may rebind, neither of
   which belongs on a launch path, which is why E1-10 recorded it rather than
   built it —
   [ADR 0091](../../adr/0091-what-a-launch-provisions-and-what-it-writes-down-instead.md)'s
   consequences carry the reasoning.
   **Done when** an operator or a sync path can rebind or retire a squatted
   section, proved by a test that provisions a section from one context, drives a
   second context whose label parses to the same identity, and asserts that after
   the repair the second context provisions and the first no longer holds the
   name — a test that fails today whatever an administrator does, because there
   is nothing to call.
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner E11.

5. **`app.services.provisioning._environment()` reads `os.environ` while every
   other reader of the same rules reads `Settings`** (round-3 security re-pass,
   LOW). The address rules are gated on `ENVIRONMENT`, and the two registration
   writers reach it through the configuration `Settings` validated;
   `provision_from_launch` is handed a session and the launch's claims, so it
   reads the variable itself. Two consequences, and only one of them costs
   anything today. The dangerous direction — an unset variable switching the
   rules *off* — is unreachable: `is_a_deployment("")` is true, so an absent value
   puts them in force, which is why this is a LOW rather than a finding to fix in
   the round. The direction that does cost something is the other one: a process
   whose `ENVIRONMENT` lives only in a `.env` file that `Settings` loads and
   `os.environ` does not see would judge a development stack by a deployment's
   rules, and refuse the mock platform's own cleartext roster address on a
   developer's machine.
   That cost materialized before this PR merged, in CI rather than on a
   developer's machine: CI's pytest process has no `.env` and set no
   `ENVIRONMENT`, so the ten in-band course-number tests recorded
   `roster_address_refused` while every local run stayed green off a dotenv
   leak. The test-side fix (the tests now state their environment, and the
   leak is closed) is `docs/MISTAKES.md` entry 40; this done-when is unchanged
   and remains the code-side half.
   **Done when** `provision_from_launch` takes the environment from `Settings` —
   the launch door already holds one on `request.app.state.settings`, so the
   thread is short — and a test drives a launch under a `.env`-only development
   configuration and asserts the mock's address is stored. E1-11 touches this
   module and is the natural place.
   **Fixed by E1-11.** `provision_from_launch(session, claims, settings)` is
   the signature now, `app.api.lti.launch` passes
   `request.app.state.settings`, and `_environment()` and its `os.environ` read
   are deleted — `settings.environment` is the one answer.
   `test_provisioning_reads_its_environment_and_its_day_from_settings.py::test_a_launch_under_a_dotenv_only_development_configuration_stores_the_mocks_address`
   drives a launch with a `.env` in the working directory and `ENVIRONMENT`
   absent from the process, and asserts both halves: the address stored, and no
   `roster_address_refused` recorded.

## From E1-11 — the roster sync service client

1. **The fetched-address rules judge the host literal, not the address it
   resolves to** (security fix round, residual MEDIUM after the HIGH was
   closed). The SSRF fix routes every fetched roster URL — the stored address
   and every `rel="next"` page — through `refuse_invalid_fetched_address`, which
   refuses cleartext off this machine, the mock-platform host, and link-local
   and loopback *literals*. That closes the cloud-metadata case outright
   (`169.254.169.254` is http-only, refused by the cleartext rule and the
   link-local literal both) and, with `requests`' default TLS verification and
   the cleartext rule, the decimal/octal IP spellings (`https://2130706433/`)
   too. The residual: a malicious or compromised registered platform sets
   `rel="next"` to an internal service that holds a **valid public certificate
   on an RFC1918 or split-horizon-DNS address** — it passes every rule, TLS
   verifies, and the tool issues the GET with its NRPS `Authorization: Bearer`
   token attached. Blind (the response is ingested as roster members, not
   returned), and it needs a registered platform to act, which bounds the
   actor. This is the same class as **E1-05 item 2** ("the address rules judge
   spellings, not addresses") and is fixed with it, one level out: at the
   fetched-URL surface rather than the registration-write surface.
   **Done when** the fetched-address path resolves the host and refuses a
   resolved address that is `not ip.is_global` (RFC1918, loopback, link-local,
   carrier-grade NAT), exempting the operator's own stored roster host, and
   connects to the pinned resolved address rather than re-resolving (so a
   rebind between the check and the GET cannot swap it) — with test pairs on
   both sides. Owed with E1-05 item 2, before a second fetched-address writer
   or E11's console ships.
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15, merged with E1-05 item 2; owner E11 at the latest.

## From E1-12 — the dual-door identity merge

1. **`mock-lms-user-dean` is a Pulse-side `user` row the mock LMS cannot sign a
   launch for.** E1-12's seed writes that row so SPEC §7.3's leadership limb is
   demonstrable on the running stack, and
   `test_the_only_users_on_the_mock_platform_are_the_mock_worlds_own` pins it as
   half of the mock world's inventory. But `mock-lms/app/launch.py::resolve_launch`
   refuses a `login_hint` naming no user its own seed holds, and that seed holds a
   learner and an instructor — measured, not assumed. So today the dean's launch
   can be driven from the integration suite, which signs its own launches, and not
   from the mock's launch page. Adding the person to `mock-lms/app/seed.py` is a
   change to that service's own inventories, and the tests that hold them were not
   part of this ticket's red phase.
   **Done when** `mock-lms` seeds a person whose `user_id` is
   `mock-lms-user-dean`, enrolled in at least one context with a roles claim
   carrying no Instructor URN, and a test drives that launch through the tool and
   asserts the section's `lms_context_memberships_url` was stored — the browser
   half of `test_a_leadership_persons_launch_stores_the_roster_address_with_no_instructor_urn`.
   E1-15 owns the browser proof and is the natural place.
   **Fixed by E1-15.** `mock-lms/app/seed.py` seeds the dean, enrolled in
   `MATH-140-E1FF` only with a roles claim carrying no Instructor URN, and the
   launch page pairs each person with only their own sections in the served
   form. The browser half is `tests/e2e/exit-dean-both-doors.spec.ts`: the
   launch lands the leadership view and the stored roster address is witnessed
   through the dev console's sections table.

2. **A web-login linkage can only be provisioned by the demo seed or by hand.**
   `web_login_subject` is read by the door through
   `public.resolve_web_person` and written by nobody: `pulse_app` holds no grant
   of any kind on the table, which is what makes "a web login writes nothing" a
   property of the database. That is the decision
   ([ADR 0097](../../adr/0097-the-identity-a-verified-subject-resolves-to.md)) and
   the ticket puts an admin surface out of scope, so this is not a defect. What it
   costs is worth carrying: a person who joins between demo seeds cannot sign in
   through the web door until somebody connects as the migration identity and
   writes the row, and the psql statement in the ADR is the whole of the
   documented path.
   **Done when** E9's People editor or E11's console can create and remove a
   linkage under the same rule the seed follows — never inferred from a claim —
   with the write behind whatever authorization that surface uses, proved by a
   test that provisions a linkage through it and signs the person in.
   **Carried** to [`../e2/carried-from-e1.md`](../e2/carried-from-e1.md) by E1-15; owner E9's People editor or E11's console, whichever ships first.

3. **The two-hat person's seeded instructor assignment is scoped to a demo
   section, not to the section her launches provision.** `mock-lms` launches her
   into `BIOL-215-R3WW`, which does not exist as a row until somebody launches, so
   the seed cannot scope a grant to it; her `INSTRUCTOR` assignment is scoped to
   `BIOL 101 X1FF` instead. Nothing today reads it — the landing view comes from
   the claim until E1-13 — so the cost is entirely in front of us: once roles come
   from the assignment model, her launch into BIOL 215 resolves to a person whose
   only instructor grant is over a different section, and what she is shown will
   be decided by whatever E1-13 does with that mismatch.
   **Done when** E1-13 has decided what a launch into a section the launching
   person holds no assignment over is shown, and either the seed's scope follows
   that decision or the assignment is dropped as scaffolding, with a test naming
   which.
   **Closed by E1-13, recorded by E1-15.** ADR 0098 resolves the landing from
   door-filtered assignments with no scope condition, so her launch into a
   section she holds no assignment over lands the instructor view her role
   names;
   `test_the_care_who_teaches_reaches_instructor_by_launch_and_care_by_web_login`
   and `tests/e2e/two-hat.spec.ts` name the consequence, and the seed's
   BIOL 101 scope is consistent with a decision that never reads the scope.

## From E1-11's fix round — the mock enforces a token on NRPS

1. **The mock platform's AGS routes still answer without a token.** E1-06 left
   both Advantage services open on one argument — a service refusing before a
   conformant client exists would be refusing this repository's own tests — and
   named E1-11's client as the event that ends it. E1-11 shipped the client for
   the roster, so this fix round closed the NRPS half: the memberships route
   requires a token this platform issued for NRPS 2.0's membership scope
   ([ADR 0099](../../adr/0099-the-mock-enforces-a-token-on-nrps-and-not-on-ags.md)).
   The AGS half is not a defect and not an oversight; the same argument still
   holds there, because no AGS client exists to prove conformance against —
   SPEC §3.4 states the passback rule and SPEC §14.3 gives the work to **E3 —
   Grade passback**. Enforcing now would turn every E0-15 line-item, score and
   result test red for a reason none of them is about (`docs/MISTAKES.md` entry
   22) and would assert nothing about a client.
   **Owner: E3**, which builds the first AGS client. (Several places read "grade
   passback is E2" when this was written; §14.3 is the authority and says E3,
   and the test-side prose was corrected in the same pull request.)
   **Done when** the AGS routes require a token this platform issued carrying
   the AGS scope the call needs, refusing in the same RFC 6750 vocabulary the
   roster uses, landing in the same change as the client that presents one —
   and the AGS-only guard in the suite's mock-platform driver
   (`refuse_an_unspecified_ags_token_flow`) is retired with it, that guard's
   whole premise being that no such client exists.

