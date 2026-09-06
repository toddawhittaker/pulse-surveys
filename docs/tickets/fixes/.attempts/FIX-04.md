# FIX-04 — attempts

Ticket: `docs/tickets/fixes/FIX-04-python-3-14.md`. Branch `fix/python-3-14`,
cut from `main` at a32ddc3. Heavy lane: the tests were committed first, at
33a2ed8, and `tests/**` is not mine to edit.

## 2026-09-06 — the red set confirmed, controls first

`.venv/bin/pytest tests/unit/test_the_python_runtime_declarations_agree.py -v`
→ **2 failed, 3 passed**, exit 1, exactly the manifest's prediction. The three
green ones are the module's controls and its two pure comparison tests, so the
machinery measures something before I move anything: the glob finds all four
Dockerfiles and a `FROM python:` stage in each, the workflow walk finds
`PYTHON_VERSION`, `major_minor` refuses to call 3.13 and 3.14 equal, and the
`requires-python` floor is read out of a specifier rather than a plain version.

The two reds are both on their own assertion, not on a blindness guard:

- `test_every_python_runtime_declaration_names_the_pinned_version` — every
  source agrees, on `3.13`, and the agreed value is not `3.14`.
- `test_the_interpreter_running_this_suite_is_the_pinned_version` —
  `assert (3, 13) == (3, 14)`.

Log: `scratchpad/red-control.txt`.

## 2026-09-06 — the pins moved

Eight `FROM` lines across `backend/`, `mock-lms/`, `mock-idp/` and `mock-ai/`
Dockerfiles moved from
`python:3.13.15-slim-bookworm@sha256:00faa2de…` to
`python:3.14.7-slim-bookworm@sha256:9ab8d9c8…`, two per file, each file's count
asserted as exactly 2 by the script that did the replacement rather than
trusted. `PYTHON_VERSION: '3.14'` in `.github/workflows/ci.yml`;
`requires-python = ">=3.14"` and mypy `python_version = "3.14"` in
`pyproject.toml`; the two prose mentions (`python:3.14-slim` in
`pyproject.toml`'s psycopg comment, `python 3.14` in `docker-compose.yml`'s beat
healthcheck comment) followed.

`[tool.ruff] target-version` stays `py313` — ruff 0.6.9 refuses `py314`, probed
before this ticket started — with a comment beside it saying so and naming the
carried-forward item. Not a sixth pin moved and deliberately not read by the new
test module.

## 2026-09-06 — the lockfiles rebuilt on 3.14, nothing moved

A fresh `compilevenv` (uv, `--python 3.14 --seed`, python 3.14.6) with nothing in
it but `pip-tools==7.6.1` and `click<8.3` — click 8.2.1, so no false `--no-index`
header — then the two `pip-compile` commands exactly as `Makefile`'s `lock`
target writes them, run from the repo root. Both exited 0.

The whole diff is two header lines, `Python 3.13` → `Python 3.14`, one per file.
**No package version moved and no hash set changed**, which is what the
pre-ticket probe predicted: every pinned version already ships a wheel that 3.14
accepts, so the resolve had nothing to force. Nothing to revert, and nothing to
name in the PR body as a forced bump.

## 2026-09-06 — the venv rebuilt on 3.14, and the one red the suite added

`.venv` recreated with `uv venv --python 3.14 .venv --seed` (python 3.14.6),
then `pip install --require-hashes -r requirements-dev.txt`, `pip install -e .
--no-deps --no-build-isolation`, and the five pinned tools `Makefile`'s `tools`
target installs (ruff 0.6.9, mypy 1.11.2, pip-audit 2.7.3, pip-licenses 5.5.5,
pip-tools 7.6.1). Every step exited 0; the hash-checked install needed no sdist
build, so every locked version really does ship a wheel 3.14 accepts.

The ticket's own module then went **5 passed**, exit 0, on the same tree that
gave 2 failed before the venv moved — so the two reds were the declarations and
the interpreter, and nothing else.

