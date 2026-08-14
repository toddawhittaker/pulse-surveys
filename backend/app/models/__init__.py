"""ORM tables (SPEC §8, §13), one module per aggregate.

Empty of tables at E0-04 — the baseline migration creates nothing, and the first
tables land in E0-05. What exists here now is `Base` and the constraint naming
convention its metadata carries.

**Importing this package must import every model module.** `backend/migrations/
env.py` autogenerates against `Base.metadata`, and a table whose module nobody
imported is not on that metadata — so `alembic check` reports no drift, the
migration nobody wrote is never missed, and the table simply does not exist in
any deployed database. Adding `app/models/<aggregate>.py` therefore means adding
an import here, in the same change.
"""

from app.models.base import NAMING_CONVENTION, Base

__all__ = ["NAMING_CONVENTION", "Base"]
