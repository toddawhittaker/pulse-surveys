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
open.

**`ENVIRONMENT` is not a spec concept, and an earlier version of this record said
it was.** It cited [SPEC §6.3](../SPEC.md) for the variable being a free-form
deployment name reported by `/healthz`. §6.3 is three bullets on the admin
console's configuration surface — the term calendar, the n-threshold, the AI
provider, the LTI registration, the people editor, the catalog viewer — and names
no environment variable; `ENVIRONMENT` and `healthz` each appear **zero** times in
the whole of `docs/SPEC.md`. Both sides of the dispute below argued partly from a
sentence that does not exist. The real source is E0-01:
`app.config.Settings.environment`, documented in `.env.example`, which names
`development`, `staging` and `production` as conventions and enforces none.

The failure this is about is not malice. It is `make seed` typed in a terminal
whose `.env` is pointed at staging, and it is a `make seed` line inherited by a
deployment runbook because it was in the development one.

## Decision

`scripts/seed.py` refuses to run unless `ENVIRONMENT` is `development`, and it
checks that **before it builds a database URL**, so a refused run opens no
connection at all.

The check is an equality, not a deny-list. The set of names a deployment might
use is open — `prod`, `production`, `live`, a customer's own word, a typo — so a
check that enumerated names to refuse would let every name nobody thought of
through. The one name that is safe is the one this script exists for.

An empty `ENVIRONMENT` is refused for the same reason: a value somebody set to
nothing is not the one name that is safe.

### What the comparison actually is

An earlier version of this record said "exactly `development`", which was true of
one half of the comparison and false of the other. The check is
`(raw or "").strip() == "development"`:

- **Surrounding whitespace is stripped, and this is a decision.** ` development `,
  `development ` and `\tdevelopment\n` are all admitted. `.env` is a hand-edited
  file, a trailing space in it is invisible in most editors, and a refusal quoting
  `'development '` is indistinguishable on screen from one quoting
  `'development'` — which would be the single most confusing failure this guard
  could produce. The widening is contained and was measured: `.strip()` admits
  exactly the whitespace-padded spellings of the one safe name and nothing else,
  so `devel opment`, `development1` and `adevelopment` are all refused and no
  deployment name can reach it.
- **Case is not folded, and this was inherited rather than chosen.** `==` is
  case-sensitive by default and nobody weighed it at the time; it is recorded as
  inherited because saying otherwise would dress up an accident as a judgment.
  **It stands on review**, for the reason that runs opposite to the strip:
  folding would make a fail-closed guard wider, and a refusal quoting
  `'Development'` is legible — the reader can see what is wrong with it. So the
  rule is *forgive what the reader cannot see, refuse what they can*, and the two
  halves are consistent rather than arbitrary.

Both halves are pinned by cases in the guard suite, and they fail in opposite
directions: dropping the `.strip()` breaks only the whitespace case, adding a
`.casefold()` breaks only the case one. Neither can change silently now.

**This subsection is about the comparison and nothing else.** Which sources
supply the value being compared was decided separately, below, and is not
reopened here.

**The guard reads *resolved* configuration — the process environment with `.env`
filling in only what it does not set — and not the process environment alone.**
That was disputed, arbitrated and decided by Todd. "How the second row was
decided" below is that decision; the table immediately under this paragraph is
only what it looks like case by case, and is not itself the decision.

`scripts/seed.py` builds that resolution once, in `resolved_configuration`, with
the precedence every other reader in this repository uses (ADR 0008, ADR 0012),
and hands the result to the guard and to the URL builder. So "unset" has two
meanings here and they are answered differently:

| `ENVIRONMENT` in the process | `.env` on disk | Result |
|---|---|---|
| absent | absent, or carrying no `ENVIRONMENT` | **refused** |
| absent | supplying `development` | **admitted** |
| set to anything that is not `development` once surrounding whitespace is stripped — the empty string, whitespace alone, and `Development` included | either | **refused** |

Every row is measured, in-process and as a subprocess, and the refusal names
which of the three ways it was wrong — an earlier version reported the first and
the third identically, which is how the two got conflated in the first place.

### How the second row was decided, and what it leaves open

