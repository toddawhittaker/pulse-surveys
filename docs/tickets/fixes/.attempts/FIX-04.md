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
