# 0174 — A set definition is recorded on its own row, and the audit log is left alone

## Context

E5-06's ticket asks, in its scope section, for the write trail:

> Audit: the recommendation is that creates, edits and deletes write `audit_log`
> rows — a named set changes what leaders compare, and the trail is cheap.
> Whether the existing audit machinery fits a non-reveal write is this ticket's
> to verify; the ADR line records the choice either way (a decision to not log is
> also a decision).

and its fourth acceptance criterion asks that "the log row for each write
exists — asserted by reading the audit trail, not the return value".

Verifying what the machinery is, which is what the ticket asked for, turns up
four facts about `audit_log` as this repository has it today:

- `app.models.audit.AuditAction` has exactly one member, `IDENTITY_REVEAL`, and
  its docstring says so: "One member, and it is the whole of E0-10's audit
  surface".
- `audit_log.subject_user_id` is `NOT NULL` and its comment names the condition
  for changing that: "a later action that names no subject is a migration that
  relaxes this, in the ticket that adds the action". A set definition names no
  student, so a row for one would have no subject to put there.
- `pulse_app`, the role every request in the product runs on, holds no privilege
  of any kind on `audit_log`. It appears nowhere in
  `RUNTIME_BASE_TABLE_PRIVILEGES`.
- The one thing that can insert a row is the identity reveal's `SECURITY
  DEFINER` function, whose privileges are their own inventory
  (`REVEAL_DEFINER_PRIVILEGES`) and which exists so that the Care connection
  cannot write, forge or suppress the record the door writes for it.

So writing an audit row for a set definition is not a line of code. It is a new
`AuditAction` member, a migration making `subject_user_id` nullable, and either
an `INSERT` granted to `pulse_app` or a second definer function — three changes
to the shape of the audit guarantee, arriving inside a management API.

SPEC §8's own sentence about the table is:

> `audit_log` is append-only and includes all re-identifications, exclusions and
> kept-decisions, policy changes, response-on-behalf actions, imports (with
> their dry-run diffs), and admin config edits.

## Decision

**E5-06 writes no `audit_log` row for a create, an edit or a delete.** What is
recorded is on the set's own row: `created_by_person_id` and `created_at` when a
set is defined, and `updated_at`, set from the clock service, whenever it is
edited. Those columns are E5-01's and exist for this (ADR 0164).

**The widening is left to the change that wants it.** Growing `audit_log` a
non-reveal action family — a nullable subject, an action value, and whatever may
write one — is a decision about the audit guarantee, and it belongs in a change
whose subject is that guarantee, reviewed as such.

**The gap a delete leaves is named rather than papered over.**
`docs/tickets/e5/deferred.md` carries it: a deleted set leaves no trace at all,
and criterion 4's literal wording is not satisfied for that one write. It is not
faked by a row that records something else.

## Alternatives rejected

**Write the audit row, making the three changes the machinery needs.** It is
what the ticket recommended and it is the honest reading of criterion 4. It is
rejected on scope, not on merit: a `NOT NULL` relaxed on the column that names
whose identity was revealed, and an `INSERT` on the append-only table handed to
the role that serves every request in the product, are exactly the kind of
change that is reviewed carefully when it is the subject of a pull request and
waved through when it is the fourth item in one about a management API. The
grant is the sharper half — `pulse_app` gaining `INSERT` on `audit_log` means
any request path in the application can append to the trail, including the ones
that exist to be refused.

**A second `SECURITY DEFINER` function for set writes**, avoiding the grant. It
avoids the worst half and keeps the rest: the action member, the nullable
subject, a function, its own privilege inventory and its own tests. That is a
ticket, and it is the shape the change should take when somebody writes it — not
a thing to add here.

**Record set writes somewhere else — a table of this ticket's own.** Rejected as
YAGNI in the worst direction: a second audit table is a second answer to "where
is the trail", and the first thing two trails do is disagree about which one is
authoritative.

**Call criterion 4 satisfied by the row's own columns and say nothing.** The
columns do satisfy it for a create and an edit, which is why they are what this
records. They do not satisfy it for a delete, and a record that claimed
otherwise would be this decision quietly becoming a false statement about the
system.

## Consequences

A deleted set leaves nothing behind. Nobody can answer "who deleted the College
of Nursing set, and when" from the database. That is the cost of this decision,
it is stated here and in `deferred.md` with a done-when, and E10's audit review
surface is where it is owned.

An edit records that a set changed and not what it changed from. `updated_at`
moves and the old name, the old pair and the old membership are gone. A set's
history is not reconstructible, which is the same cost one level down.

Whether a set definition is one of the events §8's sentence lists is a reading
rather than a plain fact, and the reading is this: it is not a
re-identification, an exclusion or kept-decision, a response on behalf of
anybody, or an import. The two neighbours that could be argued are "policy
changes" and "admin config edits", and a comparison cohort is neither a policy
nor configuration — it is data leadership creates while using the product, in
the way an instructor's response is. The argument is written down here so that
whoever disagrees has something to disagree with; if the spec means to cover set
definitions there, that is a spec edit and the ticket that makes it is the one
that widens the table.

The row's own columns carry a second job now — they are the scope key (ADR 0173)
*and* the record — and the two are not separable. A repair that changed how a
creator is stored would be changing both at once.
