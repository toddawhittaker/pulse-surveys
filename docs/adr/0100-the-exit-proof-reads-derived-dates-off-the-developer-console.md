# 0100 — The exit proof reads derived dates off the developer console

## Context

SPEC §14.3's exit line for E1 requires that "a synced section shows correct
derived dates", and §9.2 makes the proof a browser proof against
`docker compose up`. E1-15 is the ticket that proves it, and its own scope says
it proves and does not build: "a clause that cannot be proven without new code is
a finding against the ticket that owed the code".

Nothing in E1 renders a section's calendar. All five landing views are empty by
design (E1-04), so there is no product screen a browser could read the dates off,
and there is no ticket in E1 that owed one — the derivation itself is E0-07's and
is asserted in Python by `tests/integration/test_section_date_derivation.py`. The
gap is not a missing capability; it is that nothing in a browser can currently see
a value the system demonstrably holds.

The spec is silent on where a proof of that kind should read from, and the choice
is contestable: the surface a proof reads is a surface, and a development console
is where "just this once, to make debugging easier" adds a column.

## Decision

The proof reads the dates off `GET /dev`, the development-only console ADR 0079
gates in the handler body. E1-15 adds a sections table to that page: one row per
`section`, keyed `dev-section-{PREFIX}-{NUMBER}-{CODE}`, carrying the start date,
the end date, the length in weeks, the modality, an enrolled **count** from
`public.section_enrollment_count`, and a yes/no on whether a roster address is
stored.

The table carries **no identity column of any kind** — no subject, no name, no
address, and not the stored roster address itself, which is a service endpoint
carrying the platform's own context identifier. That is a rule with an assertion
behind it rather than a note: `tests/integration/test_the_dev_console_names_nobody.py`
runs a real roster sync, reads the identity strings the tool stored out of the
database, requires the table present, and requires none of them on it.

It is the same route and the same `is_development` gate. No new route is
registered, so nothing here reopens ADR 0087's verdict on what `/dev` discloses
to a method it does not serve.

## Alternatives rejected

- **A JSON endpoint for the dev console's data.** A second gated route, which
  needs its own answer to the method-mismatch disclosure ADR 0087 measured and
  settled for exactly one path — and a machine-readable copy of a page that
  already exists, kept in step by nobody.
- **Asserting the dates from the database, outside the browser.** That is the
  test `tests/integration/test_section_date_derivation.py` already is. §9.2 asks
  for the browser because the chain — staff launch, provisioning, the stored
  roster address, the sync worker, the derivation — is what an exit proof is
  about, and a direct database read skips most of it.
- **Building a product surface that renders section dates.** New capability
  inside a ticket whose scope forbids it, designed against no brief in
  `docs/DESIGN_BRIEF.md`, and reviewed as part of a proof rather than on its own
  merits.
- **Deferring the clause to E2.** The exit line is E1's, and a clause carried
  past the epic boundary is the failure `docs/tickets/e0/README.md` recorded:
  §14.3 implied an exit criterion and no ticket proved it.

## Consequences

- **The console is now a read path over roster-derived rows**, which it was not
  before. What keeps it honest is the invariant test above and the browser-level
  guard in `tests/e2e/exit-synced-section-dates.spec.ts`; both are non-vacuous
  only because the sync runs first and the count is required non-zero.
- **The enrolled figure has to keep coming from the view.** A count read off
  `public.enrollment` would work identically and would put the count somewhere
  §4.1 invariant 4 does not govern. `dev.py` spells that view's `SELECT` itself
  rather than importing `app.views_sql.queries`, which
  `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` keeps to one
  importer.
- **A row key is a prefix, a number and a section code**, so two sections of one
  course sharing a code across two terms would share a row key. The development
  stack seeds one term; the alternative puts a term into every spec that has
  nothing to say about one.
- **The exit proof depends on a development-only surface.** That is stated
  plainly: the clause is proven on the stack §9.2 names, and a deployment serves
  no such page. If a product surface later renders a section's calendar, the
  spec-level proof should move to it and this table can go back to being a
  developer convenience.
