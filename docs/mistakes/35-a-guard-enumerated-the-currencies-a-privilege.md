# Entry 35. A guard enumerated the currencies a privilege can be held in, and missed the one the design deliberately uses

**Caught: 6**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*12 occurrences recorded; six of them are catches. This file keeps the three
most recent instances; the rest live in git history — it is carrying five today,
because the oldest of them and the addendum under it are one lesson and trimming
one without the other would leave a paragraph referring to nothing.*

*(**A catch**, writing E2-16's tests, 2026-09-03. Three of the ticket's criteria
are assertions that something is **absent**: no `NOT IN` in any statement the
floored-comment sweep sends, no growth in the reads window derivation issues as
sections are added, and — the mirror image — an index over
`classification (task, prompt_version)` that is present. Each is read through an
instrument this ticket wrote: a `before_cursor_execute` recorder, and a catalog
matcher over an index's leading key columns. Every one of those absences passes
for free against an instrument that sees nothing, and the matcher's assertions
pass equally against a matcher that says yes to everything. This entry's rule put
both directions in the suite before anything rested on either: the recorder is
shown a real `NOT IN` over the real tables and has to flag exactly one, and is
shown a lone `SELECT` and has to count exactly one read; the matcher has to find
the two week-axis indexes that certainly exist and to refuse a column
(`response.first_submitted_at`) that nothing indexes. Without them, the day the
listener was registered on the wrong event, three criteria would have gone green
over a sweep nobody had watched.)*

*(Building E2-08, 2026-09-02. Three discovery walks in one ticket's test
machinery each reported a deliverable missing while it was present, and each
repair widened the walk by exactly the one level the last failure exposed: a
Celery task filtered by `__module__`, which a task proxy reports as
`celery.local` (`docs/disputes/E2-08-02.md`); a request model required to be
*defined* in the route module, while SPEC §13 homes it in `app/schemas/`
(`docs/disputes/E2-08-06.md`); then the same walk again, blind to the model
being nested behind `list[...]` in the model it did find. None of the three
applied this entry's rule when the walk was written — a discovery that
enumerates candidates must *find* a subject certainly present, as a control —
so every failure was a red naming the code instead of a red naming the walk,
and each was caught by a run rather than by reading. The repair that ended it
closed the class: both discovery helpers now carry a control asserting they
find something the tree certainly holds.)*

*(**A catch**, writing E2-03's refusal tests, 2026-09-01. The refusal test
asserts that the raw foreign-key-violation shape is absent from the migration's
failure, read through a new reader that walks the server's `message_primary`,
`message_detail` and SQLSTATE chain. Entry 35's rule turned that absence
assertion into a second control: the same reader and the same SQLSTATE walk are
run against a real foreign key violation and required to find it, by phrase and
by code. Without it, a reader that returned nothing — a driver whose `diag`
moved, a chain walk that stopped early — would have made the absence assertion
pass against the exact defect the ticket exists to remove, and the test would
have gone green the moment its machinery broke.)*

*(**A catch**, writing the E1 re-review fix's closure sweep, 2026-08-31. The
re-review had found M6's own defect recurring — three new confidentiality-denial
test modules outside the isolated §4.1 pass — and the sweep written to close it
was about to enumerate the currencies a module can hold the `invariant` marker
in: module-level `pytestmark` and per-test decorator, both accepted. That
enumeration reads `test_the_dev_console_names_nobody.py` as compliant while only
one of its tests sits inside the pass, and it goes on approving the module as
undecorated denial tests accrue to it — the role the scheme is built around,
holding its privilege the unusual way. The entry's rule turned the enumeration
around: pin the single currency the design uses — the module-level form — and
refuse the rest, so a module holding its marker any other way is red until it
adopts the form, never silently approved. The control corollary is applied too:
the sweep's planted tree carries a module for each currency, including the
per-test-only one, and asserts exactly which are demanded and which are found.)*

*(**The catch**, writing E0-34's tests — the guard that reads
`backend/app/views_sql/*.sql` looking for an identity column. It enumerates two
mechanisms, a column named as a word and a `SELECT *` over a table that carries
identity, and the shape it was about to ship was one predicate returning "found
something / found nothing" with a handful of samples asserted through it. That
version passes with either mechanism deleted: the natural sample —
`SELECT * FROM public.user_identity ui WHERE ui.identity_name IS NOT NULL` — is
caught by both, so the aggregate stays non-empty whichever probe is removed, and
the star mechanism could have been dropped in a later tidy with every test green
and `SELECT *` over the identity table unguarded. What this entry changed:
findings carry the label of the mechanism that produced them, the control asserts
that label rather than non-emptiness, and each sample is written so **only its
own mechanism** can catch it — the column samples name a relation that is not an
identity table, the star samples name no identity column. The corollary about
running the whole path came from E0-33's own repair and is applied too: the
control calls `identity_findings`, which walks the table, and never
`mechanism.find`.)*

