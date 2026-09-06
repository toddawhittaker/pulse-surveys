# 0133 — A Pulse line item is identified by its id, then by `resourceId`, never by its label

## Context

SPEC §3.4 gives every section one gradebook column called "Pulse Participation".
The tool creates it, and every posting run afterwards has to answer the same
question: is it already there? The requirement the ticket states is that a
renamed or deleted column must never produce a **second** "Pulse Participation"
column on the next run.

Three things can be matched on and the specification blesses none of them for
this purpose.

The **id** is the line item's own URL and it is the platform's. Pulse can store
it (ADR 0128) and read it back, and it is exact. It is also the thing that goes
away: a column deleted in the LMS, a course copied into a new term, a platform
that re-keys its gradebook — each leaves Pulse holding a URL that no longer
answers.

The **label** is what an instructor reads, and an instructor can edit it. Every
LMS in the sector invites them to.

The **`resourceId`** is the member AGS 2.0 provides for a tool's own key on a
line item. It is filterable on the container, no LMS user interface offers it
for editing, and it survives a rename. It is not, however, guaranteed unique by
any platform, and a platform is free to ignore the container filter that selects
on it.

## Decision

Find-or-create runs in this order, and each step exists because the one before
it can legitimately fail.

1. **The id the section holds, fetched.** If `section.ags_line_item_url` is set,
   the client GETs it. A 200 answers the question and the container is not read
   at all. It is fetched rather than believed: a client that returned the stored
   string has established nothing about whether the column still exists.
2. **The container, matched on `resourceId == "pulse-participation"`.** Reached
   when there is no stored id, or when the platform will not serve the one there
   is — an id that answers 404 is not a fault, it is what a deleted or re-keyed
   column looks like, and treating it as fatal would stop posting for that
   section for the rest of the term. The container is asked with AGS 2.0's own
   `resource_id` filter as an optimisation, walked to its last page, and matched
   on `resourceId` in the client — because a platform is free to accept the
   filter and ignore it, and a first-page read of a container that pages would
   find nothing while the column sat on page two.
3. **A create**, carrying `resourceId` `"pulse-participation"`, the label
   `"Pulse Participation"` and `scoreMaximum` 100.
4. **A container that cannot be read to the end is an error, not an empty
   container.** A `Link` header that loops, or one that never stops, ends the run
   with a refusal rather than a create: "this tool could not tell" and "there is
   no Pulse column here" are different facts, and creating on the second when the
   first is true is exactly how a section gets a new column every run.

**The label is never matched on.** It is written once, at creation, and read by
nobody afterwards.

`resourceId` is a module constant in `app/lti/ags.py`. It is not configurable:
two Pulse deployments posting into one course would each want their own key, and
nothing in v1 supports that — a knob added for it now would be a knob with no
correct value.

## Alternatives rejected

**Match on the label.** The obvious reading of "one line item per section called
Pulse Participation", and it is the failure the requirement names: an instructor
renames the column in week three, the next run finds no "Pulse Participation",
creates one, and the class now has two — one holding the term's grades and one
being written to. It is also silent, because both columns look right from every
end.

**Match on the id alone, and treat its absence as fatal.** Exact and brittle.
Every way a stored id can stop answering — a deletion, a course copy, a
platform re-key — becomes a section whose grades stop posting until somebody
notices, and the log says only that a URL 404s.

**Match on the id alone, and create when it is gone.** Recovers from the 404 and
produces the duplicate the requirement forbids, in exactly the case a re-key
causes: the old column is still in the gradebook under the same name.

**Trust the platform's `resource_id` filter and skip the client-side match.** A
page of one line item instead of a walk. AGS permits a platform to ignore its
own container filters, and a platform that accepts and disregards one answers
with the whole container — from which the client would take the first line item
it saw and post a participation grade into somebody else's column. Accepted and
disregarded is the one state a client cannot detect from a status code.

**Store nothing and always walk.** Correct, and it pays a paged container read
per section per posting run, and it makes the fallback into the rule — so the
stored id, which is the exact answer, is never used.

## Consequences

- A renamed column is re-found and keeps its grades. A deleted one is
  re-created. A second "Pulse Participation" column cannot appear from either.
- The ordinary run of a section that has posted before is **one** HTTP call to
  the gradebook: a GET of the stored id. A section on its first run is a walk and
  a create.
- `resourceId` is now a value this system depends on surviving a course copy.
  Platforms that copy line items into a new course carry it, which is what makes
  it work — and a platform that dropped it would leave the new course's first run
  creating a column, which is the right outcome anyway.
- The client persists nothing itself: it answers the line item and its caller
  stores the id (ADR 0128; E3-05 holds the `UPDATE` grant). Until that caller
  exists, every run walks the container, which is correct and slower.
- A container this tool cannot read to the end stops the run for that section
  and leaves an `ags_call` row. That is a louder failure than a truncated read,
  and deliberately so.
