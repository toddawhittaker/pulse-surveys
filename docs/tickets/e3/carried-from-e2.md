# Carried from E2 into E3

Things E2 decided or deferred that later work has to know, per SPEC §14.1: one
entry per thing, each with an owner and what it looks like to be finished. This
is a hand-off note, not a ticket; the next breakdown schedules the work, and an
entry here is what that breakdown has to have read first. Created by E2-13.
Entries point at the record that owns the detail rather than restating it — the
"done when" in the source file governs where one exists, and where none exists
the entry carries the detail itself.

Items SPEC §14.3 already assigns to a named epic are listed at the end rather
than re-owned here. An entry whose owner is not E3 is carried through this file
anyway, because §14.1 routes every deferral through the epic boundary and a
later epic's breakdown reads this file's successors, not E1's or E2's.

The completeness rule this file was written to: **every entry of
`../e2/carried-from-e1.md` not closed inside E2, plus every entry of
`../e2/deferred.md` still open after E2-13's cleanup pass, appears here.** The
first group is listed first and the second after it. Nothing was dropped
silently; an entry E2 closed is named in its own source file with what closed
it.

## `PERSON_TABLES` has no structural source, and the name-sweep passes over tables it cannot read

The reached-table report landed in E1 and the structural source for the
`PERSON_TABLES` roots did not — the grant-derived set over-reports five-fold and
marker- and model-derived sources are circular. Residual blind spot: a person
table with no foreign-key path into the graph is invisible to both the walk and
the report. Source: `docs/tickets/e1/deferred.md`, E1-01 item 2, carried through
`../e2/carried-from-e1.md`.
**Owner:** every epic's review asks the standing question of the tables it adds;
the structural source is E13's at the latest (ruled 2026-08-28).
**Done when:** the deferred entry's, for the half still open.
**E2 asked the standing question of the four tables it added** (E2-05):
`question_set` and `question` hold no key to a person and the walk reaches
neither; `response` and `answer` are reached and both are recorded in the
carries-nothing inventory with the columns each judgement was made against.
`PERSON_TABLES` is unchanged. E3 asks the same question of whatever it adds.

## A non-development deployment has no way to supply the tool's signing key

Custody is a database row only the development seed writes (ADR 0082); a
deployment holding no row answers 503 at `/lti/jwks`, loudly. Rotation is
unanswered too — the one-row rule forbids the two-key overlap a real rotation
needs. Source: `docs/tickets/e1/deferred.md`, E1-05 item 1.
**Owner:** E3, the first epic to register a real platform.
**Done when:** the deferred entry's.

**Closed by E3-01.** The done-when asked for "a documented and tested way to put
a signing key in that table — with the rotation question answered too", and both
halves shipped in one pull request.

The supply path is `scripts/signing_key.py`, an operator command with `generate`,
`list` and `retire <kid>`, connecting on `DATABASE_URL` for the address and
`DB_SUPERUSER`/`DB_SUPERUSER_PASSWORD` for the identity — the same three
variables a migration reads, so no configuration variable was added, and the
application role still holds `SELECT` on the table and no write of any kind
([ADR 0126](../../adr/0126-a-signing-key-reaches-a-deployment-through-an-operator-command.md)).
It is driven as a program against migrated databases the demo seed has never run
against, which is the half of the entry that mattered: a path proven only where
the seed works is proven in the one place it is not needed.

The rotation question is answered by
[ADR 0127](../../adr/0127-the-published-key-set-carries-every-unretired-key-and-the-newest-signs.md).
`uq_tool_signing_key_one_row` is dropped and two columns replace it: the
published key set at `/lti/jwks` is every row with `retired_at IS NULL`, and the
tool signs with the newest of those by `created_at DESC, id DESC`. A rotation is
`generate`, a wait long enough for platforms to re-fetch the key set, then
`retire` on the old key — and both keys verify in between. A retired key leaves
the set immediately and its row stays as the record of what this deployment used
to sign with. A deployment with no *live* key still answers 503, in a sentence
that now names the command that fixes it.

