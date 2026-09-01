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
**E2-05 asked the standing question of the four tables it adds.**
`question_set` and `question` hold no key to a person and the walk reaches
neither. `response` and `answer` are reached — `response.user_id` is one
hop from `user`, `answer.response_id` is a second — and both are recorded
in the carries-nothing inventory with the columns each judgement was made
against, which took it from five entries to seven. `PERSON_TABLES` is
unchanged: `response.user_id` is a foreign key, and the identity behind it
stays on `user_identity`, which `pulse_app` is granted no `SELECT` on.

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

## The security response headers — closed inside E1; only the E11 residue below is carried

E1's cleanup Batch D (PR #116, ADR 0102) shipped the full set: CSP without
`'unsafe-inline'`, `X-Content-Type-Options`, `Referrer-Policy`, and a
per-document `frame-ancestors` read from the registration table, each pinned
by a test. E2 owes **nothing** on the headers themselves. This entry
originally carried the whole set to E2; the E1 boundary review corrected it
(the same PR that shipped the headers added the residue below but never
updated the top-level claim). Source: `docs/tickets/e1/deferred.md`, E1-04
item 2, which records the closure.

**Residue owed to E11 — source-side origin validation.** The framing emitter
drops a malformed origin (`launcher_origins` validates each
`authorization_endpoint`-derived origin, ADR 0102), so the header is robust
whatever the column holds. But the registration chokepoint still stores an
`authorization_endpoint` carrying a space, `;`, `,` or `*` verbatim, and E11's
dynamic registration takes that endpoint from an untrusted party — so E11 owes
a write-time rejection of a CSP-breaking `authorization_endpoint` at the
chokepoint. Source: `docs/tickets/e1/deferred.md`, E1-04 item 2 residue.
**Owner:** E11. **Done when:** the deferred entry's.

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
browser side is already pointed at the route too — `tests/e2e/support/doors.ts`
fetches `/mock/defects` — so the spec literals are checked against the served
source today, not deferred to E2 (the E1 boundary review corrected this
line, which predated that fetch).

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

## A leadership assignment anywhere is an unscoped roster-ingestion trigger

From the E1 boundary review (threat-model, verified;
`docs/tickets/e1/boundary-review.md` M9). §7.3's leadership limb admits any
holder of a live leadership assignment as a staff-launch trigger with no
reference to the launch's context: a Lead Faculty enrolled as a Learner in a
sibling lead's course can launch from it, and Pulse binds that section,
stores its roster address permanently, and pulls the full membership —
including the squat hazard on the `(course, term, section_code)` name
(`docs/tickets/e1/deferred.md`, E1-10 item 4, reachable here by a much wider
actor set than that entry describes). Verified character: write/ingest
integrity, not a read leak — the roster is never disclosed to the trigger,
and the INSTRUCTOR row goes to the section's real teacher. The fix is a
purview condition on storing the discovered address, but it needs a design
answer first: a dean's legitimate first launch into a brand-new course no
purview yet covers must keep working.
**Owner:** E2. **Deadline (Todd's ruling, 2026-08-28):** fixed before any
surface renders roster-derived data — the same shape as E4's reveal-guard
deadline.
**Done when:** a staff launch stores a roster address only for a section
within the launcher's resolved purview (with the first-launch case settled
and recorded), a launch outside it records a defect row rather than binding,
and a two-directional test pair pins both sides.

## The `views_sql` package exemption and the import guard disagree on their object

