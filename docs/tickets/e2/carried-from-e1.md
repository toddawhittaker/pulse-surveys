# Carried from E1 into E2

Things E1 decided or deferred that later work has to know, per SPEC §14.1:
one entry per thing, each with an owner and what it looks like to be
finished. This is a hand-off note, not a ticket; the next breakdown schedules
the work, and an entry here is what that breakdown has to have read first.
Created by E1-15. Entries point at the record that owns the detail rather
than restating it — the "done when" in the source file governs where one
exists.

Items SPEC §14.3 already assigns to a named epic are listed at the end
rather than re-owned here. An entry whose owner is not E2 is carried through
this file anyway, because §14.1 routes every deferral through the epic
boundary and a later epic's breakdown reads this file's successors.

## The §4.1 catalog sweep misses the whole-row join form

**Fixed inside E1 after all**, by the cleanup Batch A PR
(`e1/sweep-closures`): the catalog half now reads `pg_get_viewdef` as well
as `pg_depend` and flags the join-hidden whole-row form, proved by the
planted hidden-case control and a live-view battery mutation. The deferred
entry (`docs/tickets/e1/deferred.md`, E1-01 item 1) carries the detail;
nothing is owed to E2.

## `PERSON_TABLES` has no structural source, and the name-sweep passes over tables it cannot read

One half of E1-01 item 2 was fixed inside E1 by the cleanup Batch A PR
(`e1/sweep-closures`): the sweep now reports a reached table it can
classify by nothing, with each carries-nothing exemption pinned to the
exact column set its reason was written against, so an added column
expires the entry. The report classifies per table, not per column: a
first unrecognizable column on a table that already carries a recognized
one is still the per-epic review's question, as the function's docstring
states.
The other half — a structural source for the `PERSON_TABLES` roots — was
attempted there and failed honestly (the grant-derived set over-reports
five-fold; marker- and model-derived sources are circular), so it stays
carried with the attempt recorded in the deferred entry. Residual blind
spot: a person table with no foreign-key path into the graph is invisible
to both the walk and the report. Source: `docs/tickets/e1/deferred.md`,
E1-01 item 2.
**Owner:** every epic's review asks the question for tables it adds
(standing); the structural source is E13's at the latest (ruled
2026-08-28), with the reached-table report as its compensating control.
**Done when:** the deferred entry's, for the half still open.

## A non-development deployment has no way to supply the tool's signing key

Custody is a database row only the development seed writes (ADR 0082); a
deployment holding no row answers 503 at `/lti/jwks`, loudly. Rotation is
unanswered too — the one-row rule forbids the two-key overlap a real
rotation needs. Source: `docs/tickets/e1/deferred.md`, E1-05 item 1.
**Owner:** E3, the first epic to register a real platform.
**Done when:** the deferred entry's.

## The address rules judge spellings, not resolved addresses — fixed inside E1

One defect recorded at two surfaces (E1-05 item 2 and E1-11 item 1, the
residual MEDIUM), and E1's cleanup batch closed both rather than handing
them on: the address rules resolve the host and refuse every returned
address that is not globally routable, and the roster walk connects to the
address it judged. E2 inherits nothing to do here. Two things to know
instead: **private ranges are refused now**, which reverses ADR 0081 and is
recorded in
[ADR 0101](../../adr/0101-a-fetched-address-is-judged-by-what-it-resolves-to.md);
and the sync's token request and the launch's key-set fetch are judged when
the registration is written and never at fetch time, so neither is pinned —
residue that record states. Source: both entries in `docs/tickets/e1/deferred.md`, each
carrying what landed and where.

## Nothing makes a future `lti_platform` writer call the address rules — fixed inside E1

Also closed by E1's cleanup batch (E1-05 item 3): `before_insert` and
`before_update` events on `LtiPlatform` judge every ORM write, reading the
environment from `Session.info["environment"]` and judging a session that
states none as a deployment. Two things a later epic — E11's registration
console above all — has to know about what is left. **A writer that states
no environment on its session is refused in a deployment's terms**, so a new
one says where it is where the session is built. And **the events do not see
every write the ORM can make**: `session.add`, an edit to a persistent row
and `session.merge` are judged, while `Session.bulk_save_objects`, an
ORM-enabled `session.execute(update(LtiPlatform).values(...))`, a Core
`insert()` and raw SQL are not — measured on SQLAlchemy 2.0.52, and the
bulk-`UPDATE` shape is a natural way to write a console's save. `pulse_app`
holds `SELECT` on the table and nothing else, so a bypassing write on the
application connection is refused by the database. Recorded residue in ADR
0081 and ADR 0101. Source: `docs/tickets/e1/deferred.md`, E1-05 item 3.

