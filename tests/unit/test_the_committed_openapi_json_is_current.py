"""The committed `frontend/src/api/openapi.json` is what the backend publishes now.

The frontend's wire types are generated from that file (ADR 0185). A backend
schema change that nobody exported leaves the file, and every type generated
from it, describing a wire that no longer exists. So this compares the export
script's own `render()` with the committed bytes: the same function that writes
the file, run under the suite's documented environment, which is the
environment the script is documented to run under.

The frontend half of the check, that `wire.gen.ts` is what the generator makes
of this file, is `frontend/src/api/wire.gen.test.ts`.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "export_openapi.py"
COMMITTED_PATH = REPO_ROOT / "frontend" / "src" / "api" / "openapi.json"

REGENERATE = (
    "PYTHONPATH=backend python scripts/export_openapi.py && npm run gen:wire --workspace frontend"
)


def load_export_script() -> ModuleType:
    specification = importlib.util.spec_from_file_location("export_openapi", SCRIPT_PATH)
    assert (
        specification is not None and specification.loader is not None
    ), f"{SCRIPT_PATH} cannot be imported as a module."
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_the_committed_document_describes_routes() -> None:
    # Two empty documents compare equal, so the comparison below means nothing
    # unless the committed one actually holds the API.
    committed = json.loads(COMMITTED_PATH.read_text(encoding="utf-8"))
    assert committed.get("paths"), f"{COMMITTED_PATH} has no paths."


def test_the_committed_document_is_what_the_backend_renders_now() -> None:
    rendered = load_export_script().render()
    committed = COMMITTED_PATH.read_text(encoding="utf-8")
    assert rendered == committed, (
        f"{COMMITTED_PATH} is stale: the backend's OpenAPI document has changed. "
        f"Regenerate it and the wire types with: {REGENERATE}"
    )
