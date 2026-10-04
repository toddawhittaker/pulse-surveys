#!/usr/bin/env python3
"""Write the backend's OpenAPI document to `frontend/src/api/openapi.json`.

The frontend's wire types are generated from that file (ADR 0185), so this is
the first half of a two-step regeneration:

    PYTHONPATH=backend python scripts/export_openapi.py
    npm run gen:wire --workspace frontend

The document is built in process from `create_app().openapi()`, which answers
whether or not the served `/openapi.json` route is switched on (ADR 0074): the
route is disabled outside development, the schema is not, and the two
environments produce the same document. So this needs the documented
environment (`.env.example`'s values) to build the application, and no
database or network.

`tests/unit/test_the_committed_openapi_json_is_current.py` compares `render()`
with the committed file, which is how a backend schema change that was not
exported fails the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import create_app

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "frontend" / "src" / "api" / "openapi.json"


def render() -> str:
    """The document as it is committed: FastAPI's own key order, two-space indent."""
    return json.dumps(create_app().openapi(), indent=2) + "\n"


def main() -> int:
    OUTPUT_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