## The TypeScript 7 pair waits on typescript-eslint

No released `typescript-eslint` accepts TypeScript 7; nothing was pinned or
forced. Source: `docs/tickets/e1/deferred.md`, E1-03 item 1, and
`docs/tickets/deps-triage-2026-08-24.md` entry 3.
**Owner:** whichever epic is running when `npm view typescript-eslint
peerDependencies` admits 7.x.
**Done when:** triage entry 3's.

## The three webfonts are declared and not loaded

The five landing views render in fallback faces; self-hosting versus
shipping fallbacks is decided against E2's first real screen. Source:
`docs/tickets/e1/deferred.md`, E1-04 item 1.
**Owner:** E2. **Done when:** the deferred entry's.

## The application sends no security response headers

No CSP, no `X-Content-Type-Options`, no referrer or framing policy — and
the framing policy has to admit the LMS iframe, so it is designed, not
copied. Source: `docs/tickets/e1/deferred.md`, E1-04 item 2.
**Owner:** E2, before real survey content reaches the SPA.
**Done when:** the deferred entry's.

## The mock IdP's key-set spelling is unpinned

The unpadded-base64url pin covers the tool's and the mock LMS's key sets;
the mock IdP's encoder is the third copy and nothing asserts its spelling.
Source: `docs/tickets/e1/deferred.md`, E1-06 item 3.
**Owner:** whichever ticket next touches `mock-idp/app/signing.py`.
**Done when:** the deferred entry's.
**Closed by E1 cleanup Batch B (item 4):** the third encoder now has the
spelling test, proven against the `.rstrip(b"=")` mutation by the battery;
the encoder was already correct, so no code changed. Nothing for E2 to do.

## The wrong-launch selector vocabulary has no served source

`ALL_SELECTORS` cannot be imported outside `mock-lms/`, so the integration
suite and E1-15's browser spec each hold copied literals (a stale one fails
loudly — the dispatcher 400s, and the spec's refusal-page assertion then
fails). Source: `docs/tickets/e1/deferred.md`, E1-07 item 1; the second
consumer is `tests/e2e/exit-refused-launches.spec.ts`.
**Owner:** the next ticket that adds a selector or a consumer.
**Done when:** the deferred entry's — one served source, proven to agree
with `ALL_SELECTORS`.
**Closed by E1 cleanup Batch B (item 3):** the mock serves `ALL_SELECTORS`
from `GET /mock/defects`, and both integration copies (the wrong-launches
suite's and the launch-door module's) now check themselves against it. The
`exit-refused-launches.spec.ts` literals stay the spec's own until E2 points
the browser at the route; the served source they were owed is in place.

## The launch door's algorithm pin has no end-to-end forgery proof — resolved inside E1

E1's cleanup Batch B settled this rather than carrying it: the end-to-end
proof is impossible, because `pylti1p3` matches a key by `kid` and `alg` and
verifies against the PEM export of that matched key, while the mock's
`hs256_confusion` mint keys its HMAC with the canonical JWK JSON and ADR 0035
bars the mock from producing a PEM to forge against — so `jwcrypto` cannot
PEM-export the symmetric key the confusion would need, and an RSA key's PEM is
not what the mock signed with. `_refuse_unpinned_algorithm` is therefore a
confirmed redundant defence-in-depth guard whose removal does not turn the
launch green, and the confusion launch's end-to-end refusal is already
asserted by an existing parametrised test. E2 inherits nothing to do here.
Source: `docs/tickets/e1/deferred.md`, E1-08 item 1 (the full reasoning is
there).

## A squatted section binding is never reconciled or aged out

