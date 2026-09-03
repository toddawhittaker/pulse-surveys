# 43. A broad guard's pattern matched ordinary prose, and named a file that runs no SQL

## Instance: FIX-01's schema description tripped the org-views SQL sweep (2026-09-03)

`backend/app/schemas/student.py` gained a one-line Pydantic `Field`
description for the respelled `course_label`:

> The reader's own course as a person names it: prefix, number, section code,
> title, term name.

That module contains no SQL, imports no query, and touches no database. The
whole unit and integration pass — four and a half minutes under `-n 4` — came
back with one failure:

```
{'backend/app/schemas/student.py': ['section']} run SQL naming a relation the
org views are built on.
```

`tests/unit/test_the_org_views_are_read_only_through_the_grant.py` sweeps every
**non-docstring** string constant under `backend/app/` for a policed relation in
a position that reads or writes it, and one of the positions it counts is
`,\s*` — the comma-separated `FROM` list that E0-42's security pass used to get
past an earlier version of the sweep. So the prose list "prefix, number, section
code" reads, to that pattern, as `…, section`.

The fix was one word of prose: "prefix, number, the section code, title and term
name". A comment above the field says why the wording is what it is, so the next
person to tidy it up finds out before their own suite run does.

## Root cause

The sweep excuses docstrings, because a module that deliberately goes through
the grant is expected to name the relations in prose. It excuses nothing else,
and a schema's `Field(description=...)`, an enum's label, a log message and a
copy string are all prose that is not a docstring. The comma alternative was
added to close a real hole and must stay; what it costs is that any English
list whose next word is a relation name reads as SQL.

Neither half is wrong. The guard is right to be broad — the thing it protects
is the only barrier between a caller and the whole institution — and the
description was right to name the parts of the label. What was missing was
anybody checking the two against each other before spending a full suite run.

## Consequence

Four and a half minutes of full-suite time, and a failure whose text points at a
confidentiality guard for a change with no confidentiality dimension at all. The
worse outcome is the one that did not happen here: a report reading "the sweep
found a module naming `section`" is exactly what a real leak looks like, and
somebody in a hurry could equally have widened the sweep's exemptions — which
would have been the guard narrowed to accommodate a sentence.

## The whole rule

**Prose in a non-docstring string under `backend/app/` is read by the SQL
sweep.** Before a full-suite run, re-read any `Field(description=...)`, log
message, error sentence or other string literal you added there for a policed
relation name — `assignment_scope`, `college`, `containment_path`, `course`,
`department`, `enrollment`, `institution`, `lead_faculty_course`,
`lead_faculty_mapping`, `prefix`, `role_assignment`, `section`,
`section_enrollment_count`, `section_roster` — sitting after a comma, or after
`from`, `join`, `into`, `update`, `table` or `using`. Running
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py` alone takes a
fraction of a second and answers it.

**Reword the prose; never widen the guard.** An exemption added so that a
sentence can keep its comma is an exemption a real query can then sit behind,
and the sweep's own docstring says the only acceptable widening is a fifth
exempt location decided in the open. Leave a comment beside the reworded string
saying why it is worded that way, or the next edit puts the comma back.
