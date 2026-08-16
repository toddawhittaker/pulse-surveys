# Architecture decision records

A record of construction decisions that [`docs/SPEC.md`](../SPEC.md) does not
answer and that a reasonable engineer might have made differently.

## When to write one

Both halves have to be true: the spec is silent, **and** the choice is genuinely
contestable. Choosing a JSON library needs no record. Choosing how identity
separation is enforced in the database does.

Write it in the same pull request as the decision, not afterwards. An ADR
written later is a reconstruction, and reconstructions leave out the option that
seemed obvious at the time and turned out to be wrong.

## When not to write one

- **The spec already decides it.** Link to the spec section instead. An ADR that
  paraphrases a spec section is noise that makes the real ones harder to find.
- **The decision contradicts the spec.** An ADR is not sufficient and not the
  right instrument. Raise it, and update the spec — a record of having gone
  around the spec is not the same as the spec being right.

## Format

`NNNN-slug.md`, four sections, under a page:

1. **Context** — what forced a choice, and which spec section left it open.
2. **Decision** — what was chosen, stated plainly.
3. **Alternatives rejected** — each with the reason it lost. This is the section
   that earns the document; a list of alternatives with no reasoning is a list.
4. **Consequences** — what this costs, what it constrains later, and what has to
   be true for it to keep working.

Number sequentially, never reuse a number, never renumber. **Add a row to the
table below in the same commit** — an unindexed record is one nobody finds, and
three of them accumulated on one branch before anyone noticed, because the index
is the artifact nobody re-reads once it exists.

A superseded record stays where it is with a line at the top pointing at its
replacement. Where a later decision changes only *part* of an earlier one, say
amended rather than superseded, on the earlier record's status line and beside
the specific paragraph that moved — and in the table, so the qualifier is
visible without opening the file. Calling a record superseded when its decision
still stands sends a reader looking for a replacement that does not exist.

## Records

| # | Decision | Status |
|---|---|---|
| [0001](0001-identity-separation-by-database-role.md) | Identity separation enforced by database role and grant | Accepted — one consequence amended by [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md) |
| [0002](0002-ci-gates-ship-tolerant.md) | CI gates ship tolerant and name the ticket that enforces them | Accepted, recorded retroactively |
| [0003](0003-deferred-authz-seams-fail-closed.md) | Deferred authorization seams fail closed by raising | Accepted |
| [0004](0004-agent-roster-mechanism.md) | Agent roster mechanism: hooks, computed gating, session-scoped warmth | Accepted |
| [0005](0005-dependency-locking.md) | Python dependencies are locked with pip-compile, hashes and all | Accepted |
| [0006](0006-settings-lifetime.md) | Settings are built inside `create_app()` and hung on `app.state` | Accepted |
| [0007](0007-container-images-pinned-by-tag-and-digest.md) | Container images are pinned by tag and by digest | Accepted |
| [0008](0008-env-has-two-readers-and-the-database-credential-is-split.md) | `.env` has two readers, and the database credential is split into parts | Accepted — the count amended to three by [0012](0012-the-migration-environment-builds-its-own-superuser-connection.md) |
| [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md) | A superuser identity is sanctioned for migrations and bootstrap | Accepted |
| [0010](0010-the-celery-application-is-built-at-import-time.md) | The Celery application is built at import time, at module level | Accepted — answers for Celery the entry-point question [0006](0006-settings-lifetime.md) left open |
| [0011](0011-ci-validates-the-image-by-running-the-base-compose-file-alone.md) | CI validates the image by running the base Compose file alone | Accepted |
| [0012](0012-the-migration-environment-builds-its-own-superuser-connection.md) | The migration environment builds its own superuser connection | Accepted — settles the two open rows in [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)'s provisioning table |
| [0013](0013-the-database-session-is-synchronous.md) | The database session is synchronous, and the engine is built at import | Accepted — answers for the database the entry-point question [0006](0006-settings-lifetime.md) left open |
| [0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md) | LMS-owned columns are marked by an `lms_` name prefix | Accepted — a convention, with the enforcing check deferred to E0-11 |
| [0015](0015-course-level-is-a-stored-generated-column.md) | Course level is a stored generated column, and the bands are its only authority | Accepted |
| [0016](0016-primary-keys-are-database-generated-uuids.md) | Primary keys are database-generated UUIDs | Accepted — UUIDv7 revisited when the Postgres image moves to 18 |
| [0017](0017-prefix-codes-are-unique-across-the-deployment.md) | Prefix codes are unique across the deployment, not per institution | Accepted — rests on one institution per deployment, stated in the record |
| [0018](0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md) | Cross-table length rules are enforced by a composite foreign key carrying the term's length | Accepted |
| [0019](0019-a-naive-datetime-is-refused-by-the-column-type.md) | A naive datetime is refused by the column type, not by Postgres or a service | Accepted |
| [0020](0020-identity-bearing-columns-are-marked-by-a-name-prefix.md) | Identity-bearing columns are marked by an `identity_` name prefix | Accepted — follows [0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md), and takes the name where the two markers meet |
| [0021](0021-overlapping-enrollments-are-refused-by-an-exclusion-constraint.md) | Overlapping enrollment windows are refused, by a GiST exclusion constraint | Accepted — settles the choice E0-08's criterion 5 leaves open |
| [0022](0022-the-person-to-user-link-is-carried-by-person.md) | The person-to-user link is carried by `person`, and is one to one | Accepted — rests on one registered platform per person, stated in the record |
