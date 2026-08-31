# 0091 — What a launch provisions, and what it writes down instead

> **Amended 2026-08-27 by E1-11.** Three sentences below were true when this was
> written and are not now. Everything else stands, and nothing here is reopened.
>
> - **"The day of the launch" is the institution's day, not UTC's.** The
>   consequence paragraph saying otherwise, and the rejected alternative "A
>   `settings` parameter for the institution timezone", record the state E1-10
>   shipped. E1-11's D13 took that alternative — `provision_from_launch(session,
>   claims, settings)`, with the door passing `request.app.state.settings` — so the
>   term a new section lands in is read off `settings.institution_timezone` (SPEC
>   §3.1, §8). The rejected-alternative paragraph stays in place as the record of
>   what deferring it cost, which is what deferred E1-10 item 2 was.
> - **`_environment()` is gone with it.** It read `os.environ` for the rule
>   deciding which roster addresses this container may fetch, and `Settings` reads
>   `.env` where `os.environ` does not — so a development stack configured only by
>   a `.env` file was judged by a deployment's rules and the mock's own cleartext
>   address was refused. `settings.environment` is the one answer now (deferred
>   E1-10 item 5).
> - **E1-11's sync does not write sections.** The paragraph on the unique
>   constraint says it "writes sections and never reads
>   `app.services.provisioning`". The second half stands and is still why the
>   constraint belongs in the schema; the first half does not — E1-11's catalog
>   entry grants `user`, `enrollment` and the `INSTRUCTOR` `role_assignment` row
>   and deliberately not `section`, because SPEC §7.3 gives a section exactly one
>   way to be discovered (ADR 0090's own amendment, and ADR 0095).
>
> One thing this record predicted and E1-11 confirms: "E1-11 picks its platform off
> the binding, not off the section's course." The sync resolves its registration
> through `section.lti_deployment_id` and through nothing else, which is deferred
> E1-10 item 1's done-when.
>
> E1-11 also spends what this record left open at the door: `provision_from_launch`
> now answers with the id of the section a roster can be fetched for, or `None`, so
> that the launch handler can hand it to the debounced sync trigger without
> resolving a context claim to a row itself.

## Context

SPEC §2.1 gives courses and sections two arrival paths, "hourly roster sync +
launch-time ingestion", and §7.3 makes the first staff launch of a section the
only thing that can bootstrap the second: the scheduled job "has no way of its
own to learn that a section exists". E1-10 builds that path. The spec settles what
is LMS-owned, that the launching person's role authorizes the trigger, and that an
out-of-band course number is "a defect to see, not a row to accept" (§8, ADR
0015). It settles none of the following, and a reasonable engineer would decide
each differently:

which term a newly discovered section belongs to; what `course.lms_title` holds
when a platform sends a context with no title, given the column is NOT NULL; what
happens to a launch whose context cannot be read at all; and what the record of
that failure may contain, given §10 keeps personal information out of what gets
written down.

Todd ruled on the first three on 2026-08-26. This record is those rulings plus
the design they imply. The mechanism by which this writer passes `guard_write` is
[ADR 0090](0090-a-sanctioned-writer-passes-the-chokepoint-by-being-in-a-catalog.md);
the calendar derivation it leans on is
[ADR 0021](0021-a-sections-derived-calendar-has-one-writer.md).

## Decision

**A `user` row for every verified launch, before anything else.** The launching
subject is authenticated whatever their role and whatever their context turns out
to be, so a teaching assistant the door has no view for, and an instructor whose
course number is out of band, both get one. It is inserted without a prior read
and `UNIQUE (lti_platform_id, lms_user_id)` decides — the same reasoning
`claim_nonce` gives for spending a nonce with no `SELECT`, and it keeps this
module clear of E0-11's rule that a service does not query an identity table.
E1-12 builds on that row existing for anyone who has launched.

**A staff launch is the exact context-instructor URN, and nothing else yet.**
A whole-value comparison against
`http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor`. The rule it
defends against is not one URI matching the other — the TeachingAssistant
sub-role URN is `…/vocab/lis/v2/membership/Instructor#TeachingAssistant` and
neither URI contains the other — but the implementation somebody writes instead,
`any("Instructor" in role for role in roles)`, which that sub-role satisfies
because it spells its parent role in its own path. §7.3's
leadership limb is stated and **dormant**: resolving a launch subject to a live
`role_assignment` needs the `sub` → `user` → `person` link only E1-12 builds, so
until then a dean's launch discovers nothing. That fails safe — a launch that
provisions late, rather than one that provisions for the wrong person — and E1-12
carries the accept-side criterion. **That limb is live as of E1-12**: the
launching subject resolves to a person and `public.assignment_scope` is asked
whether they hold a leadership role, with the claim test above running first and
short-circuiting, so an ordinary instructor launch costs no query. See
[ADR 0097](0097-the-identity-a-verified-subject-resolves-to.md); nothing else in
this record changes.

