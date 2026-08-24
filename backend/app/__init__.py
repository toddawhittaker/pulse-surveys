"""Pulse Surveys backend.

`backend/` is the import root, so modules are imported as `app.<module>` and
never as `backend.app.<module>`. That is what `mypy_path = "backend"` in
`pyproject.toml` and `uvicorn app.main:create_app --factory` both assume.

`__version__` is the single source of the version: `pyproject.toml` reads it
from here (`[tool.setuptools.dynamic]`), and `/healthz` reports it.
"""

__version__ = "0.1.0"

SERVICE_NAME = "pulse-surveys"
