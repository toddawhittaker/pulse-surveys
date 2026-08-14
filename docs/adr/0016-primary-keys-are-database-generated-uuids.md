# 0016 — Primary keys are database-generated UUIDs

**Status:** Accepted
**Date:** 2026-08-14
**Tickets:** E0-05

## Context

E0-05 creates the first six tables, so it picks the surrogate key every later
table will copy. [SPEC §8](../SPEC.md) lists the tables and their relationships
and says nothing about key type; §13 says nothing either.

Two things about this system bear on the choice. Identifiers reach the browser:
E1's routes address a section, a course and a report by id, and the LTI launch
resolves a section from a platform claim. And confidentiality is the project's
subject — [ADR 0001](0001-identity-separation-by-database-role.md) separates
identity by database role precisely because an accidental join is the failure
mode that matters.

## Decision

Every primary key is a `uuid` column with `server_default gen_random_uuid()`.

The database generates it, not the application: a row inserted by a seed script,
a migration, a `psql` session or the ORM gets an id the same way, and there is
one place to change if that ever moves to a different generator.

## Alternatives rejected

**`bigint` identity columns.** Smaller, faster to join, and sequential inserts
keep a B-tree packed — the right default for most schemas. Rejected because the
ids appear in URLs. A sequential id is enumerable, so a leadership or instructor
URL invites walking the neighbours, and the count itself leaks: an id tells you
roughly how many sections, or responses, the deployment holds. Neither is a
confidentiality *breach* on its own — [§4.1](../SPEC.md)'s invariants are
enforced by the views, not by id opacity — but the cheap way to not have the
argument is to not have the sequence.

**Application-side `uuid4()` defaults on the ORM columns.** The usual SQLAlchemy
idiom, and it lets code know an id before flushing. Rejected because it is only
in force for writes that go through the ORM; a migration, a seed script or the
mock LMS bypassing it would insert a `NULL`. A server default holds for every
writer.

**UUIDv7, for time-ordered keys with the locality `bigint` has.** The genuinely
better answer for the high-volume tables E2 adds (`response`, `answer`), and it
is rejected only for now: `uuidv7()` is a Postgres 18 function and the pinned
image is `postgres:17.10` ([ADR 0007](0007-container-images-pinned-by-tag-and-digest.md)).
Vendoring a PL/pgSQL implementation to get it early would put a hand-written
random-bit generator in the schema, which is more risk than the index locality
is worth at E0's row counts. Revisit when the image moves.

## Consequences

Sixteen bytes per key and per foreign key, and random insert order, so index
pages fill less densely than a sequence would. Invisible at E0's volumes;
`response` and `answer` in E2 are where it could be measured, and where UUIDv7
becomes worth the upgrade.

**Containment and configuration ids are safe to put in URLs and in logs** — an
`institution`, `college`, `department`, `prefix`, `course` or `section` id
identifies a row and says nothing about who or how many.

**Ids that identify a person or a response are not**, and this decision does not
make them so. `user.id` and `response.id` are governed by the rule above — every
primary key is a UUID — but a UUID is a *stable* pseudonym, and stability is the
property that matters here. An instructor who sees the same id against a comment
in week 3 and again in week 7 can group a term's comments by author without ever
joining to an identity column. [SPEC §4](../SPEC.md) spends randomized comment
order and suppressed timestamps preventing exactly that linkage, and §4.1
invariant 6 forbids any view widening it. So those ids do not go into a URL, an
export column, a log line, or anything an instructor or a leadership role can
read, and E1 and E2 should treat this paragraph rather than the one above it as
the governing case.

Ids are **not** a confidentiality mechanism in either direction: nothing should
ever be readable *because* its id is hard to guess, since §4.1 puts that
guarantee in the views and the authorization chokepoint.

A test or a fixture cannot predict an id before inserting. Rows are seeded and
their ids read back, which `tests/integration/test_org_containment_schema.py`
already does with `RETURNING`.