Three limits stated rather than left to be discovered. Nothing expires a key or
bounds how many the published set carries: `retire` is a command somebody has to
run, and `list` exists so the state a rotation is halfway through is visible. The
migration's downgrade **refuses** when it meets more than one *live* key, because
below that revision the table permits one row and completing would have to choose
which identity survives — the one discarded being the private half of a key a
platform may already have been registered against; retirement is the route down,
which is why the guard counts live rows rather than stored ones. And a downgrade
that does complete **discards the retired-key records**, which the one-row schema
has nowhere to hold: no identity anything still verifies against is lost, but the
record of what this deployment used to sign with is, and only a backup has it
afterwards. ADR 0127 carries all three.

## AGS still answers without a token

E1's fix round enforced the client-credentials token on NRPS only; the AGS
containers keep signature-level bounds and no credential check, because no AGS
client exists to build against. ADR 0099 records the decision and the boundary.
Source: `docs/tickets/e1/deferred.md`, "From the E1-11 fix round".
**Owner:** E3, paired with the first AGS client.
**Done when:** ADR 0099's consequences — enforcement lands with that client, the
way NRPS's landed with E1-11's.

**Closed by E3-04.** The done-when asked for enforcement to land with the client
rather than after it, and both halves shipped in one pull request: the client is
`backend/app/lti/ags.py` and the six AGS routes require a token in the same
change.

Each route names the scopes AGS 2.0 defines for it — the create takes the
line-item scope, the two line-item reads take that or its read-only sibling, the
score post takes the score scope, and both result reads take the result read-only
scope ([ADR 0134](../../adr/0134-the-mocks-ags-routes-map-to-scopes-one-per-route.md)).
The credential is judged before the query parameters and before the context
lookup, which is the roster route's order copied, so both containers' `ge=1` page
bounds came out of the route signatures and are read by `app.paging::page_number`
behind the credential — the consequence ADR 0099 wrote down when the roster's own
bound moved, arriving in the ticket that record named. The `/mock/` prefix stays
tokenless by decision (ADR 0047), with a test that says so, so an enforcement
applied to the application rather than to the routes is caught rather than
shipped.

## The registration chokepoint stores a CSP-breaking authorization endpoint verbatim

E1 shipped the security response headers in full; the residue is on the write
side. The framing emitter drops a malformed origin, so the header is robust
whatever the column holds, but the chokepoint still stores an
`authorization_endpoint` carrying a space, `;`, `,` or `*` as given — and a
dynamic registration takes that endpoint from an untrusted party. Source:
`docs/tickets/e1/deferred.md`, E1-04 item 2 residue.
**Owner:** E11, whose dynamic registration is the untrusted writer.
**Done when:** the deferred entry's.

## A squatted section binding is never reconciled or aged out

First-writer-wins on `(course, term, lms_section_code)` is deliberate and loud,
but a context that squats a name before the genuine one launches holds it
forever; repair needs an operator surface and a rebind rule. Source:
`docs/tickets/e1/deferred.md`, E1-10 item 4, and ADR 0091.
**Owner:** E11. **Done when:** the deferred entry's.

## A web-login linkage can only be provisioned by the demo seed or by hand

`web_login_subject` is written by nobody the application role can reach, so a
person who joins between seeds cannot use the web door until the psql in ADR
0097 is run by hand. Source: `docs/tickets/e1/deferred.md`, E1-12 item 2.
**Owner:** E9's People editor or E11's console, whichever ships first.
**Done when:** the deferred entry's.

## Logout and back-channel logout

No epic in SPEC §14.3 names logout; sessions are short-lived JWTs that expire
rather than end.
**Owner:** E9 (ruled 2026-08-28) — beside the role switcher and the admin
surfaces, whose web-door roles are the people who need a session to end before
its hour expires.
**Done when:** E9's breakdown schedules it and it is built there.