*(**And it did not stop the level above.** The control that catch
produced was parametrised over the mechanism table itself, so deleting a
mechanism deleted its own case and the controls passed at the smaller size —
three tests where there had been four, with a planted view file reading a marked
identity column going completely unguarded. This entry's rule is about each
mechanism being *found* on a subject that has it, and says nothing about where the
list of subjects comes from. Found by mutation in review, so no bump. The repair
is an inventory written down separately, which the table cannot shrink: a
required-labels constant, a flat tuple of shapes, and a test over neither of the
structures being guarded. **A control is only as complete as the list it iterates,
and a list derived from the thing under test cannot notice a deletion.**)*

**What happened.** E0-33 added a sweep asserting that neither runtime connection
role can *become* a role that may read identity. It was written because
`has_table_privilege` and `pg_has_role(…, 'USAGE')` both follow role
inheritance, so a membership granted `WITH INHERIT FALSE` writes no ACL entry
and is invisible to both — a real hole, correctly found, and the sweep asked in
`'MEMBER'` mode to close it.

The sweep built its set of dangerous roles from **table privileges on
`user_identity`**. `pulse_care` holds none. That is not an oversight in the
schema; it is the entire design of
[ADR 0001](../adr/0001-identity-separation-by-database-role.md) — the Care role
reaches a name only by executing one `SECURITY DEFINER` function, and holds no
grant on the identity table at all. So the role the whole confidentiality scheme
is built around was the one role a membership sweep phrased over table
privileges could never flag.

Measured on a live database, after `GRANT pulse_care TO pulse_app WITH INHERIT
FALSE`:

| probe | before `SET ROLE` | after |
|---|---|---|
| `has_table_privilege(user_identity,'SELECT')` | false | — |
| `pg_has_role('pulse_care','USAGE')` | false | — |
| `has_function_privilege(reveal,'EXECUTE')` | false | **true** |
| `has_table_privilege('role_assignment','SELECT')` | — | **true** |

One statement, and the connection every instructor and leadership screen runs on
can `SET ROLE pulse_care` and call the reveal. The full suite — 42 tests, three
of them `invariant`-marked — stayed green. The reveal verifies the actor it is
*handed* rather than its caller, so the audit row it writes names an innocent
CARE person: the escalation launders itself through SPEC §4's audit trail.

A second instance of the same shape sat one test over. A test named for "anything
in `public`" read `pg_class.relacl` and never `pg_proc.proacl`, so a role granted
`EXECUTE` on the reveal function was outside every assertion in the suite while
able to call the door.

**Root cause.** A privilege is not one thing. It can be held as a grant, by
ownership, by a role attribute, by membership in another role, or as `EXECUTE` on
something that runs as somebody else. A guard is written against the currency the
author happened to be thinking about — here, the ACL — and the enumeration reads
as complete because every mechanism it names is genuinely checked. Nothing in a
green run distinguishes "no role can do this" from "no role can do this *the one
way I looked*."

The sharper half is that the miss is not random. **The role a scheme is built
around is the role least likely to hold its privileges in the ordinary
currency**, precisely because the scheme went to trouble to avoid giving it an
ordinary grant. So a guard phrased over the ordinary currency is not merely
incomplete — it is systematically blind to the most dangerous case, and it looks
strongest exactly where it is weakest.

**Rule.** When a guard enumerates the mechanisms by which something can be held,
require it to **find** each mechanism on a subject that certainly has it, and
make that a control in the test. A guard that only ever reports absence cannot
tell you which mechanisms it can see. Put the mechanisms in a table, one per
line, so that disabling one is a single edit that still parses — then prove the
control by deleting a probe and watching the control go red while the sweep goes
green. The sweep passing while the control fails is the whole demonstration, and
it is not available at all if the mechanisms are welded into one predicate.

Two corollaries worth stating, because both were live here:

- **Ask what the protected object's own design does.** If the scheme deliberately
  gives a role its access some unusual way, that way is the first currency to
  check, not the last.
- **Name the catalog, not the concept.** "Nothing is granted in `public`" was
  implemented as `pg_class.relacl`. `public` also contains functions, and
  `pg_proc.proacl` is a different column. A guard's name should be no wider than
  the catalog it actually reads, or it should read them all.
