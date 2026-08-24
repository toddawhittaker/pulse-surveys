# 0049 — The mock platform's gradebook is per-application state, held in memory

## Context

E0-15 gives the mock platform its first *mutable* state. Everything E0-14 built
answers out of the seed or out of the issuer key: the launch page, discovery,
JWKS and the authorization endpoint all read and none of them writes. Line items
and posted scores are different — a tool creates a line item, addresses scores to
it, and reads them back, and all three steps have to agree about something that
did not exist when the process started.

Nothing in SPEC §9.2 or §13 says where that lives. The mock has no database and
no volume; `docker-compose.yml` gives it neither, and E0-14's ADR 0037 settles
that it is configured by Compose literals with nothing in `.env.example`.

## Decision

The gradebook is a plain object built inside `create_app()` and closed over by
the routes, exactly as the issuer key and the seed already are. One application
is one gradebook. Nothing reaches it through a module-level global, so two
platforms started in one test process hold two gradebooks and cannot see each
other's line items.

It is not persisted anywhere. A restarted container is a platform with no line
items and no posted scores, and this record is where that is stated rather than
discovered.

## Alternatives rejected

**A module-level store.** One line shorter and it breaks the property E0-14 spent
a ticket establishing: `tests/conftest.py` starts two platforms in one process to
assert that issuer keys are per run, and a module-level gradebook would make
those two platforms share a gradebook while sharing nothing else. It is also the
shape `docs/MISTAKES.md` entry 20 records as invisible to mutation testing,
because the test fixture re-imports every `app.*` module per platform.

**SQLite in the container.** Survives a restart, and buys nothing anybody needs:
no test spans a restart, E0-18's Playwright run drives one container from a
single `docker compose up`, and a file in a container with no volume does not
survive anything either. It also adds a schema and a migration question to a
service whose whole value is that it is small enough to read in one sitting.

**A named Compose volume.** The same as above with an operational cost attached:
a mock platform that remembers yesterday's line items is a mock platform whose
tests depend on what somebody did yesterday, and the first confusing failure
would be a green suite locally and a red one in CI.

**Seed the "Pulse Participation" line item so nothing has to be created.** It
would remove most of the mutable state, and it contradicts SPEC §3.4, which has
the tool create the line item on first launch. It would also let a test mistake a
fixture for a stored line item — which is exactly the near miss
`test_a_created_line_item_appears_in_the_line_item_listing` reads the listing
twice to rule out.

## Consequences

**The posted-score log grows for as long as the process lives**, and nothing
trims it. Correct for a test session and for a development afternoon; it is the
reason this service must never be run anywhere that stays up, which ADR 0038
already establishes on other grounds.

**The mock cannot be scaled to two replicas.** Two processes would answer
different line items for one context, and a score posted to one would be
invisible to the other. `docker-compose.yml` runs one, and this record is what
says a second is not a scaling decision but a broken one.

Nothing about the mock's state is shared with `backend/`, so no Pulse code path
learns a persistence assumption from it. What E3 may assume is only what a real
platform guarantees: a line item it created is addressable until it deletes it,
within one platform's lifetime.