## Local-account fallback for web login

SPEC §7.1 names it as a pilot fallback; nothing in E1 through E13 schedules it.
**Owner:** E13 (ruled 2026-08-28) — release-readiness insurance against the pilot
identity provider falling through.
**Done when:** E13 either schedules and builds it, or deletes the §7.1 sentence
because the risk expired.

## The TypeScript 7 pair waits on typescript-eslint

`typescript-eslint` has to accept TypeScript 7 before the pair can move, and
nothing is pinned or forced meanwhile. Source: `docs/tickets/e1/deferred.md`,
E1-03 item 1, and `docs/tickets/deps-triage-2026-08-24.md` entry 3.
**Checked at the E2 boundary on 2026-09-03: 7.x was not admitted during E2.**
The latest published `typescript-eslint` is 8.69.0 and it declares
`typescript >=4.8.4 <6.1.0`; the pinned 8.68.0 declares the same range, and
`typescript` is pinned at 6.0.3. So the wait continues and this is a re-carry
with a dated fact rather than a silent one.
**Owner:** whichever epic is running when `npm view typescript-eslint
peerDependencies` admits 7.x.
**Done when:** triage entry 3's.

## The mock's scope check is only provably a membership check while no advertised scope is a superstring

E1's battery left one recorded survivor: a scope check by substring is
indistinguishable from a membership check because the token endpoint refuses
unadvertised scopes and no advertised scope contains the membership scope as a
substring. Recorded in PR #109.
**Owner:** whichever ticket widens the mock's `ADVERTISED_SCOPES`.
**Done when:** if a new scope is a superstring of another, a pair proves the
check is membership rather than substring.

**Closed by E3-04.** No scope was added; the pair became expressible because a
second service started enforcing. `…/scope/lineitem.readonly` was already
advertised and already contains `…/scope/lineitem` as a prefix, and until AGS
required a credential there was no route on which the two could be told apart.

Both halves are asserted on the route that creates a gradebook column: a token
granted only the read-only line-item scope is refused 403 `insufficient_scope`
there, and a token granted the writing scope creates a line item the container
then lists. The refused half alone would be satisfied by a route that refuses
every credential, which is why the accepted half is asserted past the 201 and
against the container's own contents. `app.tokens::authorised_token` compares
membership of RFC 6749 §3.3's space-delimited list, so the substring, prefix and
`startswith` implementations each die against the first half while passing every
other test in the module.

## The reveal-subject guard, restated

