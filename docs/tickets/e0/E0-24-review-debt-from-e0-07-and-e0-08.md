# E0-24 — Review debt from E0-07 and E0-08

**ID:** E0-24
**Branch:** `e0/review-debt-e0-07-e0-08`
**Depends on:** E0-07, E0-08

## Status — what is left here

**Partly moved.** One item is now a batch item, one is a decision for Todd, and
two are carried out of this epic with named owners.

| Item | Now |
|---|---|
| 1 — `jwks_url` is credential-equivalent and unconstrained | **Carried to E1**, which writes and fetches the column and is the only code positioned to say what a legitimate value looks like |
| 2 — nothing asserts there is no second writer of the derived section columns | [E0-35](E0-35-the-writer-and-the-marker-nobody-routed.md) |
| 3 — nothing re-derives a section when a term's start-letter map is edited | **Carried to E2/E11**, the owners ADR 0021 and ADR 0018 already name |
| 4 — the summer start-letter map is invented by the test suite | **Todd's decision** — a real seed map is a spec edit |

Items 1 and 3 are in the README's carried-out-of-E0 table, so a deferral recorded
only in the ticket that deferred it does not become a deferral nobody picks up.

On item 4, this ticket's job until it is answered is unchanged: the invented
constants stay marked as the test suite's choice, and **the gap at position 6
survives any edit** — a contiguous 2-through-5 map is satisfiable by a range
computed from the term's length, which is exactly the wrong implementation those
tests exist to refuse.


## Context

Findings from PR #22 and PR #23 that editing those tickets could not close,
collected the way E0-21 collects E0-05's. None blocks anything. Each is here
because a pull request body is read once at merge and never again, and each of
these needs to be found by someone who was not in that conversation.

Two of the four are the same shape and worth naming as one: **a property that is
true of the code today, correct by design, and defended by nothing.** A later
edit that breaks it produces no failure. That is `docs/MISTAKES.md` entry 2's
subject, and it is what the E0-07 and E0-08 reviews kept finding.

The marker-convention findings from E0-08's security review are **not** here.
They went into E0-10 directly, because E0-10 is the ticket that grants the read
paths that make them exploitable, and a dependency belongs in the ticket that
depends on it.

## Scope

### 1. `jwks_url` is credential-equivalent and unconstrained

`backend/app/models/lti.py`. MEDIUM from E0-08's security review.

Criterion 7 of E0-08 is satisfied — LTI 1.3 is asymmetric, so no client secret is
stored — but "no secret" is a fact about the protocol, not about the table's
trust surface. Control of `jwks_url` is control of the key set every launch
signature is verified against. Anyone who can write `lti_platform` repoints it at
a host they control; E1's launch flow fetches and caches attacker public keys;
every `id_token` they forge validates from then on. That is impersonation of any
student or instructor on the platform, the Care role included.

Nothing today constrains scheme, host, or same-origin-with-`issuer`, and nothing
records that the value changed.

**This wants doing with E1's launch flow, not before it.** E1 writes and fetches
the column and is the only code positioned to say what a legitimate value looks
like. What this ticket owes is that the finding survives until then. If E1 lands
without it, it belongs to whoever adds the admin console that writes the column.

### 2. Nothing asserts there is no *second* writer of the derived section columns

E0-07's scope requires `length_weeks`, `start_date`, `end_date` and `modality` be
populated through `apply_section_code`, "so there is exactly one path that sets
them". Two tests assert the observable half — the columns cannot hold values the
derivation does not produce, at any position in the map. A second writer that
*disagrees* is caught. One that *agrees* is invisible from outside a test.

No bypass exists today; E0-08's security review grepped the backend and scripts
tree and found nothing outside the service assigning any of the four. It is
convention, not enforcement: no trigger, no generated column, no privilege
restriction. ADR 0021 records that trade-off deliberately.

Closing it needs a mechanism E0-07 deliberately left open. The likely home is the
E0-11 chokepoint. The cheaper interim form is a test that fails when a second
assignment site appears — the same shape as
`tests/unit/test_lms_owned_column_marker.py`.

### 3. Nothing re-derives a section when a term's start-letter map is edited

ADR 0021 states it and routes it to E2/E11, the same owners ADR 0018 names for
`week` rows. Recorded here so the three land together rather than being
rediscovered separately: a map is admin-configured data (§2.2, §6.3), so it
*will* be edited after sections exist, and every section deriving from a changed
row silently keeps its old calendar.

### 4. The summer start-letter map is invented by the test suite

E0-07's per-term tests seed a 12-week summer term because §2.2 gives summer 12
weeks but seeds no summer map. The start date (5/11/2026), the three-week block
offsets, and the choice of positions 2, 3, 5 and 7 are all this suite's, and are
marked as such in the constant block.

The non-contiguity is deliberate and load-bearing — see the acceptance criteria
below — so anything that replaces these numbers has to keep it. If the spec grows
a real summer seed map, these become documented values instead of invented ones,
which is the better end state. **That is a spec edit and therefore Todd's call**;
this ticket's job is to make sure the invented numbers are not mistaken for
documented ones in the meantime.

## Out of scope

- The marker-convention gaps — in E0-10, deliberately.
- The `alembic check` blind spots — in E0-20 item 3a, deliberately.
- Anything about how E1 validates a launch. Item 1 records a constraint E1 must
  satisfy; it does not design E1.

## Acceptance criteria

- [ ] `lti_platform.jwks_url` either carries a validation rule with a stated
      threat model, or E1's ticket carries the requirement explicitly and this
      item is closed by pointing at it. Either is acceptable; silently dropping
      it is not.
- [ ] A second assignment site for any of the four derived section columns fails
      something, or ADR 0021 is amended to say plainly that this is unenforced
      and why that is acceptable. Do not leave the ticket's "exactly one path"
      wording standing with nothing behind it.
- [ ] Re-derivation on map edit has a named owner in E2 or E11, recorded where
      that team will find it rather than only in ADR 0021.
- [ ] If the summer map is still invented, its constants remain marked as the
      test suite's choice and the **gap at position 6 survives any edit** —
      a contiguous 2-through-5 map is satisfiable by a range computed from the
      term's length, which is exactly the wrong implementation these tests exist
      to refuse.

## Definition of done

**Tests apply** to items 2 and 4. Item 1 is most likely a constraint plus a test;
item 3 is a record, not code.

**Docs apply** — an ADR amendment if item 2 is answered with "deliberately
unenforced".

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light**, unless item 1 is built here, in which
case it is the review that matters and should be scoped to key handling.
