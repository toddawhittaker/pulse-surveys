# Entry 35. A guard enumerated the currencies a privilege can be held in, and missed the one the design deliberately uses

**Caught: 2**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*7 occurrences recorded; two of them are catches.*

*(**An occurrence, not a catch**, in E0-36 item 3, by the orchestrating session,
and the currency was a pytest marker. The question "which tests are marked
`invariant`" was measured with an AST walk over `decorator_list`, which answered
20. `pytest -m invariant --collect-only` answers 24: four tests are marked by a
module-level `pytestmark = pytest.mark.invariant` — three in
`tests/unit/test_no_service_reads_an_identity_table_directly.py`, one in
`tests/unit/test_care_is_not_reachable_from_a_claim.py` — and a decorator walk
cannot see any of them. The number went into the ticket and into a test docstring
as the justification for the rule being green on the suite. **The implementer read
both forms and got 24; the mutation that disables the `pytestmark` path makes the
checker report exactly 20**, which is a clean scan printed over four real §4.1
invariants it never looked at — item 3's own subject, inside the round that was
fixing item 3. The entry's sharper half held too: those two modules use
`pytestmark` **because every test in them is an invariant**, so the files that are
wholly confidential are precisely the ones the walk was blind to. "Name the
catalog, not the concept" is the corollary that applies — `decorator_list` is not
the marked set, pytest's collector is — and the repair is to quote the count from
the collector rather than from a walk. **The entry's own rule then closed the
second half of it**, one round later: the eight planted samples in
`tests/unit/test_the_invariant_gate_refuses_a_test_that_asserts_nothing.py` all
used the decorator form, so nothing under `tests/**` would have noticed the
checker's `pytestmark` path regressing — the currency had been named in the record
and not yet planted in the battery. Two samples now carry it, refused and allowed,
and it takes both: the refusal alone is passed by a checker that refuses every
`pytestmark` module whatever its body, and the allowance alone is passed by a
checker blind to the form, which scans nothing and objects to nothing. The refusal
is checked as a non-zero exit **and** the offending test named, because a checker
that cannot see the marking reports an empty scan, which may exit non-zero for its
own reasons and would otherwise read as the rule having been applied.)*

*(**A catch**, writing E0-35's tests — three static sweeps over writes to
LMS-owned data. All three have an empty subject set today, because E0 ships no
application write path, so the shape about to be written was a sweep plus a set
of samples it must *refuse*: over a tree containing nothing, that is a file that
reports green having demonstrated nothing about what it can see. This entry is
why each sweep is now required to **find** every mechanism it claims, on a sample
carried in the module — an ORM `add`, a Core `insert().values()`, textual
`INSERT`, `UPDATE` and `DELETE`, and an `INSTRUCTOR` role assignment written both
as the string `"INSTRUCTOR"` and as `AssignmentRole.INSTRUCTOR`, since a detector
that saw one spelling would miss whichever E1's roster sync happens to use. The
corollary about the design's own currency is what put the second spelling there:
the enum member is how the codebase actually holds a role, and the string is the
one a guard's author reaches for. The inventory follows the same rule — the ORM
half resolves every guarded table to a mapped class off `Base.registry` and fails
if any of them resolves to none, rather than trusting a class name typed into a
test file.)*

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
