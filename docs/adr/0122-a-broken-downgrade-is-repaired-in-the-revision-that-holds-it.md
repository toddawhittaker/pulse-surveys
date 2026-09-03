# 0122 — A broken `downgrade()` is repaired in the revision that holds it, not by a new one

**Status:** Accepted
**Date:** 2026-09-03
**Tickets:** E2-16

## Context

The E2 epic-boundary data-model review found two merged revisions irreversible in
ways that destroy stored data, and verified both by execution on a throwaway
database:

- `3f6907349751` drops `survey_window.term_id` unpreserved and drops
  `question_set`, `question`, `response` and `answer` whole; its `upgrade()` then
  re-adds `term_id` `NOT NULL` with no backfill, so a database holding windows —
  188 of them on the development stack — aborts on the way back up and is
  stranded below every revision E2 added, with the responses already gone.
- `f1a3c7d02b64` drops `response.is_valid` and `classification.answer_id`
  unpreserved; its `upgrade()` backfills `is_valid = true` over every row and
  leaves `answer_id` null. Both fail silently. A submission a model judged
  nonsense comes back counting toward SPEC §3.4's participation, and a floored
  verdict comes back naming no comment — invisible to `app/services/validity.py`'s
  sweep for ever, because both legs filter `answer_id IS NOT NULL` and
  `classification` takes no `UPDATE` ([ADR 0055](0055-a-classification-row-names-its-task-and-no-comment.md)).

Both revisions are merged and pushed. SPEC §13 says the identity-separated views
ship as migrations and says nothing about what may be edited afterwards, and
[ADR 0041](0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md) decides
the immutability question for the `.sql` files a revision *executes* — not for
the revision module itself. So the mechanical question this ticket had to answer
is open: repair the two files, or chain a new revision that does something about
them.

## Decision

**Both `downgrade()` bodies, and the `upgrade()` halves that pair with them, are
edited in the revisions that hold them.** No new revision is chained for either
repair. Each edited revision says so in its own docstring, in the paragraph the
repair belongs to, so a reader who arrives through `git blame` finds the reason
where the change is.

The argument is that a new revision cannot reach the broken code. A `downgrade()`
runs while the database is standing *at* its own revision; anything chained above
it has already run its own downgrade by then and can neither substitute for the
broken body nor wrap it. The same is true of the re-upgrade that aborts: it is
this revision's `upgrade()` that adds the `NOT NULL` column over rows it has just
emptied. There is no position in the chain from which another module can fix
either path.

**What ADR 0041 protects is preserved, and that is what makes the edit legal.**
Its rule exists so that two databases at the same revision cannot hold different
objects. Every statement added here is a preserve, a restore or a backfill, and
each is a no-op on a database that has never been downgraded — the scratch tables
are simply absent, and the tables being backfilled are empty. The one structural
change, `survey_window.term_id` added nullable and altered to `NOT NULL` rather
than added `NOT NULL`, ends in the identical column. So a database at
`f1a3c7d02b64` built before this change and one built after hold the same schema,
which is the property the rule is about.

**The boundary this permits is narrow: a path that has never run anywhere.** A
`downgrade()` nobody has executed, and a re-upgrade that only exists after one,
are code with no applied consequences to protect. Editing an `upgrade()` statement
that *has* run is the thing ADR 0041 forbids and it stays forbidden.

## Alternatives rejected

**A new revision that repairs the schema after the fact.** It is the reflex, and
it does not work: it can only run once the database is already back at head,
which is the state the broken re-upgrade never reaches. On the `f1a3c7d02b64`
half it is worse than useless — the data is gone by then, `classification` takes
no `UPDATE`, and there is nothing left to compute a repair from.

**A new revision that supersedes the old ones' bodies by re-defining them** —
importing and monkey-patching, or a shared helper the old revisions call. It moves
the two paths into a module the revisions read at run time, which is the exact
shape every revision in this tree refuses in a sentence E0-05 wrote first: "a
migration records what was applied on the day it ran, and importing an application
class would make this revision change meaning whenever that class did."

**Squashing the E2 revisions into a new baseline.** It repairs the paths by
deleting them, and it discards the history of what was applied to the development
database and to every reviewer's. The chain is nine revisions old in this epic
alone and a squash forces every existing database to be rebuilt.

**Leaving the downgrades broken and documenting them as one-way.** Considered
seriously, and rejected on the second revision rather than the first. A one-way
migration is a defensible thing to declare; a migration that *silently* corrupts
is not. `f1a3c7d02b64`'s re-upgrade writes `is_valid = true` over every row and
raises nothing, so the operator's database comes back looking whole and counting
wrong, and the floored verdicts are unreachable afterwards by anything.

**A separate `_v002` module beside each, in the shape a superseded `.sql` file
takes.** The naming scheme in ADR 0041 exists because a file is read at upgrade
time and its *content* is what ran. A revision module's content is not read again;
its identifier is what the `alembic_version` row holds. A `_v002` module would be
a second revision with a second identifier — which is the first alternative above,
under a different name.

## Consequences

**A reviewer holding a database at either revision owes it a downgrade and
re-upgrade**, or a `docker compose down -v`, exactly as ADR 0041's own paragraph
about the pre-push window describes. The schema does not change, so the cost is a
rebuild rather than a repair.

**This is a permission to repair a path that has never run, and not a general
licence to edit applied migrations.** Any future use of it has to be able to say
both halves out loud: the broken code is unreachable from any later revision, and
the edit leaves two databases at that revision holding the same objects. An edit
that fails the second test is what ADR 0041 forbids, whatever it fixes.

**A downgrade that removes something now owes a preserve, and the test for
whether one is owed is derivability.** `survey_window.term_id` and the four
dropped tables are preserved because nothing left behind can reconstruct them;
`response.term_id` (`b1e7d4a90c26`) preserves nothing, because it is the row's own
section's term and the upgrade computes it again from the same statement. The
scratch tables are named `<subject>_preserved`, are outside `Base.metadata`, and
are dropped by the upgrade that restores from them — so a database at head never
holds one and `alembic check` never sees one.

**What keeps this working is that the round trip is now asserted rather than
believed.** `tests/integration/test_the_survey_schema_survives_a_downgrade.py`
seeds two terms' worth of windows, responses, answers and verdicts, walks a
database of its own down and back up, and compares whole rows keyed by primary
key — including a third test that makes the trip twice, which is what catches a
preserve written as a one-shot. Before it, both defects were invisible to a green
suite.