From the post-merge re-review (threat-model; consolidated comment on PR
#123, finding 3). The org-view SQL sweep excuses any module under
`backend/app/views_sql/` by containment, while the one-importer sweep pins
the literal name `app.views_sql.queries` — so a second module added to the
package, holding a raw org read and imported from an API handler, passes
both halves of the M8 closure in two individually legal steps (reproduced
with a planted module during the re-review). ADR 0107's stated reason for
leaving the package unpinned ("the one-importer sweep guards `views_sql`
separately") describes a guard that watches one module name, not the
package.
**Owner:** E2. **Deadline (Todd's ruling, 2026-08-31):** fixed before any
second module lands under `backend/app/views_sql/` and before E2's first
read path behind the sweep, whichever comes first.
**Done when:** the exemption and the import guard name the same object —
either the exemption narrows to the module the import guard watches, or the
import guard widens to the package — proven by the re-review's two-step
planted offender going red, and ADR 0107's sentence corrected.

## Low findings and record notes from the post-merge re-review

From the consolidated re-review comment on PR #123 (findings 6–12 there,
each with file-and-line evidence). Carried as a block; the re-review judged
none reachable today.

- The exempt files' statement pin compares relation names, not statements,
  and the test docstring claims otherwise; ADR 0107 describes the pin
  honestly, so the two records disagree. The count-only-plant docstring in
  the same file also claims a location assertion the assertion doesn't make.
  **Owner:** whichever E2 ticket next touches the org sweep. Done when the
  pin matches its docstring or the docstrings match the pin.
- The `DESC` on `ix_nrps_call_section_id_called_at_desc` serves no query in
  the tree, and it is exactly what makes the declaration invisible to
  `alembic check`; a plain ascending composite would perform identically
  and be comparable. **Owner:** E2's roster work, alongside M9. Done when
  the index is comparable or the `DESC` has a reader.
- `tests/integration/test_the_section_binding_survives_a_downgrade.py`
  cites `e2c94b6a1f70` as a preserve/restore precedent that the boundary
  record corrections in the same merge struck as false. **Owner:** E2,
  with the migration-message bullet below — same file family, one ticket.
  Done when the docstring names no precedent the record has struck.
- Downgrade below `b8c41f7d2e05`, delete the registration, upgrade back:
  the restore hands the foreign key a dead deployment and the operator gets
  a raw constraint violation instead of the migration's usual actionable
  refusal. Fail-closed — the transaction rolls back and the preserved rows
  survive for a retry. **Owner:** E2. Done when that path refuses with a
  sentence naming the preserved table.
- The stored roster host joins `unpinned_hosts` in every environment while
  the docstring beside it calls that entry development-only. **Owner:**
  E2's roster work, alongside M9, which owns the sync's transport. Done
  when the entry is environment-narrowed or the docstring states what the
  code does.
- The roster walk's cycle/page-cap terminator is the one exit that discards
  members it already read; every other failure exit keeps the prefix with
  `complete=False`. A platform that advertises `next` on a full final page
  starves that section's roster forever, with 200s in `nrps_call` and only
  an ERROR line as signal. **Owner:** E2's roster work, alongside M9. Done
  when that branch returns the prefix incomplete like its siblings.
- Record notes: `backend/app/services/authz.py` still says the sweep
  polices "the three org views" (it is fourteen relations now); and E1 has
  no generative purview coverage — §4.1 item 2 is proven on hand-built
  fixtures only, which stands while the union computation is E9's (E9
  already owns the Hypothesis purview properties, listed below).
  **Owner:** E2 for the comment correction, done when the comment stops
  asserting a count and points at the catalog the sweep reads (amended at
  the E2 breakdown: this entry first said "counts what the sweep polices",
  and a written count re-creates the drift the fix exists to end); the
  purview note is E9's already and carries no work here.
- The denial-module closure sweep's inventory is a naming convention
  (`DENIAL_NAME_SHAPES` in
  `tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`),
  with two disclosed limits, stated precisely because the first draft of
  this bullet got them wrong: a §4.1 denial module named outside every
  shape escapes the sweep (the singular `_name_nobody` spelling nearly
  escaped exactly this way; PR #130's review caught it), and deleting a
  shape **together with its planted sample in the same change** is green
  in both tests while the modules that shape demanded are demanded by
  nothing. A shape deleted *alone* is red on the demanded-set equality —
  that half is covered. The paired deletion is the one a future editor
  could do by accident while tidying. **Owner:** E2's breakdown. Done when
  the sweep's inventory has a source the naming convention cannot shrink,
  or the E2 boundary review re-affirms both disclosed limits in writing.

## Owned by the spec already

Listed so this file is a complete boundary record; each is §14.3's or a
standing ADR's, not re-owned here: transitive purview, the
resolve-only-your-own-subject rule, and the Hypothesis purview properties
(E9, per `carried-from-e0.md`'s three entries); §4.1 item 1's assertion and
the copy-inventory test (E2); `PlatformProfile` adapters (E3);
supervision-graph and Lead-Faculty-mapping editing (E9); notifications
(E12); term-map edits re-deriving section calendars (ruled E11, 2026-08-31,
at the E2 breakdown; ADR 0018 and ADR 0021); real-LMS certification (post-v1, §14.4).
