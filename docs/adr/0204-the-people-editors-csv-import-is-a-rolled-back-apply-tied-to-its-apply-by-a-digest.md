# 0204 — The people editor's CSV import is a rolled-back apply, tied to its apply by a digest

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-06](../tickets/e9/E9-06-people-and-mapping-editor-backend.md)

## Context

[SPEC §6.3](../SPEC.md) gives the People & reporting table and the Lead Faculty
mapping table "CSV import/export where import always shows a dry-run diff
before applying", and §2.1 gives the diff's shape ("2 mappings added · 1 changed
· BIOL 441 unmapped, falls to chair"). The spec does not say what a file's keys
are, what a record missing from a file means, how a dry run is computed, or what
ties an apply to the dry run the admin reviewed. The writes themselves are
[ADR 0200](0200-the-admins-people-graph-definers.md)'s definers.

## Decision

**Keys are the records' own ids.** The people file is `person_id,name,category`;
a blank `person_id` is a new person. The mapping file is
`course_id,course,person_id,lead`; `course` and `lead` are labels for the reader
and are never read back, and a blank `person_id` unmaps the course. Each file's
header must be exactly the export's.

**A file states only the records it names.** A person or course the file does
not name is left alone, so removing a mapping is a blank lead, never a missing
line, and a file of ten lines cannot unmap the rest of the institution. People
are never removed by an import; no definer deletes a person.

**The dry run is the apply, rolled back.** The service applies the file through
the definers inside the request's transaction, reads the named records back,
diffs them against what it read first, and rolls back. Audit rows written along
the way are rolled back with everything else.

**The digest ties the apply to its dry run.** It is SHA-256 over the file's text
and the named records' state before the dry run; for a people file that state
also holds every person already bearing a new line's name. The apply sends the same file
and the digest; inside a `SERIALIZABLE` transaction it reads the state again,
refuses (409) if the digest differs, and otherwise applies and commits. A
serialization failure at any point is the same refusal. The apply answers the
same diff the dry run answered.

*Amended by E9-14:* the apply compares the digest after its last line and before
it records or commits anything, rather than before its first write. The digest
is still computed from the state read before the first write, so a stale apply
still commits nothing; what changes is only which refusal a file with both
faults hears. A file one of whose lines the definers refuse is answered with that
line (422) whatever digest came with it, so a file that can never be applied
says why, rather than asking for a dry run that would refuse it anyway.

**Strict reading, all or nothing.** A line with the wrong number of cells, a key
not written the way the export writes it, a repeated key, or a name or category
with spaces at either end is refused (422) naming its line, and nothing is
applied. A line the database refuses names its line too, and the lines before it
are rolled back. Nothing is repaired into a valid value (MISTAKES entry 29).

**Spreadsheet formulas are escaped.** The export writes a cell starting with
`=`, `+`, `-`, `@`, a tab, a carriage return or `'` with one `'` in front; the
import removes exactly that one and refuses a cell that starts with one of
those characters unescaped, so the encoding reads back to the same value.

## Alternatives rejected

- **A file replaces the whole table.** Export and re-import would still be an
  empty diff, but a partial file would silently unmap or orphan every record it
  left out, and an apply would be refused whenever anybody touched any mapping.
- **Computing the diff in Python without writing.** It would duplicate every
  rule the definers and ADR 0044's trigger already hold, and a diff that the
  database would refuse would look applicable.
- **A stored dry-run token.** It needs a table and an expiry for what a hash of
  the file and the state already proves.
- **Natural keys (a course's code, a person's name).** Names are not unique, and
  a course code can be renamed by the platform.

## Consequences

- An unchanged record costs no write and no audit row; a changed lead is an
  unmap and a map, two audit rows (ADR 0200).
- A new person has no id until applied, so a people diff lists new people by
  name and category only.
- Applying the same file twice is refused the second time: the first apply
  changed the named records, or created a person bearing a new line's name, and
  either changes the digest.
- Assignments and reporting lines are edited in the editor, not by import; the
  people file carries names and categories only.
- An applied import leaves one `IMPORT_APPLIED` audit row naming the admin, with
  the kind and the diff it answered in `audit_log.detail`, written by
  `admin_record_import` (`people_graph_v002.sql`) inside the apply's transaction
  before its commit, so a dry run or a refused apply leaves none (SPEC §8).
