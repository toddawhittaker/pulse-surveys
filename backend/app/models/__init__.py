"""ORM tables (SPEC §8, §13), one module per aggregate.

`org` holds the containment hierarchy — institution, college, department,
prefix, course, section (E0-05). `term` holds the academic calendar — term,
week, start_letter_map, survey_window (E0-06). `identity` holds user,
user_identity, person and enrollment, and `lti` the registration tables they
hang off — lti_platform and lti_deployment (E0-08). `identity` also holds the
supervision graph, role_assignment and lead_faculty_mapping (E0-09), which SPEC
§13 puts in that module. The other aggregates §13 lists arrive with the tickets
that need them.

**Importing this package must import every model module.** `backend/migrations/
env.py` autogenerates against `Base.metadata`, and a table whose module nobody
imported is not on that metadata — so `alembic check` reports no drift, the
migration nobody wrote is never missed, and the table simply does not exist in
any deployed database. Adding `app/models/<aggregate>.py` therefore means adding
an import here, in the same change.

The module is imported for that side effect, so it is re-exported in `__all__`
rather than left to look like an unused import that a later cleanup can delete.
"""

from app.models import identity, lti, org, term
from app.models.base import NAMING_CONVENTION, AwareDateTime, Base

__all__ = ["NAMING_CONVENTION", "AwareDateTime", "Base", "identity", "lti", "org", "term"]
