# 0128 — The line item's id lives on the section row

## Context

SPEC §3.4 gives every section one AGS line item called "Pulse Participation",
created by this tool in the container the launch advertises. Once it exists,
its own URL is what every later post addresses. E3-04 creates it, E3-06 posts
to it many times a term, and neither can afford to re-read a container on
every run to find it again — so it has to be stored somewhere.

The spec names `grade_sync` and `ags_call` in its table list and says nothing
about where a line item id is kept. E3-02 builds the schema everything else in
the epic writes to, so it is the ticket that has to decide, and the ticket text
records both candidates as defensible.

There are two places it can go, and the choice is contestable in both
directions. `section` is a table SPEC §2.1 puts on the LMS's side, whose
columns are mirrors of what a platform published, and the id of a line item
Pulse created is not that. A Pulse-owned table of its own avoids putting a
Pulse value on a platform-mirroring row, and it needs no addition to the write
sanction — but it is a table with one useful column, one foreign key and one
reader.

## Decision

The line item's id is a nullable text column on `section`, named
`ags_line_item_url`, beside `lms_ags_line_items_url` — the container address
the launch supplies.

It carries **no `lms_` prefix**, and that is the whole of how the two are told
apart. The container is the platform's and Pulse never edits it, which is what
the marker means (ADR 0014). The line item is this tool's own creation in that
container, so the marker would be a lie and its absence is the record that
Pulse owns the value.

E3-02 creates the column and writes nothing to it. E3-05 is its writer, and
the `UPDATE` privilege it needs is granted in that ticket rather than this one:
a grant issued now would be one nothing in the tree uses.

NULL means no line item has been created for this section yet, which is a state
and not a fault — the same reading the container address beside it takes.

## Alternatives rejected

**A Pulse-owned table, one row per section, holding the line item id.** The
tidier answer on ownership: no Pulse value on a platform-mirroring row, and no
column-scoped grant on `section` to justify. It costs a table whose whole
content is a foreign key and one URL, with exactly one reader — the poster —
and a second lookup on every post to get a value the section row already had to
be fetched for. It also splits one section's two gradebook addresses across two
tables, so a question as simple as "can this section be posted to" becomes a
join. A table nobody reads except the writer that filled it is the shape this
project has been trimming rather than adding.

**A column on `grade_sync`.** Rejected quickly and recorded because it looks
economical. That table is append-only at the grain of one post (ADR 0124), so
the line item id would be repeated on every row and the current value would be
"whatever the latest row says" — which makes a fact about a section into a
derived read of a log, and leaves a section with no posts yet holding the id
nowhere.

**Re-read the container before every post.** Removes the column and any
ownership question with it. It makes every sweep a listing request per section
against a third-party service before it can post anything, it depends on a read
scope a platform may not grant, and it answers "which line item is ours" by
matching on a label that a human in the platform can rename.

## Consequences

**`section` now carries two gradebook addresses with different owners**, and
the naming convention is the only thing that says which is which. That is a
convention a reader has to know, and it is the one this schema already uses
throughout — `course.level` beside `course.lms_number` is the same split.

**E3-05 spends a column-scoped `UPDATE` on `section`** and records it in the
grant inventory with the sentence it rests on. The alternative table would have
needed no such grant, and this is the cost that ADR names.

**A section can hold a container address and no line item id**, which is the
ordinary state between a first staff launch and the first sweep that creates
the line item. Nothing about that is a fault, and E11's console reads it as
work not yet done rather than as a failure.

**Nothing was added to `SANCTIONED_WRITERS`.** The catalog entry for
`launch_provisioning` already grants `section`, and E3-05's writer will need
its own entry only if it is not one of the writers already sanctioned for that
table — which is that ticket's question, not this one's.
