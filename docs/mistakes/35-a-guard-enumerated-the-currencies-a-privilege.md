# Entry 35. A guard enumerated the currencies a privilege can be held in, and missed the one the design deliberately uses

**Caught: 9**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*14 occurrences recorded; eight of them are catches. This file keeps the three
most recent instances; the rest live in git history — plus the oldest catch and
the addendum under it, which are one lesson, and trimming one without the other
would leave a paragraph referring to nothing. The E4-04 catch below makes four
recent ones, and the trim of the E2-16 paragraph is owed to whoever touches this
file next.*

*(**A catch**, writing E4-04's grant tests, 2026-09-06. The ACL half of
`tests/integration/test_the_comment_path_runs_over_the_connection_production_uses.py`
asks `has_table_privilege` in both directions over four relations and two roles,
and every one of those questions is answerable by a probe that has gone blind. So
each probe passes a control first: a relation the role under test certainly reads,
**one per role and that is the point rather than a detail** — `pulse_app` reads
`classification`, and `pulse_care` does not read it at all, because the Care role's
whole grant list is `SELECT` on `role_assignment` plus the reveal's definer path.
A control pointed at the wrong role's relation reports absence, passes, and makes
every assertion behind it vacuous, which is the failure a control exists to catch.
The same reading covers the one place this ticket reaches identity: the
respondent leg of the release gate walks `answer.response_id` to `response.user_id`,
and the identity-table sweep polices relation names and model classes, neither of
which a column called `user_id` is — so the module docstring names the three
functions a reviewer has to read rather than letting a green sweep stand as the
claim.)*

*(**A catch**, writing the E3 exit cleanup's tests, 2026-09-06. The view guards
on identity enumerate two currencies — a column dependency and a whole-row
reference — and ADR 0139's definer function is a third that neither sees: the
function body is a quoted SQL string, so a view calling it records no
dependency edge to the identity column at all. The new sweep was written with a
planted calling view, a join-key-only near miss that must not be flagged, and a
canary asserting a function of exactly the searched name exists — because a
guard that only ever reports absence cannot say whether it can see anything.)*

*(**A catch**, writing E3-04's tests, 2026-09-04. The ticket's criterion 6 is a
triple per AGS route — absent token refused, wrong scope refused, right scope
accepted — and the third is only there because of this entry: the ticket's own
known-traps section quotes it. A module holding the two refusals alone is green
against a platform that refuses **everything**, which is the one implementation
nobody wants and the cheapest way to satisfy a wall of refusal tests. Acting on
the entry put the accepting half beside every refusal *and* pushed it one level
further out, which is where the value was: the two read routes accept either the
line-item scope or its read-only sibling, so the control loops over the whole
accepted set rather than presenting the first one — an any-of rule implemented as
a single required scope passes a one-scope control and refuses a conformant tool.
Two more controls came from the same reading: the six routes are asserted to be
six different `(method, url)` pairs, because a `results_url` that came back as the
line item's own id would turn six routes into four with every refusal still green;
and the platform is required to *grant* a token for each of the four scopes, since
a driver handing back a string it invented would fail every acceptance and pass
every refusal.)*

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
