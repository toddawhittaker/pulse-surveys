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

## AGS still answers without a token

E1's fix round enforced the client-credentials token on NRPS only; the AGS
containers keep signature-level bounds and no credential check, because no AGS
client exists to build against. ADR 0099 records the decision and the boundary.
Source: `docs/tickets/e1/deferred.md`, "From the E1-11 fix round".
**Owner:** E3, paired with the first AGS client.
**Done when:** ADR 0099's consequences — enforcement lands with that client, the
way NRPS's landed with E1-11's.

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
