# 0063 — The demo seed runs only where `ENVIRONMENT` is `development`

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-17

## Context

`scripts/seed.py` writes an invented institution, an invented term and eighteen
invented people into whatever database `DATABASE_URL` names, connecting as the
bootstrap superuser ([ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md),
[ADR 0012](0012-the-migration-environment-builds-its-own-superuser-connection.md)).
That identity bypasses every grant [ADR 0001](0001-identity-separation-by-database-role.md)
puts between a read path and a student's name.

E0-17's definition of done asks the security review to "confirm the seed script
cannot run against a non-development environment", and leaves the mechanism
open. [SPEC §6.3](../SPEC.md) makes `ENVIRONMENT` a free-form deployment name
reported by `/healthz`; `.env.example` names `development`, `staging` and
`production` as conventions and nothing enforces the vocabulary.

The failure this is about is not malice. It is `make seed` typed in a terminal
whose `.env` is pointed at staging, and it is a `make seed` line inherited by a
deployment runbook because it was in the development one.

## Decision

`scripts/seed.py` refuses to run unless `ENVIRONMENT` is exactly `development`,
and it checks that **before it builds a database URL**, so a refused run opens no
connection at all.

The check is an equality, not a deny-list. The set of names a deployment might
use is open — `prod`, `production`, `live`, a customer's own word, a typo — so a
check that enumerated names to refuse would let every name nobody thought of
through. The one name that is safe is the one this script exists for.

An empty `ENVIRONMENT` is refused for the same reason: a value somebody set to
nothing is not the one name that is safe.

**What "unset" means here needs saying precisely, because an earlier draft of
this paragraph said two things at once and a test was built against the wrong
one.** The guard reads the variable *after* `load_dotenv(REPO_ROOT / ".env",
override=False)`, which is how every other reader in this repository resolves
configuration (ADR 0008, ADR 0012). So there are two different absences and the
code treats them differently:

| `ENVIRONMENT` in the process | `.env` on disk | Result |
|---|---|---|
| absent | absent, or carrying no `ENVIRONMENT` | **refused** — measured |
| absent | supplying `development` | **admitted** — measured |
| set to anything but `development`, empty included | either | **refused** — measured |

The second row is the one under dispute. `.env` is the development
configuration — `app/config.py`: "in every deployed environment the process
environment is the only source" — so admitting it is what lets `make seed` work
on a stock checkout, and refusing it would make an exported
`ENVIRONMENT=development` the string a developer must type to seed at all, which
is the opt-in flag rejected below under another name. Against that:
`DATABASE_URL` and `ENVIRONMENT` can then come from different sources, so an
operator who exports a production address over a development checkout and never
touches the environment name is admitted.

**That question is open and this record does not settle it.** It is
[`docs/disputes/E0-17-01.md`](../disputes/E0-17-01.md), with both measurements
and both arguments; the table above is what the code does today, whichever way it
is ruled.

`app/db.py` compares against the same literal before it lets the engine echo SQL,
so the string `"development"` now appears twice. Consolidating the two crosses a
module boundary that E0-17 does not otherwise touch, so it is **proposed in
E0-17's pull request rather than done**: `DEVELOPMENT_ENVIRONMENT` belongs beside
the field in `app/config.py`, imported by both readers.

## Alternatives rejected

**An explicit opt-in flag — `--force`, or `PULSE_SEED_I_MEAN_IT=1`.** The
mechanism the test author expected to have to argue with, and it is weaker where
it matters. A flag is a thing a runbook copies once and carries forever, and the
first person to hit the refusal in staging adds it rather than asking why the
refusal was there. It also earns no `.env.example` entry — a variable read only
by a script cannot have one under [ADR 0008](0008-env-has-two-readers-and-the-database-credential-is-split.md)
— so it would be a configuration knob documented nowhere.

**Refusing on the database instead: a non-empty `response` table, a row count, a
seeded marker.** Attractive because it protects the thing that actually matters,
and rejected because it protects it too late. The dangerous case is an *empty*
production database — a fresh deployment, migrated and not yet launched into —
which is precisely the shape this check would wave through.

**Nothing at all, on the argument that a deployment does not run `make`.** True
today and not a guarantee. `make seed` is one line, the image carries the source
tree, and E0-18's exit checklist is the first thing that will want to run it from
somewhere other than a laptop.

**Refusing on the `DATABASE_URL` host — anything but `localhost` or a Compose
service name.** Rejected because it is a check about *where* rather than about
*what*, and the two come apart in both directions: a developer's stack reached
through a tunnel is refused, and a production database reached through a local
port-forward is allowed.

## Consequences

**This guard shipped with nothing in the test suite executing it, and that is now
closed.** The only run this module made with a deployment name sat behind the
mock-platform condition, which is false under
[ADR 0065](0065-the-demo-institution-registers-a-fictional-platform.md), so the
guard was a convention rather than a guarantee — `docs/MISTAKES.md` entry 9,
which is why this paragraph named the gap rather than leaving it to be found. The
hand measurements that stood in for a test have been replaced by ten tests in
`tests/integration/test_demo_seed_script.py`: two controls — a `development` run
is admitted, and a `development` run pointed at an unreachable address gets past
the guard and fails on the address — and six refusal cases, each asserting that
the run failed, that the message names the variable, the value found and the
value wanted, and that no connection was attempted.

**Nine of the ten pass. The tenth is `docs/disputes/E0-17-01.md`** and is the
"absent from the process, supplied by `.env`" row of the table in the Decision
above.

Two things about that round are worth keeping, because neither is visible in the
result:

- **The hand measurement that preceded the tests missed the case the tests
  found.** It ran `ENVIRONMENT=` — the variable present and empty, which
  `load_dotenv` does not override — and reported the unset case as covered.
  Setting a variable to nothing and not setting it at all are different
  questions, and only one of them had been asked. A measurement is better than an
  argument and it is still only as good as the case it chose.
- **The obvious fix turns the whole module green while breaking the one path no
  test covers.** `seed_environment` in `tests/conftest.py` lays every documented
  `.env.example` entry into the child environment, so `ENVIRONMENT` is present in
  the process for every run the suite makes; reading it before `.env` therefore
  passes 29 of 29 and refuses `make seed` on a developer's machine. Anyone acting
  on the ruling should measure that path by hand, because the suite cannot.

**A developer whose `.env` says anything else gets a refusal rather than a seed.**
That is the intended cost. The message names the variable, the value it found and
the value it wants.

**Anyone adding a second thing to this script that a deployment might want** —
a repair, a backfill, a re-derivation after a calendar edit — inherits this
refusal, and should ask whether that thing belongs in a script that may not run
in a deployment at all rather than weakening the check.
