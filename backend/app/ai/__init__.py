"""The AI boundary — SPEC §7.4.

Everything a model produces enters the system through this package, and it
enters as a validated object rather than as parsed JSON. Three things live here
once the epic is finished:

- `contracts.py` — one Pydantic output model per §7.4 task. It is simultaneously
  the runtime contract, the API response schema and the eval fixture (§9.3), so
  there is one shape rather than three that can drift apart.
- `prompts/` — versioned prompt files, one per task and version. Its README
  states the naming scheme.
- `gateway.py` and `tasks.py` — the single-shot client and the per-task calls.
  `gateway.py` is the one place a model is called from; `tasks.py` gives each
  §7.4 task its own function. E0-13 built both and implements the first task
  end to end — the other four carry contracts and wait on the prompts that
  belong to E2, E4, E6 and E7.

Nothing in this package reaches the database or the configuration surface. A
contracts module that imports `app.db` builds an engine out of `Settings()` at
import time, which is the second rule in `docs/tickets/e0/README.md`'s "What the
built tickets settled".
"""
