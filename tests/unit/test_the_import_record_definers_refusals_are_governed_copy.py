"""Every refusal `people_graph_v002.sql` raises is a governed `admin_people.` sentence — E9-06 fix round, Q1 (g).

The fix round's definer refuses a non-admin actor with SQLSTATE `P0001` and the
existing key `admin_people.actor_not_an_admin` (E9-02's settled shape: `RAISE
EXCEPTION '<copy key>' USING ERRCODE = 'raise_exception'`). The copy inventory
(`test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`) collects the
registry, not the SQL, so a key written inline in the new file and never
registered would reach the admin as a bare key and no sweep would read it. This
reads the new file's raised messages and requires each to be registered under
`admin_people.`. The inventory test itself is unchanged (E9-06 done-when 12).

**Which failure a red is, at 09778dc5.** The file does not exist: a FAILED from
`pytest.fail` naming it.
"""

import importlib
import re
from pathlib import Path

import pytest

from app.copy.admin_people import COPY

SQL_FILE = "people_graph_v002.sql"
RAISED = re.compile(r"RAISE\s+EXCEPTION\s+'([^']*)'", re.IGNORECASE)
ACTOR_NOT_AN_ADMIN = "admin_people.actor_not_an_admin"


def test_every_key_the_import_record_file_raises_is_a_registered_admin_people_sentence() -> None:
    """Each `RAISE EXCEPTION '<message>'` in the v002 file names a key in `app.copy.admin_people.COPY`.

    **The mutations it kills:** a refusal written as an English sentence inline
    in SQL; a new key under another prefix or not registered. **The near miss:**
    the actor check's key, which must be among the raised ones — so an empty
    scan (a file raising nothing, or a pattern matching nothing) is red, not a
    vacuous green (`docs/MISTAKES.md` entry 3).
    """
    package = Path(importlib.import_module("app").__file__ or "").parent
    path = package / "views_sql" / SQL_FILE
    if not path.is_file():
        pytest.fail(f"There is no `app/views_sql/{SQL_FILE}`; E9-06's fix round adds it.")
    raised = set(RAISED.findall(path.read_text(encoding="utf-8")))

    assert ACTOR_NOT_AN_ADMIN in raised, (
        f"`{SQL_FILE}` raises {sorted(raised)}, and not `{ACTOR_NOT_AN_ADMIN}`, the settled "
        "refusal of a non-admin actor."
    )
    stray = sorted(key for key in raised if not key.startswith("admin_people.") or key not in COPY)
    assert (
        not stray
    ), f"`{SQL_FILE}` raises {stray}, which are not registered `admin_people.` sentences."