First-writer-wins on `(course, term, lms_section_code)` is deliberate and
loud, but a context that squats a name before the genuine one launches
holds it forever; repair needs an operator surface and a rebind rule.
Recorded as a MEDIUM by E1-10's re-pass. Source:
`docs/tickets/e1/deferred.md`, E1-10 item 4, and ADR 0091.
**Owner:** E11. **Done when:** the deferred entry's.

## A web-login linkage can only be provisioned by the demo seed or by hand

`web_login_subject` is written by nobody (`pulse_app` holds no grant), so a
person who joins between seeds cannot use the web door until somebody runs
the psql in ADR 0097. Source: `docs/tickets/e1/deferred.md`, E1-12 item 2.
**Owner:** E9's People editor or E11's console, whichever ships first.
**Done when:** the deferred entry's.

## AGS still answers without a token

E1's fix round enforced the client-credentials token on NRPS only; the AGS
containers keep signature-level bounds and no credential check, because no
AGS client exists to build against. ADR 0099 records the decision and the
boundary. Source: `docs/tickets/e1/deferred.md`, "From the E1-11 fix round".
**Owner:** E3, paired with the first AGS client.
**Done when:** ADR 0099's consequences — enforcement lands with that
client, the way NRPS's landed with E1-11's.

## Logout and back-channel logout

No epic in §14.3 names logout; E1's sessions are short-lived JWTs that
expire rather than end. Raised at the E1 breakdown (PR #89) and still
unowned at E1 exit, which is the condition E1-09 set for carrying it here.
**Owner:** E9 (ruled 2026-08-28) — beside the role switcher and the admin
surfaces, whose web-door roles are the people who need a session to end
before its hour expires; E9 lands before the Care queue (E10) ships.
**Done when:** E9's breakdown schedules it and it is built there.

## Local-account fallback for web login

SPEC §7.1 names it as a pilot fallback; nothing in E1..E13 schedules it.
Raised at the breakdown (PR #89).
**Owner:** E13 (ruled 2026-08-28) — it is release-readiness insurance
against the pilot IdP falling through, and E13 is where that risk is either
real or expired.
**Done when:** E13 either schedules and builds it, or deletes the §7.1
sentence because the risk expired.

## Deep Linking

E0-14 deferred it out of the mock and no epic names it. Ruled 2026-08-28:
post-v1, and §7.3 now says so rather than promising it — unless a real
platform demands the flow before then, in which case it is E3's.
**Owner:** post-v1 (§14.4); E3 only if a real platform forces it earlier.
**Done when:** done — §7.3 was edited with the ruling (E1's cleanup Batch C
PR); nothing further is owed unless a platform demands the flow.

## The mock's scope check is only provably a membership check while no advertised scope is a superstring

E1's battery left one recorded survivor: a scope check by substring is
indistinguishable from membership because the token endpoint refuses
unadvertised scopes and no advertised scope contains the membership scope
as a substring. Recorded in PR #109.
**Owner:** whichever ticket widens the mock's `ADVERTISED_SCOPES`.
**Done when:** if a new scope is a superstring of another, a pair proves
the check is membership, not substring.

## The reveal-subject guard, restated

The reveal's actor check and an instructor's read scope compose: a two-hat
actor can today reach `reveal_identity` with a `user_id` taken off her own
roster view. Nothing E1 shipped renders roster rows, so the path stays
unreachable. The full entry, with the composing facts and the done-when, is
`docs/tickets/e1/carried-from-e0.md` ("The reveal's actor check and an
instructor's read scope compose") — kept there, pointed at from here.
**Owner:** E4, whose §14.3 entry binds the deadline: before any
instructor-facing surface renders roster-derived rows.
**Done when:** the carried-from-e0 entry's.

## Owned by the spec already

Listed so this file is a complete boundary record; each is §14.3's or a
standing ADR's, not re-owned here: transitive purview, the
resolve-only-your-own-subject rule, and the Hypothesis purview properties
(E9, per `carried-from-e0.md`'s three entries); §4.1 item 1's assertion and
the copy-inventory test (E2); `PlatformProfile` adapters (E3);
supervision-graph and Lead-Faculty-mapping editing (E9); notifications
(E12); term-map edits re-deriving section calendars (E2 or E11, ADR 0018
and ADR 0021); real-LMS certification (post-v1, §14.4).