The reveal's actor check and an instructor's read scope compose: a two-hat actor
can reach `reveal_identity` with a `user_id` taken off her own roster view.
Nothing shipped through E2 renders roster rows to an instructor, so the path
stays unreachable. The full entry, with the composing facts and the done-when,
is `docs/tickets/e1/carried-from-e0.md` ("The reveal's actor check and an
instructor's read scope compose").
**Owner:** E4, whose §14.3 entry binds the deadline: before any
instructor-facing surface renders roster-derived rows.
**Done when:** the carried-from-e0 entry's.

## Two registration-write blind spots a console has to know about

Both were recorded rather than closed when E1 fixed the address rules, and both
are facts about writing `lti_platform` rather than work anybody owes today.
**Fetch-time addresses are not pinned:** a registration's addresses are judged
when the registration is written and never at fetch time, so the roster sync's
token request and the launch's key-set fetch are not re-judged. **The ORM events
do not see every write:** `session.add`, an edit to a persistent row and
`session.merge` are judged, while `Session.bulk_save_objects`, an ORM-enabled
`session.execute(update(...))`, a Core `insert()` and raw SQL are not — and the
bulk-`UPDATE` shape is a natural way to write a console's save. The application
role holds `SELECT` on the table and nothing else, so a bypassing write on that
connection is refused by the database. Recorded residue in ADR 0081 and ADR
0101; source `docs/tickets/e1/deferred.md`, E1-05 items 2 and 3.
**Owner:** to-know for E11's registration console, which is the first surface
that writes the table from outside the seed.
**Done when:** nothing here is owed as work; the entry exists so a console is
built against what the events actually cover, and it closes when a console
either states that it uses only the judged write shapes or extends the judging
to the ones it needs.

## The E1 generative purview coverage note

SPEC §4.1 item 2 is proven on hand-built fixtures only; there is no generative
coverage of the purview union. That stands while the union computation is E9's,
and E9 already owns the Hypothesis purview properties. Source:
`../e2/carried-from-e1.md`, the record notes in the re-review block.
**Owner:** E9, with the properties it already owns.
**Done when:** E9's, and no work is owed before it.

## The denial-module closure sweep's inventory is a naming convention

`DENIAL_NAME_SHAPES` is the sweep's whole inventory, with two disclosed limits: a
§4.1 denial module named outside every shape escapes the sweep, and deleting a
shape together with its planted sample in the same change is green in both tests
while the modules that shape demanded are demanded by nothing. A shape deleted
alone is red on the demanded-set equality.
**Owner and done-when: settled at the E2 breakdown** — the entry's own second
branch, the E2 boundary review re-affirming both disclosed limits in writing,
which `../e2/boundary-review.md` carries. It is listed here because a reader of
this file should not have to go back to E1's to find out what happened to it.
**Carried only if that re-affirmation reports the limits no longer hold**, in
which case the boundary record says so and names what replaces them.

## A bounced submission's verdict rows are unbounded per attempt

Ruled 2026-09-03: the rows are bounded by a cap on the attempts a window will
classify, and linkage is rejected in ADR 0055's direction. Two halves are left,
and the entry stays open for both. Source: `../e2/deferred.md`.
**Owner:** the cap's value and the copy a capped student sees belong to the
ticket that implements it, scheduled in a later breakdown; the aggregation half
is E11's, with §6.1's drift panel.
**Done when:** the deferred entry's — the cap ships, and the drift surface
either excludes these rows or bounds them, naming that entry where it does.

## Nothing structurally forces the next mutating route onto the CSRF dependency

`require_student` and `csrf_verified_student` sit beside each other and nothing
makes a writing route reach for the checked one, so the next mutating route is
one import away from being unprotected in the way that reads as fine in review.
The submit path itself is correct. Source: `../e2/deferred.md`.
**Owner:** a candidate E3 ticket — E3 posts grades, which is the next epic
likely to add a mutating route.
**Done when:** the deferred entry's — a sweep over the built application's
routes, asserted in both directions so a stale exemption fails as loudly as an
unguarded route.

## The launch-path roster enqueue still waits six seconds on a broker that is down

`request_section_sync` publishes on an unbounded connection, so a staff launch
whose Redis is restarting holds the request for six seconds after the launch is
already verified and committed. The bounded shape exists next to it in
`enqueue_reclassification` and was measured at 0.037s against the same closed
port. Source: `../e2/deferred.md`.
**Owner:** unowned — a candidate ticket for whichever epic next touches the
launch door's suites, which should move with it.
**Done when:** the deferred entry's — the bounded connection, and a test that
times a staff launch against a broker at a closed port under a stated budget.

**Closed by E3-05.** Both halves of the done-when landed in the ticket that added
a second enqueue to the same door.

`request_section_sync` publishes through `app.jobs.celery_app.publish_once`,
which is where the bounded shape now lives: one attempt, a connection made for
the call with `max_retries: 0` and its socket timeouts bounded, and no result
backend. The constants moved out of `app.services.validity` rather than being
copied, so the three request paths that enqueue — the submit path's
re-classification, the launch door's roster sync and the launch door's line-item
creation — cannot come apart (`docs/MISTAKES.md` entry 13). Each caller keeps its
own broad `except`, its own error log and its own answer, because what to do
about a broker that is not there is a different question per caller.

The measurement is
`tests/integration/test_a_staff_launch_is_prompt_with_the_broker_at_a_closed_port.py`:
a real instructor launch with the broker at a closed loopback port, under SPEC
§10's 2.5-second budget, asserting *both* error-level refusals — one under
`app.services.roster_sync` and one under `app.services.grading` — so that a door
which published nothing cannot satisfy the budget by being fast. The section it
drives is required to hold both service addresses, to carry no line-item id and
to have no `nrps_call` row at all, so neither trigger can be correctly silent and
the roster debounce cannot fire (`docs/MISTAKES.md` entry 7).

## The unproven structural battery rows

Recorded so the residue is findable rather than to schedule work: E2-05's
battery proved the security-relevant schema rules by migration-side mutation and
recorded the rest by mechanism class, since model-side mutation is inert when
the test database builds from the migration. Source: `../e2/deferred.md`.
**Owner:** nobody; it is a note to a later battery.
**Done when:** nothing. A later battery over those tables mutates the migration
rather than the model.

## The bounce names no offending position, so the form coaches every comment it sent

A submission can carry two comments and the 422 names neither, so the form
attaches the coaching to every comment field the submission carried. Correct and
precise for one comment; correct and imprecise for two. Source:
`../e2/deferred.md`.
**Owner:** a candidate heavy-lane ticket — the change is on the write path and in
the route's detail, so it is not the form's alone.
**Done when:** the deferred entry's, including the test that sends two comments
and requires the untouched one to carry no coaching.

## The week eyebrow cannot say how long the course runs

`OpenSurvey` carries the week under both names and when the window shuts, and
nothing that says how many weeks the section runs for; deriving it in the
frontend would be a second copy of the start-letter map in TypeScript. Source:
`../e2/deferred.md`.
**Owner:** a candidate heavy-lane ticket — one field on a schema and one read in
the survey read service.
**Done when:** the deferred entry's.

## The self-hosted faces: an unrecognized licence, a missing notice, and a second copy nobody fetches

The three font packages declare the SIL Open Font License, which the licence
gate's rule table does not name, so all three classify as unknown and would fail
the build the day that gate is run strictly; the licence asks for its text and
copyright notices to travel with the files and the build ships neither; and each
package's stylesheet lists woff beside woff2, so 147,028 bytes no supported
browser fetches ship in the image. Source: `../e2/deferred.md`, and ADR 0116.
**Owner:** E13's accessibility and licence pass for the first two; the woff
duplicates ride with them.
**Done when:** the deferred entry's, including the near-miss control on the new
licence rule.

## A resubmission under a rewound development clock answers 500

The development clock is an offset rather than a freeze, so setting the same
pretended minute twice produces an effective now slightly earlier than the first
setting had drifted to, and a resubmission then writes a row the response
table's ordering check refuses — surfacing as a 500 where a refusal belongs. No
deployment reaches it: real time does not run backwards and the override is
refused outside development. Source: `../e2/deferred.md`.
**Owner:** a candidate heavy-lane ticket — the fix is on the submit path.
**Done when:** the deferred entry's — the path refuses in words or refuses to
move the timestamp backwards, and a test drives it and requires something other
than a 500.

## The model identifier lives in three places and nothing ties them

The identifier is named in `.env.example`, in the workflow's eval step and in
the floor declaration's provenance sentences, and no test compares any of the
three; re-pointing either configuration site alone survives the whole suite. The
move to an aliased model sharpened this: the alias can be re-pointed by the
provider with nobody editing anything, so a fourth thing — the weights — can now
disagree with the three written sites, and no test can read it. Source:
`../e2/deferred.md`, and ADR 0120.
**Owner:** a candidate ticket, and whichever epic next changes the model or the
prompt inherits the urgency.
**Done when:** the deferred entry's — one test reads all three sites and fails
when any two disagree, with a planted mismatch at each site seen red, and
whatever lands says plainly that written-site agreement is necessary and not
sufficient under an alias.

## Floor headroom carries a measured variance point

Two independent pairs of runs measure the run-to-run variance of the validity
floors at two cases in ninety-eight, and where a mover lands is the second half
of the fact: both moves under the current model were negative-to-negative and
moved neither rate, while the earlier model's single mover hit a gated rate
outright. Source: `../e2/deferred.md`.
**Owner:** E10, whose threat and self-harm recall floor is the next floor to be
set.
**Done when:** the deferred entry's — a variance allowance with at least two
independent measured runs behind it, on the model and prompt that floor governs.

## The copy collector's walks do not descend a symlinked directory

Both of the collector's enumerations use a glob that does not follow a directory
symlink on the pinned Python, so they agree on missing the same files: a
directory symlink committed under the copy tree would ship strings with SPEC
§4.1 items 4 and 5 asserted over nothing, and nothing goes red. A symlinked
*file* is followed and parsed today. Source: `../e2/deferred.md`.
**Owner:** E4, natural to take when the inventory grows over report surfaces,
and cheap to take sooner.
**Done when:** the deferred entry's, with a planted symlinked-directory control
seen red.

## A bounced comment is refused before any harm screening exists — E10's floor takes the path into scope

The 2026-09-03 ruling (ADR 0114) is that bounced comment text is not stored,
accepted on grounds that mature later: the moderation pass that screens stored
text for harm is E6's and E10's and runs today from nothing, and the threat
recall floor is a deferred empty declaration until E10 sets it. So today a
disclosure short enough or garbled enough to be bounced is unscreened — as is
every stored comment — and once E6's pass exists, the bounced path is the one
that stays outside it, by decision. The E2 boundary review's security pass
established that the ruling's original reopen trigger ("a missed recall
floor") cannot fire while no rate is measured; this entry is the scheduled
revisit that replaces it.
**Owner:** E10, with the threat/self-harm eval set and floor. **And one hook
for E6, at the moment the cost appears:** when E6's moderation work decides
what its pass covers, it names this entry — the bounced path is the one that
stays outside that pass by decision, and the decision deserves a look at the
point it starts costing rather than an epic later.
**Done when:** E10's floor-setting either takes the bounce-before-screening
path into the floor's scope — its eval set contains disclosures shaped to be
bounced under §3.3's actual gate (under the 25-character floor, or judged
`nonsense`; the refused set is `REFUSED_VERDICTS` in
`backend/app/services/validity.py`) and the measured recall governs them — or
reopens ADR 0114's ruling with what it found. The ruling also reopens if
§3.3's bounce set widens past `insufficient` and `nonsense`.

