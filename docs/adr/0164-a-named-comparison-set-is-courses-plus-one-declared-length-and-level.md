# 0164 — A named comparison set is a list of courses plus one declared length and level

## Context

SPEC §5.1 lets leadership define named comparison sets beside the default one:

> The default comparison set is the same Lead Faculty's courses filtered to
> matching length+level; leadership can define named sets, and set-definition UI
> makes invalid combinations impossible rather than erroring on them.

and, earlier in the same paragraph:

> To be comparable, sections must match on **both** length (§2.2's length set)
> *and* level (§8's set: `DEV`, `UG`, `UGGR`, `GR`, `DR`) … Levels match
> **exactly**; no level is folded into another.

The spec says a named set exists and says what comparability requires of it. It
does not say what a named set is *made of*, and several shapes satisfy both
sentences: a list of sections, a list of courses, or a stored filter that names
a length, a level and an owner and resolves to whatever matches. E5-01 has to
pick one and give it a schema, and E5-04 resolves whatever is picked into a
cohort of sections.

Three further questions come with the shape and are settled here because they
are all one decision in practice: where the length and level are held, what
happens when a member course is deleted, and who a set records as its creator.

## Decision

**A named set is a list of member courses plus one declared length and one
declared level.** `comparison_set` carries the pair; `comparison_set_member`
carries one course in one set. E5-04 resolves a set to the member courses'
sections of the declared length, across the current and prior terms.

**Membership is at course grain, not section grain.** Benchmarks are
past-referencing and a section exists in exactly one term, so a set of sections
would age out every term and leadership would rebuild it each time. A set of
courses keeps its meaning as terms come and go.

**The length set is hard-coded in the migration**, as
`length_weeks IN (3, 6, 8, 10, 12, 15, 16, 18)`, citing SPEC §2.2. It is written
out rather than as a range because the set has interior gaps: a range accepts 17
weeks, which is a benchmark nothing can ever resolve.

**The level rule is enforced across the two tables by the database.** A `CHECK`
cannot read another table (ADR 0018), so the membership row denormalizes both
levels — `set_level` and `course_level` — and each is held to its own table by a
composite foreign key, into `comparison_set (id, level)` and `course (id,
level)`. A `CHECK` then compares two columns of one row. `course` gains
`UNIQUE (id, level)` for the key to reference; since `id` is a primary key the
constraint refuses no row that could otherwise be written. The mechanism is the
one `response`, `survey_window` and `release_batch` already use for the
section/term pairing.

**Deletion runs in opposite directions.** Deleting a course a set names is
refused (`RESTRICT`). Deleting a set takes its membership rows with it
(`CASCADE`) and leaves every course untouched.

**A set records its creator as a foreign key to `person`**,
`created_by_person_id`, with `RESTRICT` — the actor convention `audit_log`
already uses. No name is copied onto the row.

**A set may be empty.** What an empty set means when it is resolved is E5-04's:
suppressed, like any set below the benchmark minimum (SPEC §4.1 item 7).

## Alternatives rejected and why

**Membership at section grain.** Rejected because benchmarks are
past-referencing: "week N of a 12-week section is compared against week N of
12-week sections of the same level in the current *and prior* terms". A set of
sections describes one term, so every set would need rebuilding each term and a
set that was not rebuilt would quietly stop covering the present. It also makes
the declared length redundant, which sounds like a simplification and is
actually the loss: with no declared length the set has no rule to hold new
sections to.

**A stored filter rather than a stored list** — a set as a length, a level and
an owner, resolved to whatever matches at read time. Rejected because it makes
the set's contents change without anybody deciding they should: a course added
to a department joins every filter that covers it, and last week's published
figure is not reproducible. It is also the shape that cannot express the thing
leadership actually asks for, which is a deliberate list.

**Reading the length set from the per-term start-letter map** instead of
hard-coding it. The map is where a section's length is really derived from, so
this reads like the one-source answer. Rejected because the map is *term* data
and a set outlives terms: a set validated against this term's letters becomes
invalid the moment a later term's map omits a length nobody ran that term, and
the operator meets a row that will not save. The cost of hard-coding is a
migration when the institution's calendar gains a length, which is a
deliberate change to §2.2 and reaches the spec anyway.

**Enforcing the level agreement in E5-06's route** rather than in the database.
Rejected by the ticket's own criterion, and rightly: a route is one caller among
several by the time E5-09 and any later import exist, and a set holding one
off-level course produces a mean over two populations §5.1 says are not
comparable — visible nowhere on the chart it is drawn on.

**`CASCADE` on the member-to-course key.** Rejected because a set that shrinks
without anybody deciding it is a benchmark that changes without anybody deciding
it, and past-referencing means the change reaches figures that were already
published. The only trace would be the difference between two Mondays' charts. A
course leaving the institution is a real event and is one somebody edits the set
for. The cost of `RESTRICT` is that deleting such a course fails until the sets
naming it are edited, which is the intended friction.

**`RESTRICT` on the member-to-set key**, for symmetry. Rejected because the set
is the aggregate root: E5-06 builds the delete, and a set held in place by its
own membership rows is a set nobody can remove without the caller deleting the
members first.

**A creator recorded as a name, or not recorded at all.** A name would put
identity on a table the identity sweep would then have to mark, which would
forbid the read every surface offering a named set needs. Recording nobody would
leave a cohort that shapes every instructor's benchmark with no accountable
author.

## Consequences

- A set is only as current as leadership keeps it. A new course in a department
  does not join a named set; somebody adds it. That is the price of a
  deliberate list and the reason the default comparison set stays computed.
- Deleting a course requires editing the sets that name it first. Postgres
  answers a foreign key violation, and the surfaces that delete courses have to
  say so in a way an operator can act on.
- The membership row carries two columns that are copies of other rows'
  values. They cannot drift — each is held by a foreign key — but any reader
  writing SQL against the table has to know they are the key's second column
  rather than free data.
- `course` carries one more unique constraint and its index. It refuses nothing,
  and no fixture can break on it.
- The length set now exists in three places: SPEC §2.2, `CALENDAR_LENGTHS` in
  `app/models/benchmark.py`, and the `CHECK` in migration `b4d7e2a91c58`. The
  migration's copy is deliberate — a migration is a record of what was applied
  and must not change when a model does — but a calendar change touches all
  three.
- `pulse_app` holds no privilege on either table. E5-04 grants the read it
  spends and E5-06 the writes it spends, each in its own change; until then the
  tables are unreachable from any request path, which
  `tests/integration/test_the_comparison_set_tables_are_refused_to_the_application_connection.py`
  proves on the connection production opens.
