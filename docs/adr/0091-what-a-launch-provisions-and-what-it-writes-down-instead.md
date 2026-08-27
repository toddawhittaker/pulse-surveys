# 0091 — What a launch provisions, and what it writes down instead

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
carries the accept-side criterion.

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

**Two rows already there are tolerated, not reported.** A returning person's
`user` insert and a simultaneous first launch of one section both end in a unique
violation inside a savepoint, which is rolled back and ignored — the row this
launch wanted exists. The cost is that a genuine constraint defect on those three
tables would also be swallowed; the check that would catch it is the suite, not
production.