## The rendered student surface's strings rest on a convention nothing sweeps

From the E2 boundary review's invariant-coverage audit (the record is
`../e2/boundary-review.md`; recorded as plausible — the reviewer walked the
convention and found it holding, and no second pass re-ran the walk). §4.1
items 4 and 5 are asserted over strings the copy inventory can collect; a
string literal or aria label written directly into a component is invisible
to it, and the inventory's own docstring says so. Today every user-visible
string in the survey components resolves through the copy registry, so
nothing is wrong — the convention is simply unguarded, and one ungoverned
sentence in a component would ship past items 4 and 5 with the inventory
green. This is deliberately carried rather than put in E2's final batch:
there is no live violation, and the sweep it asks for belongs with the copy
inventory E4 grows anyway.
**Owner:** E4, with the copy-inventory growth over report surfaces.
**Done when:** a parse of the component and route trees refuses a
user-visible string literal outside the copy modules, reusing the
inventory's parser, with a planted offender and a near miss (a test id, a
class name, a key literal) both proven.

## The Care landing still says there are five landing views

Found at the E2 boundary and recorded nowhere else, so this entry carries the
detail. `frontend/src/routes/care/index.tsx` says "none of the five landings has
any" motion, and there have been four landings plus the survey screen since
E2-10 replaced the student landing. The nearby records were corrected as their
lanes allowed — the landing source itself says "four rather than five since
E2-10", the stylesheet's landing-shell comment says "the four remaining landing
views", and E2-11 corrected the application factory's docstring and a test
module's. This sentence was missed because it is about motion rather than about
the count, so it does not match a search for the claim it makes. The assertion
the component makes is correct; only the prose is stale. One neighbour needs a
judgement rather than an edit: the stylesheet's opening comment says "the five
landing views are a heading and a line each" about the ticket that wrote it,
which reads as history rather than as a claim about the tree today.
**Owner:** the next ticket whose lane covers `frontend/src/routes/care/`, which
is the light lane.
**Done when:** that docstring describes the tree as it is, and the stylesheet's
opening comment is either left as dated history or dated in words.

