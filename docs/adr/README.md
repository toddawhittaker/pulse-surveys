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

**0029, 0033 and 0034 do not exist, and no record is missing.** Three tickets
were built in parallel worktrees and each was given a range to number within —
0025–0029, 0030–0034, 0035–0039 — so that two branches could not both claim one
number. Each ticket used fewer than its range allowed and the remainder was left
unused rather than back-filled, because renumbering is the one thing this file
forbids. A gap in the sequence means a range ran out early, never that a record
was lost.

A superseded record stays where it is with a line at the top pointing at its
replacement. Where a later decision changes only *part* of an earlier one, say
amended rather than superseded, on the earlier record's status line and beside
the specific paragraph that moved — and in the table, so the qualifier is
visible without opening the file. Calling a record superseded when its decision
still stands sends a reader looking for a replacement that does not exist.

## Records

| # | Decision | Status |
|---|---|---|
| [0001](0001-identity-separation-by-database-role.md) | Identity separation enforced by database role and grant | Accepted — one consequence amended by [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md) and again by [0040](0040-pulse-migrate-is-the-bootstrap-identity-under-another-name.md), which also resolves `pulse_migrate`; [0043](0043-the-reveal-function-has-an-owner-of-its-own.md) adds the definer role it does not name |
| [0002](0002-ci-gates-ship-tolerant.md) | CI gates ship tolerant and name the ticket that enforces them | Accepted, recorded retroactively |
| [0003](0003-deferred-authz-seams-fail-closed.md) | Deferred authorization seams fail closed by raising | Accepted |
| [0004](0004-agent-roster-mechanism.md) | Agent roster mechanism: hooks, computed gating, session-scoped warmth | Accepted |
| [0005](0005-dependency-locking.md) | Python dependencies are locked with pip-compile, hashes and all | Accepted |
| [0006](0006-settings-lifetime.md) | Settings are built inside `create_app()` and hung on `app.state` | Accepted |
| [0007](0007-container-images-pinned-by-tag-and-digest.md) | Container images are pinned by tag and by digest | Accepted |
| [0008](0008-env-has-two-readers-and-the-database-credential-is-split.md) | `.env` has two readers, and the database credential is split into parts | Accepted — the count amended to three by [0012](0012-the-migration-environment-builds-its-own-superuser-connection.md) |
| [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md) | A superuser identity is sanctioned for migrations and bootstrap | Accepted — one row of its provisioning table amended by [0040](0040-pulse-migrate-is-the-bootstrap-identity-under-another-name.md) |
| [0010](0010-the-celery-application-is-built-at-import-time.md) | The Celery application is built at import time, at module level | Accepted — answers for Celery the entry-point question [0006](0006-settings-lifetime.md) left open |
| [0011](0011-ci-validates-the-image-by-running-the-base-compose-file-alone.md) | CI validates the image by running the base Compose file alone | Accepted |
| [0012](0012-the-migration-environment-builds-its-own-superuser-connection.md) | The migration environment builds its own superuser connection | Accepted — settles the two open rows in [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)'s provisioning table |
| [0013](0013-the-database-session-is-synchronous.md) | The database session is synchronous, and the engine is built at import | Accepted — answers for the database the entry-point question [0006](0006-settings-lifetime.md) left open |
| [0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md) | LMS-owned columns are marked by an `lms_` name prefix | Accepted — a convention; E0-11 chose a table grain instead of the marker's ([0045](0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)), so the enforcing check this record defers is still open and E0-21 carries it |
| [0015](0015-course-level-is-a-stored-generated-column.md) | Course level is a stored generated column, and the bands are its only authority | Accepted |
| [0016](0016-primary-keys-are-database-generated-uuids.md) | Primary keys are database-generated UUIDs | Accepted — UUIDv7 revisited when the Postgres image moves to 18 |
| [0017](0017-prefix-codes-are-unique-across-the-deployment.md) | Prefix codes are unique across the deployment, not per institution | Accepted — rests on one institution per deployment, stated in the record |
| [0018](0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md) | Cross-table length rules are enforced by a composite foreign key carrying the term's length | Accepted |
| [0019](0019-a-naive-datetime-is-refused-by-the-column-type.md) | A naive datetime is refused by the column type, not by Postgres or a service | Accepted |
| [0020](0020-a-sections-end-date-is-its-last-day.md) | A section's end date is its last day, inclusive | Accepted |
| [0021](0021-a-sections-derived-calendar-has-one-writer.md) | A section's derived calendar is NOT NULL and has exactly one writer | Accepted |
| [0022](0022-identity-bearing-columns-are-marked-by-a-name-prefix.md) | Identity-bearing columns are marked by an `identity_` name prefix | Accepted — follows [0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md), and takes the name where the two markers meet; the discovery rule beside it widened in E0-10, the marker itself unchanged |
| [0023](0023-overlapping-enrollments-are-refused-by-an-exclusion-constraint.md) | Overlapping enrollment windows are refused, by a GiST exclusion constraint | Accepted — settles the choice E0-08's criterion 5 leaves open |
| [0024](0024-the-person-to-user-link-is-carried-by-person.md) | The person-to-user link is carried by `person`, and is one to one | Accepted — rests on one registered platform per person, stated in the record |
| [0025](0025-an-assignments-scope-is-one-nullable-foreign-key-per-level.md) | An assignment's scope is one nullable foreign key per containment level | Accepted — settles what SPEC §8's singular `scope_node_id` references |
| [0026](0026-entry-doors-are-derived-from-the-role-as-generated-columns.md) | Entry doors are derived from the role, as stored generated columns | Accepted — follows [0015](0015-course-level-is-a-stored-generated-column.md) |
| [0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md) | Supervision edges are policed by one row-level trigger, holding an advisory lock | Accepted — takes the trigger [0015](0015-course-level-is-a-stored-generated-column.md) rejected, for a rule that spans rows; every relation schema-qualified against a `pg_temp` hijack; holds under READ COMMITTED and SERIALIZABLE, and refuses REPEATABLE READ rather than being silently wrong under it; extended by [0044](0044-a-supervision-edge-must-climb-the-role-rank.md), which added two rules to the same function and made the cycle walk defence in depth |
| [0028](0028-a-student-holds-no-role-assignment.md) | A student holds no role assignment | Accepted — a student's access is resolved from `enrollment` |
| [0030](0030-a-verdict-is-an-enum-whose-value-is-the-stored-token.md) | A verdict is an `enum.Enum` whose value is the stored token | Accepted |
| [0031](0031-every-task-contract-carries-the-prompt-version-and-model-id.md) | Every task contract carries the prompt version and model ID, and the gateway supplies them | Accepted — reads E0-12's "every model" over §7.4's narrower "every classification" |
| [0032](0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md) | Prompts are named `<task>.v<N>.md` and a committed prompt file is never edited | Accepted — half enforced by test, half convention, said so in the record |
| [0035](0035-the-mock-platform-signs-with-standard-library-rsa.md) | The mock platform signs with standard-library RSA | Accepted — bounded to `mock-lms/`, and the bound is part of the decision |
| [0036](0036-the-mock-platform-publishes-its-registration-as-a-document.md) | The mock platform publishes its registration as a document keyed by column | Accepted |
| [0037](0037-the-mock-platform-is-configured-by-compose-literals.md) | The mock platform is configured by Compose literals, and earns no `.env.example` entry | Accepted — applies the rule in [0008](0008-env-has-two-readers-and-the-database-credential-is-split.md) |
| [0038](0038-the-mock-platform-ships-in-the-base-compose-file.md) | The mock platform ships in the base Compose file, and is kept out of a deployment by what it holds | Accepted |
| [0039](0039-the-two-app-packages-are-typechecked-in-two-runs.md) | The two `app` packages are typechecked in two mypy runs | Accepted |
| [0040](0040-pulse-migrate-is-the-bootstrap-identity-under-another-name.md) | `pulse_migrate` is the bootstrap identity under another name, and is not created | Accepted — amends one row of [0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)'s provisioning table and resolves the third role named in [0001](0001-identity-separation-by-database-role.md), its own role count amended by [0043](0043-the-reveal-function-has-an-owner-of-its-own.md) |
| [0041](0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md) | A read view ships as an immutable, versioned `.sql` file that a migration executes | Accepted — follows [0032](0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md); the layout is a decision this record holds and the suite does not enforce, measured and said so |
| [0042](0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md) | The Care pool has a credential of its own, and opens on first use | Accepted — answers for the Care queue the entry-point question [0006](0006-settings-lifetime.md) left open; one rejected alternative reversed by E0-10, so `api` alone holds the credential and `CARE_DATABASE_URL` is optional |
| [0043](0043-the-reveal-function-has-an-owner-of-its-own.md) | The reveal function has an owner of its own, holding three grants | Accepted — amends the role count in [0040](0040-pulse-migrate-is-the-bootstrap-identity-under-another-name.md); the views deliberately keep the migration identity, and the record says what that leaves open |
| [0044](0044-a-supervision-edge-must-climb-the-role-rank.md) | A supervision edge must climb the role rank, and the trigger is what refuses one that does not | Accepted — extends [0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md); settles the choice E0-09 left in neither place; bounds the graph at six deep and subsumes acyclicity; the same-role half was disputed and upheld ([E0-11-01](../disputes/E0-11-01.md)), the ruling finding that `LEAD_FACULTY → LEAD_FACULTY` is refused by §4.1 invariant 2 and every other same-role pair is spec-silent |
| [0045](0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md) | The chokepoint refuses an LMS-owned write at table grain, plus one row | Accepted — chooses the grain E0-11 refuses to inherit from [0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md)'s marker, and says what it does not catch; [0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md)'s open half stays open |
| [0046](0046-a-purview-is-a-materialised-node-set-per-containment-level.md) | A purview is a materialised, downward-closed node set per containment level | Accepted — the value every read path is handed; Care is deliberately not one of its fields, and the deferred union it composes with is [0003](0003-deferred-authz-seams-fail-closed.md)'s |
