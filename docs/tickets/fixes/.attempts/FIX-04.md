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