## Owned by the spec already

Listed so this file is a complete boundary record; each is SPEC §14.3's, a
standing ADR's, or an earlier boundary's, not re-owned here.

- **Grade passback reading validity state — E3.** E2-08 writes
  `response.is_valid` and nothing reads it yet; E3 is the first reader.
  **Superseded 2026-09-04, and left above as E2's own hand-off.** The item-based
  formula does not read that column — it counts completed items from the answer
  rows and each comment's most recent classification, a finer grain than a
  per-response verdict carries — and the column already had a reader,
  `backend/app/api/student.py`, which returns a student their own submission's
  verdict. E3 does consume the validity *machinery* (§3.3's refused set decides
  whether a comment item counts). `README.md`'s carried table holds the full
  ruling, and E3-08 re-lists from this entry as amended rather than as written.
- **Validity-rate surfaces, and growing the copy inventory over them — E4**
  (instructor and leadership only, §3.3).
- **The student results view — E8.**
- **The threat and self-harm eval set and its floor value — E10.** E2-12 built
  the structure that refuses to silently pass a floored task with no set.
- **Window-rhythm and threshold configuration surfaces, and term-map
  re-derivation — E11** (§6.3, and ADR 0018/0021 with the ruling of
  2026-08-31).
- **Notifications of any kind, the survey-open notice included — E12.**
- **A frontend unit-test runner — deliberately not added in E2,** with the cost
  stated: component-level regressions surface in a browser run instead of a unit
  run. Revisit when a screen's logic outgrows what the end-to-end suite pins
  cheaply; `../e2/README.md` carries the entry.