[`docs/disputes/E0-17-01.md`](../disputes/E0-17-01.md) objected that the second
row lets a gitignored file grant permission to a destructive script. Two readings
were put, and both are defensible:

- **Reading A — the guard reads resolved configuration.** `.env` *is* the
  development configuration (`app/config.py`: "in every deployed environment the
  process environment is the only source"), a deployment has no such file, and
  requiring an exported `ENVIRONMENT=development` would make that string the
  incantation a developer must type in order to seed at all — which is the opt-in
  flag rejected below, under another name, travelling with the runbook that needs
  it.
- **Reading B — the guard reads the process environment alone.** It refuses the
  case where an operator exports a production `DATABASE_URL` over a development
  checkout and never touches the environment name, which is the ordinary-Tuesday
  version of getting this wrong.

**A fresh arbitrator ruled that no record in this repository decides between
them, and it went to Todd, who chose Reading A.** The code is unchanged from what
E0-17 shipped, `make seed` keeps working on a stock checkout with nothing
exported, and `README.md`'s promise about that stands.

**The gap Reading B would have narrowed is accepted, not closed, and that is now
a decision rather than an oversight.** An operator who exports a production
`DATABASE_URL` over a development checkout, leaving `ENVIRONMENT` to `.env`, is
admitted: the address comes from the process and the permission from the file,
and nothing here notices they describe different systems. Todd took that
knowingly, on the arbitrator's observation that **no equality check on an
environment name closes it anyway** — Reading B refuses only the slice where the
operator forgot to export the name, and admits the slice where they exported
`development` alongside a production address. The check that would close it
properly is a check on the *address*, which this record rejects below for reasons
that still hold. **Anyone reaching for this gap later should reopen the address
question, not this one.**

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

**Nine of the ten passed. The tenth was the second row of the table above, and it
is `docs/disputes/E0-17-01.md`, ruled as described there.** It stays red until
the case is re-specified, which is the test author's to do and not something to
make green from this side.

**The guard's own resolution is now injectable, which is what that case needs.**
`resolved_configuration(environ, dotenv_path)` returns a mapping instead of
mutating `os.environ`, and `main` takes both as optional arguments defaulting to
the real thing. All four ways `ENVIRONMENT` can be absent or wrong are therefore
one function call with one mapping and one path, rather than a subprocess started
in a directory that happens to contain a particular untracked file. The
subprocess tests remain the right shape for the ordering claim — a refusal
printed while pointed at an unreachable address cannot have connected first — and
are the wrong shape for the resolution question.

Three things about that round are worth keeping, because none of them is visible
in the result:

- **The hand measurement that preceded the tests missed the case the tests
  found.** It ran `ENVIRONMENT=` — the variable present and empty, which
  `load_dotenv` does not override — and reported the unset case as covered.
  Setting a variable to nothing and not setting it at all are different
  questions, and only one had been asked. A measurement beats an argument and is
  still only as good as the case it chose.
- **The obvious fix turned the whole module green while breaking the one path no
  test covers.** The suite's fixture lays every documented `.env.example` entry
  into the child environment, so `ENVIRONMENT` is present in the process for
  every run it makes; reading it before `.env` therefore passed 29 of 29 and
  refused `make seed` on a developer's machine. That path cannot be measured by
  the suite, and had to be measured by hand.
- **The red carried as little information as the green.** The failing case is
  decided by whether an untracked `.env` exists, so it measures the machine
  rather than the script. Verified in `.github/workflows/ci.yml`: the `test` job
  runs `pytest tests/unit tests/integration` and never creates `.env` — only the
  `e2e` and `docker` jobs copy `.env.example` — so the case passes in the gate
  that is supposed to be the guarantee and fails for every developer who followed
  the README's first instruction. Neither side's suite evidence was worth much; the pair of hand
  measurements was.

**A developer whose `.env` says anything else gets a refusal rather than a seed.**
That is the intended cost. The message names the variable, the value it found and
the value it wants.

**Anyone adding a second thing to this script that a deployment might want** —
a repair, a backfill, a re-derivation after a calendar edit — inherits this
refusal, and should ask whether that thing belongs in a script that may not run
in a deployment at all rather than weakening the check.
