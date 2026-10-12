"""`pulse_app` cannot write the people graph except through the definers — E9-02 done-when 2.

> 2. **`pulse_app` cannot write around the definers.** As `pulse_app`, a direct
>    `INSERT`, `UPDATE` or `DELETE` on `person`, `role_assignment`,
>    `lead_faculty_mapping` and `web_login_subject` is refused by the database.
>    This is the database's whole guarantee: a `pulse_app` session that passes
>    a real admin's key to a definer is answered as that admin, so neither this
>    test nor done-when 1 claims the database knows who is acting.

**Green today, and that is its job.** The ticket's context says it: "`pulse_app`
holds no write on the people graph today". E9-02's migration creates definers
that write these four tables and grants `pulse_app` `EXECUTE` on them; the
mistake this module exists to catch is the migration granting the table writes
as well (or instead), which would make every admin check inside a definer
decorative — the application connection could write a dean without asking one.

**Through the connection production uses** (`docs/MISTAKES.md` entry 46):
`application_session` connects as `pulse_app`, holding only what the migrations
grant. A suite run on the migrating engine would pass every write and say nothing
about the grant.

**Refused means SQLSTATE 42501**, not "raised": a missing table (42P01), a
missing column (42703) or a constraint (23xxx) would satisfy a bare `raises` while
saying nothing about what the role may do. And each refused write is followed by
reading the row back on another connection, so "refused" is not a 42501 raised
after the write took effect.

**The other half** — that `pulse_app` may *execute* the definers and that each
refuses a non-admin key — is
`test_the_people_graph_definers_answer_only_an_admin.py`.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.supervision import foreign_key_columns, require_table, single_primary_key
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

APPLICATION_ROLE = "pulse_app"
INSUFFICIENT_PRIVILEGE = "42501"

PERSON = "person"
ROLE_ASSIGNMENT = "role_assignment"
LEAD_FACULTY_MAPPING = "lead_faculty_mapping"
WEB_LOGIN_SUBJECT = "web_login_subject"
PEOPLE_GRAPH_TABLES = (PERSON, ROLE_ASSIGNMENT, LEAD_FACULTY_MAPPING, WEB_LOGIN_SUBJECT)
VERBS = ("INSERT", "UPDATE", "DELETE")

# ADR 0024's link on `person`, and ADR 0097's linkage columns.
PERSON_USER_COLUMN = "user_id"
LINKAGE_PERSON_COLUMN = "person_id"

# A read view `pulse_app` is granted `SELECT` on (ADR 0044's graph, v002 carries
# `reports_to`), for the control that this connection is answered at all.
A_GRANTED_VIEW = "assignment_scope"


def refused(session: Any, statement: str, parameters: dict[str, Any]) -> Any:
    """Run `statement` in a savepoint; answer the database error it provoked, or `None`."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


class Planted:
    """One committed row in each of the four tables, and the statements that would write them."""

    def __init__(self, committed_rows: Any, web_identity: Any, tables: dict[str, Any]) -> None:
        self.rows = committed_rows
        self.tables = tables
        graph = committed_rows.graph
        self.person = web_identity.person()
        assignment = graph.node("DEAN")
        self.assignment = assignment[graph.assignment_key]
        self.reports_to = graph.reports_to_column
        mapping = graph.lead_mapping(person=self.person)
        self.mapping = mapping[single_primary_key(require_table(tables, LEAD_FACULTY_MAPPING))]
        self.mapping_person = foreign_key_columns(
            require_table(tables, LEAD_FACULTY_MAPPING), PERSON
        )[0]
        self.subject = f"e9-02-subject-{uuid4().hex[:8]}"
        web_identity.link_web_subject(
            issuer="https://e9-02-issuer.invalid", subject=self.subject, person_id=self.person
        )
        committed_rows.commit()

    def key(self, table: str) -> str:
        return single_primary_key(require_table(self.tables, table))

    def statement(self, table: str, verb: str) -> tuple[str, dict[str, Any]]:
        """The one write of `verb` on `table`, naming the planted row where it names one."""
        if table == PERSON:
            key, column, value = self.key(PERSON), PERSON_USER_COLUMN, self.person
        elif table == ROLE_ASSIGNMENT:
            key, column, value = self.key(ROLE_ASSIGNMENT), self.reports_to, self.assignment
        elif table == LEAD_FACULTY_MAPPING:
            key, column, value = self.key(LEAD_FACULTY_MAPPING), self.mapping_person, self.mapping
        else:
            key, column, value = "idp_subject", LINKAGE_PERSON_COLUMN, self.subject
        cast = "text" if table == WEB_LOGIN_SUBJECT else "uuid"
        where = f'WHERE "{key}" = CAST(:row AS {cast})'
        if verb == "INSERT":
            return f'INSERT INTO public."{table}" ("{column}") VALUES (NULL)', {}  # noqa: S608
        if verb == "UPDATE":
            return (
                f'UPDATE public."{table}" SET "{column}" = "{column}" {where}',  # noqa: S608
                {"row": str(value)},
            )
        return f'DELETE FROM public."{table}" {where}', {"row": str(value)}  # noqa: S608

    def still_there(self, table: str) -> int:
        """How many rows answer to the planted row's key, read on the seeding connection."""
        statement, parameters = self.statement(table, "DELETE")
        selecting = statement.replace("DELETE FROM", "SELECT count(*) FROM", 1)
        self.rows.session.rollback()
        return int(self.rows.session.execute(text(selecting), parameters).scalar_one())