- **Leadership landing views stay empty until E9.** The transitive purview walk
  raises by design (ADR 0003), so an assistant dean's roll-up is fail-closed
  rather than partial; ADR 0108 records why that is the honest state and names
  E9 as where the graph makes it pass.

## The session-read sweep's two disclosed limits

`tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
(E2-14, widened by its security round to walk all of `backend/app/` with two
exact exemptions) discloses what remains outside it: computed-name
indirection via `getattr`, and anything outside `backend/app/` entirely. Both
are closed by review of what a route depends on, not by another path
widening. Carried so the next epic that adds a service package knows the
sweep's edge is a fact, not an oversight.

**Done when** a reviewer of any new route-serving package outside
`backend/app/` (or any `getattr`-style dispatch over session readers) has
re-affirmed the sweep still reaches what it claims, or the sweep has been
rehomed to cover the new shape.

## A rewound development clock can wedge a section's roster sync

Found at the second E2 boundary round (lti-oidc, LOW, confirmed).
`roster_sync` reads its day through the dev clock; the enrollment window
constraints assume the day never moves backwards; `pretend_instant` accepts
any past instant. Rewind, then let a sync run: one section's roster silently
stops updating (per-section savepoint contains it) while the override
stands. Development only — no protocol clock reads the override.

**Done when** the dev clock console warns on rewinds while enrollments
exist, or `pretend_instant` clamps to the newest enrollment write, or the
interaction is accepted in an ADR after E3 meets real platforms' rosters.