The unit and integration suites together, `-n 4`, were then **1 failed, 2989
passed** in 4m47s. The single red was not a 3.14 behaviour change and not the
new pins. It was
`test_every_repository_wide_sweep_runs_in_a_job_the_filter_cannot_switch_off`,
in the documentation-only-diff guard module, reporting that the ticket's new
declarations module walks the repository from its root (an `rglob` to find every
Dockerfile without a list of file names) and runs only in the job a
documentation-only diff switches off.

The repair that guard itself names is to run the module in `lint-python`, which
is unconditional — never to reshape the sweep until the detector stops seeing
it, and never to add it to the exemption set, which lives behind the test wall
anyway. It is named there whole, because its five cases are the sweep plus the
controls that prove each collector can see what it claims to; a sweep run
without its controls is a silence nobody can read. The guard module went **27
passed**, exit 0, after the edit.

A note for whoever reads the shell history: the hook that protects `tests/**`
matches the whole command text positionally, so writing this log through a
heredoc that quotes a test path is refused. Append it with an editor.

## 2026-09-06 — the records that asserted 3.13, swept by the fact

`grep -rn "3\.13\|py313\|cp313\|python3\.13"` over the whole tree, not just the
seven pinned places, found six records outside them. Three were amended, three
were left alone deliberately, and one is on the other side of the test wall.

Amended:

- `README.md` — "Python 3.13 or newer (SPEC §7.1)" was the setup instruction for
  working without containers, and `requires-python = ">=3.14"` now makes `make
  install` refuse a 3.13 interpreter. It says 3.14, and says plainly that the
  spec's floor and this repository's are different numbers.
- `backend/app/config.py` (~line 433) and ADR 0077 (~line 225) both say
  `ip_address("::ffff:127.0.0.1").is_loopback` was measured `True` "on 3.13", on
  "the pinned interpreter" — and the pinned interpreter moved. Re-measured on
  3.14.6: `is_loopback` is `True` and `ipv4_mapped.is_loopback` is `True`, so
  the behaviour is unchanged and both records now name both versions. The module
  that guards the rule is green on 3.14 (95 passed).
- ADR 0073 (~line 78) said "the runtime image is `python:3.13-slim`" in the
  present tense, as the reason `cryptography`'s wheels hold. Now names 3.14 and
  says which ticket moved it.

Left alone, each for a reason:

- `docs/SPEC.md` §7.1 says "Python 3.13+", which 3.14 satisfies. The 2026-08-24
  dependency triage already ruled this: moving to 3.14 is a construction
  decision, not a spec change. No spec edit, and therefore no ADR either — the
  spec is not silent here.
- `docs/AGENTS_INTENT.md` ("Modern Python 3.13+") is a floor, still true.
- `.claude/agents/implementer.md` says the same thing and is a process file:
  CLAUDE.md routes `.claude/` through a `process/` branch, not this one.

Not mine to edit: a comment in the OIDC provider configuration tests
(~line 209) says the mapped-address behaviour was "measured on Python 3.13, this
repository's floor". The behaviour is re-measured and unchanged, but the floor
in that sentence is now wrong. The module is green on 3.14, so this is a record
edit rather than a finding, and it is reported to the orchestrator to route to
whoever owns `tests/**`.

Also swept: the old base-image digest `00faa2de…` appears nowhere in the tree.

## 2026-09-06 — the gates, on a frozen tree

Every gate below ran with nothing uncommitted, each redirected to a file and
each exit status read from `$?` rather than through a pipe (`docs/MISTAKES.md`
entry 34). Logs are in the session scratchpad under the names given.

| Gate | Exit | Result | Log |
|---|---|---|---|
| `ruff format --check .` | 0 | 398 files already formatted | `gate-ruff-format.txt` |
| `ruff check .` | 0 | All checks passed | `gate-ruff-check.txt` |
| `make typecheck` | 0 | mypy: 76 + 12 + 7 + 4 files, no issues; `tsc --noEmit` clean | `gate-typecheck.txt` |
| unit + integration, `-n 4` | 0 | 2990 passed in 4m37s | `gate-pytest-final.txt` |
| `make invariants` | 0 | 240 invariant tests ran, none skipped; 176 marked tests each assert something | `gate-invariants.txt` |
| `make docker-build` | 0 | images built, contents checked, E0-02/E0-03 stack criteria all met | `gate-docker-build.txt` |