def test_the_connection_these_refusals_ride_is_pulse_app_and_it_is_answered(
    application_session: Any,
) -> None:
    """CONTROL — green today. A red here means the instrument is broken, not the grants.

    Every refusal below is attributed to what `pulse_app` may do, so the session
    has to be `pulse_app`, and it has to be answered where it is granted
    something: a connection that refused everything would satisfy every refusal
    in this module.
    """
    current = application_session.execute(text("SELECT current_user")).scalar_one()
    assert current == APPLICATION_ROLE, (
        f"`application_session` authenticates as {current!r}, not `{APPLICATION_ROLE}`; every "
        "refusal below would be measuring some other role."
    )
    counted = application_session.execute(
        text(f'SELECT count(*) FROM public."{A_GRANTED_VIEW}"')  # noqa: S608
    ).scalar_one()
    assert counted >= 0, f"`{APPLICATION_ROLE}` could not read `{A_GRANTED_VIEW}`."


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("table", PEOPLE_GRAPH_TABLES)
def test_a_direct_write_on_a_people_graph_table_is_refused_to_the_application_role(
    application_session: Any,
    committed_rows: Any,
    web_identity: Any,
    metadata_tables: dict[str, Any],
    table: str,
    verb: str,
) -> None:
    """Done-when 2, one table and one verb per case, on the planted row where it names one.

    **The mutations it kills:** E9-02's migration granting `INSERT`, `UPDATE` or
    `DELETE` on any of the four tables to `pulse_app` (or to `PUBLIC`, which
    includes it) — the definers are then a door beside an open wall; a column
    grant (`GRANT UPDATE (reports_to) ON role_assignment`), which re-points an
    edge without the definer's audit row. **The near miss it spares:** the
    `SELECT`s `pulse_app` already holds on read views, which the control shows
    are answered.
    """
    planted = Planted(committed_rows, web_identity, metadata_tables)
    before = planted.still_there(table)
    assert before == 1, (
        f"The planted `{table}` row is found {before} times before the write. A broken world, not "
        "a red: a refused UPDATE or DELETE of a row that is not there proves nothing."
    )

    statement, parameters = planted.statement(table, verb)
    failure = refused(application_session, statement, parameters)

    assert failure is not None, (
        f"`{APPLICATION_ROLE}` ran `{statement}` without error. Done-when 2: a direct {verb} on "
        f"`{table}` is refused by the database, so every write to the people graph goes through "
        "an admin-checked definer and leaves its audit row."
    )
    assert sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}`'s {verb} on `{table}` failed with SQLSTATE {sqlstate(failure)!r}, "
        f"not {INSUFFICIENT_PRIVILEGE} (insufficient privilege): {failure.orig!r}. Any other code "
        "means the statement got past the grant and was stopped by something else."
    )
    assert planted.still_there(table) == before, (
        f"The planted `{table}` row is found {planted.still_there(table)} times after the refused "
        f"{verb}, where it was found {before} times before."
    )
