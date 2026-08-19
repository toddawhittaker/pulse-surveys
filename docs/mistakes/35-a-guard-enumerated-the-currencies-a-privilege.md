# Entry 35. A guard enumerated the currencies a privilege can be held in, and missed the one the design deliberately uses

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*3 occurrences recorded, and none of them is a catch.*

*(Twice more on the same pull request, after this entry was
written. **Both were found by review or by mutation, so neither is a catch** —
this file's own rule is that a detection does not earn a bump, and the counter
stays at 0 until this entry stops somebody in advance. **A column grant** is recorded in `pg_attribute.attacl`, which neither
`has_table_privilege` nor `pg_class.relacl` reads — a fourth currency, found by a
reviewer one round after the entry naming the third. And when the probe for it
was added, nothing asked it about the roles that hold the grant: the sweep
consulted the probes only for roles a runtime role could *become*, and a grant
made directly to `pulse_app` is not a membership. Measured: 28 tests passed while
that connection could read every student's name. **The control was the second
half of the same miss.** It called the probe function directly rather than
through the table of probes, so deleting the probe from the table left it green —
a control that cannot fail when the thing it guards is removed is not a control.
The repair on both was the same: ask the enumeration the question you actually
care about, and make the control run the whole path rather than the piece you
were thinking about.)*

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