The images were rebuilt before any of this: `docker compose up -d --build`, then
`python -V` inside each of api, worker, mock-ai, mock-idp and mock-lms reports
**3.14.7**, so no gate ran against a stale image (`docs/MISTAKES.md` entry 12).
`make docker-build` built them again from scratch and its own health criteria
passed, including beat keeping its schedule file and the worker going unhealthy
when Redis stops.

No migration moved, so `alembic check` was not part of this.

## 2026-09-06 — Celery on 3.14, driven rather than argued

The multiprocessing change the ticket flagged is real and visible in the
container: `multiprocessing.get_start_method()` answers **`forkserver`** on
3.14.7 where it answered `fork` before. Celery's prefork pool does not use it —
it rides billiard, which forks itself — and the drive says so.

```
docker compose exec -T worker celery --app app.jobs.celery_app inspect ping
->  celery@61df1d56ad95: OK
        pong
1 node online.
```

Three real tasks called, `celery --app app.jobs.celery_app call <name>`, and the
worker log read afterwards:

```
Task app.jobs.tasks.ping[f653a5c9…] succeeded in 0.0037s: 'pong'
Task app.jobs.tasks.purge_launch_nonces[3f232814…] raised unexpected:
  ProgrammingError('(psycopg.errors.InsufficientPrivilege) permission denied
  for table lti_launch_nonce')
Task app.jobs.tasks.derive_survey_windows[68cf22d9…] succeeded in 0.0131s: None
```

Both successes ran in `ForkPoolWorker-32`, a pool child, so acceptance criterion
4 is met: a worker on the rebuilt images accepts a task and completes it, and the
one that reaches the database (`derive_survey_windows`) completes as well.

### The middle line is a real defect, and it is not this ticket's

`purge_launch_nonces` fails for a privilege reason that has nothing to do with
the runtime. Postgres requires `SELECT` on the columns a `DELETE ... WHERE`
reads; `lti_launch_nonce_grants_v001.sql` grants `pulse_app` `INSERT, DELETE`
and withholds `SELECT` deliberately; the purge deletes on `expires_at`. Measured
as `pulse_app` against the dev database, three probes:

- `DELETE FROM lti_launch_nonce WHERE expires_at < now()` — **refused**, 42501.
- `DELETE FROM lti_launch_nonce` with no `WHERE` — **permitted**.
- the same `DELETE ... WHERE` against `lti_launch_state` — **permitted**, because
  that table's grant includes `SELECT`.

So it is the `WHERE`, not the `DELETE`, and it has been failing on every daily
beat run since E1-08 shipped the ledger on 2026-08-26. The launch path is
unaffected: `claim_nonce`'s `INSERT` is permitted, probed the same way. Nothing
here was fixable inside FIX-04 — a grant widening needs a decision about what
the role learns and an entry in the privilege record behind the test wall — so it
is recorded in `docs/tickets/e4/carried-from-e3.md` with an owner and a
done-when, and reported. `docs/MISTAKES.md` entry 48 is what put it in that file
rather than only in the pull request body; its counter is bumped in the same
commit.

## 2026-09-06 — the two greps the ticket asks for

- **PEP 649.** `grep -rn "__annotations__\|get_type_hints" backend/app
  mock-lms/app mock-idp/app mock-ai/app scripts/` → no match, exit 1. No
  application code reads annotations directly, so lazy annotations change
  nothing here.
- **Criterion 3.** `grep -rn "3\.13"` over the four Dockerfiles, `ci.yml`,
  `pyproject.toml`, `docker-compose.yml` and both lockfiles → no match, exit 1.
  The same search for `3\.14` over the same files finds 16 lines, so the search
  is not blind. Widened to `py313\|cp313`, exactly two lines remain, both the
  ruff exception: `target-version = "py313"` and the comment above it.