**The term is the one whose dates contain the day of the launch** (Todd's
ruling). Not the only term, not the most recent: an empty `term` table and a table
holding next year's term are different situations with the same answer, and taking
whatever term exists would put every section of the year into it. No such term
means the launch is refused and recorded — **a pre-term launch refusing is a named
limit of this design**, and the repair is an administrator configuring the term,
which is where §2.2 puts the calendar anyway.

**The label parse is exactly `PREFIX-NUMBER-CODE` on hyphens.** The prefix must
already exist in `prefix`, because §2.1 builds the org top-down and a launch may
not invent the containment chain it hangs from. The number is checked against §8's
bands **in Python, before any write** — `course.level`'s NOT NULL would refuse an
out-of-band number too, but as a 500 in the middle of a request rather than as a
refusal anybody can see.

**The titleless case splits in two** (Todd's ruling). A context carrying `id`
alone identifies no course and is refused and recorded. A context carrying its
`label` and no `title` identifies one perfectly well: `course.lms_title` becomes
`"BIOL 215"` — the label's prefix and number, spelled as §2.1 spells a course —
and a new Pulse-owned column, `course.title_is_fallback`, records that this
project made the value up. The marker is what makes the corrections asymmetric: a
real title replaces a fallback and clears the flag, a fallback never replaces a
real title, and a *changed* real title replaces the stored one because the LMS
owns the name.

**A refusal is a `launch_defect` row and never a failed launch.** Five kinds, as a
closed Postgres enum: `unparseable_context_label`, `unknown_prefix`,
`out_of_band_course_number`, `no_term_for_launch_date`, `section_code_underivable`.
Five fields beside the key: kind, issuer, deployment id, context id, timestamp —
and never a `sub`, a name, an email or a claims payload (§10). Log lines on this
path carry no more than the row. Course and section are written together or not at
all; the `user` row lands either way, because the person is not what failed.

**A section is resolved by the context it was discovered from, and the two
identities have to agree** (round 3). `section` carries `lms_context_id` — the
context claim's `id`, the platform's own value — and `lti_deployment_id`, the
registration it was issued under, unique together **in the database**. A launch
resolves by that pair first, and by the parsed identity `(course, term,
lms_section_code)` second, and the two disagreeing is a `context_collision`.
Both directions of one question are that disagreement — a copied course wearing
another context's name, and a renamed context whose old name is somewhere else —
which is why one rule closes both. The unique constraint is in the schema rather
than only in the writer, because ADR 0045's "a caller can bypass it by not calling
it" applies to E1-11's sync, which writes sections and never reads
`app.services.provisioning`.

**What a collision stops is that launch, and the scope of "nothing is written" is
worth stating exactly** (the round-3 re-pass asked, and an earlier draft of this
paragraph over-claimed). When the two identities disagree, nothing at all is
written for that launch — the course's title included — because the check sits
above the atomic boundary rather than inside it. It does **not** mean a course's
title is protected from every other context that names it: a launch whose section
identity agrees takes the ordinary path, and that path writes the title of the
course its label names, which may be a course several contexts share. That is
SPEC §2.1's model rather than a gap in this one — the LMS owns a course's title,
`course` is keyed `(prefix_id, lms_number)` and is deliberately one row per course
however many sections and contexts hang off it, so the last staff launch to name
that course sets the name. **Accepted**: the alternative is per-context titles,
which is a different schema and a different product.

**The roster address is judged by the rules every address this container fetches
passes** (round 3). It arrives as an NRPS claim and E1-11 calls it with the tool's
own client credentials, on a schedule, with nobody present — so it goes through
`app.models.lti.refuse_invalid_fetched_address`, the same rules `jwks_url` and
`auth_token_url` pass — four of them when this was written, five since
[ADR 0101](0101-a-fetched-address-is-judged-by-what-it-resolves-to.md) added the
resolution — reached through the one function that holds them rather than a copy
beside it (`docs/MISTAKES.md` entry 13). A refused address leaves the
column NULL, records `roster_address_refused`, and **still provisions the
section**: §7.3 makes a section with no roster a state rather than a fault, and
refusing the launch would take a real course out of the product over a URL.

**A refusal from `guard_write` is caught, logged at error level, and given no
record.** It cannot happen while the catalog and this writer agree, and the day
they stop agreeing — a table added to a write site and not to the grant, or
dropped from the grant and not from the writer — the refusal would otherwise
escape the launch request and lock every person out of the product. That is the
failure direction this record's first rule forbids, arriving on the one path where
the chokepoint is working, so it is caught on the same savepoint a defect is
(nothing partial survives) and the person lands. It gets **no `launch_defect`
row**: the five kinds are facts about a launch's context and this is a fact about
this project's own code, and it would need a sixth kind that the closed set is
pinned against having. The error line names the writer and the table and is the
whole of the visibility.

## Alternatives rejected

**Refusing the launch on a defective context.** It turns a data-quality problem
into a person who cannot get into the product, and it puts the failure where
nobody who can fix it will see it.

**Skipping the write and logging.** `docs/MISTAKES.md` entry 26 exactly — the
fallback path swallowing the defect that triggered it. A row is a surface E11 can
build on; a log line is not.

**Leaning on `course.level`'s NOT NULL to refuse an out-of-band number.** Free,
and it produces a 500 with no record. The Python check is a second spelling of
§8's bands and the two have to move together; that cost is stated in the source
beside both.

**A nullable `lms_title`, or storing the context id as the title.** The first
makes a section with no name renderable everywhere and reportable nowhere; the
second puts an opaque platform identifier on a screen a person reads.

**An unmarked fallback title.** Then this project's guess is indistinguishable
from the LMS's own value, and no later launch or sync can tell whether replacing
it is a correction or vandalism.

**Recording the `sub` on a defect** so an administrator can ask the person what
happened. It is the join key E1-01 keeps out of every view, and an ingestion
failure is a fact about a course — the person who happened to be launching is not
part of it.

**A `settings` parameter for the institution timezone**, so "the day of the
launch" is the institution's day. It would have to be threaded through the door;
see the consequence below.

## Consequences

**The launch handler gains a call and a second commit.** The launch's own
persistence — the claimed nonce, the consumed handshake — commits first and is not
hostage to what provisioning found.

**A defect is invisible until E11 builds the surface.** `pulse_app` holds `INSERT`
on `launch_defect` and no `SELECT` deliberately, so nothing in this epic can read
one back; today the only way to see one is a direct query as an administrator.

**"The day of the launch" is UTC's day.** The writer is handed a session and
claims, not settings, so a launch in the hours either side of a term boundary can
be read into the neighbouring calendar day. Small and real: the repair is to pass
the launch moment in, and E1-11's sync will want the same. Recorded rather than
built.

**Overlapping terms are decided by the most recently started one.** The schema
permits two terms to contain one day and nothing else adjudicates; a deterministic
answer beats `MultipleResultsFound` in a request, and the configuration is what
wants fixing.

**A renamed context label is a new section.** Nothing stores the platform's
context `id` against the section, so a platform that renames `BIOL-215-R3WW` to
anything else presents a section this tool has never seen and discovers a second
one. Nobody has asked for rename handling; storing `lms_context_id` is the obvious
future repair and is deliberately unbuilt.

> **Round 3, 2026-08-26 — this consequence was the safe half of a hole, and it is
> closed.** The security review asked the *other* direction of the same question:
> not one context under two names, but one name under two contexts. A Canvas
> course copy keeps the section code, so a staff launch from the copy parsed to the
> original section's identity exactly — and the writer resolved by that parse, so
> it repointed the original's stored roster address at the copy's own endpoint and
> overwrote its course's title. E1-11 fetches that address with the tool's own
> credentials, so the original section's roster, names and email addresses
> included, went to whoever held the copy. Copying a course needs no privilege at
> all. The paragraph above stands as the record of what was known then, and the
> rest of it — that storing the context id was the repair — turned out to be
> right for both directions.

**The first context to claim a name owns it, and nothing ages that claim out.**
The binding makes `(course, term, lms_section_code)` first-writer-wins: whichever
context provisions first holds the name, and every later context whose label parses
to it is refused. That is the direction this design chose on purpose — the
alternative, and what the code did before round 3, is the last launch silently
repointing the section — but it has a cost worth writing down. **A copy launched
before the genuine context denies the genuine one.** Somebody who copies a course
and launches it first takes the name, and the real instructor's launches are
refused from then on, each leaving a `context_collision` row naming their context.
That is loud rather than silent, which is the whole of why it is the safe
direction: an administrator reading E11's surface sees a specific context being
refused, repeatedly, with the identifiers to act on. What does not exist yet is the
acting: nothing rebinds or retires a squatted section, so the denial is unbounded
in time until an operator repairs it by hand. **The reconciliation question is
deferred** — `docs/tickets/e1/deferred.md` carries it with a done-when — rather
than answered here, because the repair needs an operator surface E11 owns and a
rule about who may rebind, and neither belongs to a launch path.

**A concurrent first launch is tolerated, so its collision is recorded one launch
late.** Two contexts whose labels parse alike, launching for the first time at the
same moment, both find no section and both insert one; the second violates the
unique constraint and
`_tolerating_a_row_that_is_already_there` rolls its savepoint back and carries on,
because that helper cannot tell "the row I wanted is already there" from "somebody
else's row is". So the loser writes no `context_collision` on that launch. Its
*next* launch takes the ordinary path — the binding lookup finds nothing, the label
lookup finds the winner's row, the identities disagree — and records the collision
then. The window is one launch wide and closes by itself, and the state it leaves
in the meantime is the correct one: the loser has provisioned nothing.

**E1-11 picks its platform off the binding, not off the section's course.** The
sync mints a client-credentials token for one registration, and
`section.lti_deployment_id` is now what says which one a section's roster belongs
to — the column exists precisely because a context identifier means nothing
outside the registration that issued it. A sync that resolved the platform any
other way would be able to present one institution's token to another
institution's roster service, which is the finding this pair closes arriving one
epic later. `docs/tickets/e1/deferred.md` carries it with a done-when.

**A section stored before the binding carries a synthetic context id.** The
migration binds it to the one registered deployment under a `pre-binding-section-`
identifier, and refuses to guess where there is no unambiguous registration. Those
rows are unreachable by any launch, which is right for rows no launch created —
the demo seed's eighteen sections are the only ones that exist — but it does mean
`lms_context_id` is not universally a value some platform issued, and a reader of
that column has to know it.

**Two rows already there are tolerated, not reported.** A returning person's
`user` insert and a simultaneous first launch of one section both end in a unique
violation inside a savepoint, which is rolled back and ignored — the row this
launch wanted exists. The cost is that a genuine constraint defect on those three
tables would also be swallowed; the check that would catch it is the suite, not
production.
