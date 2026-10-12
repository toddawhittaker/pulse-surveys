"""SPEC §2.1's worked example, entered by both doors on the demo seed (SPEC §14.3, E9 exit).

The seed is `scripts/seed.py`, run as a program against a database of its own
(`tests/fixtures/seed.py`). Nothing here reads what the seed wrote about the
assistant dean. Each door's subject is resolved by the function that door
resolves it with, and the tree is read through the roll-up, on `pulse_app`'s
connection, the one production uses (`docs/MISTAKES.md` entries 46 and 58).

The two subjects are the mock platform's and the mock provider's own spellings
(`mock-lms/app/seed.py`'s `ASSISTANT_DEAN`, and the provider's `assistant-dean`
persona), written here rather than imported from the seed.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration

TERM_NAME = "Fall 2026"
LAUNCH_SUBJECT = "mock-lms-user-assistant-dean"
WEB_SUBJECT = "mock-idp-user-assistant-dean"


def seeded(run: Any) -> None:
    if not run.succeeded:
        pytest.fail(
            "The seed run this module is built on did not succeed; `test_demo_seed_script.py` "
            "owns that failure.\n" + run.report()
        )


@contextmanager
def production_session(demo: Any) -> Iterator[Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(demo.database.application_url)
    try:
        with Session(bind=engine) as session:
            yield session
    finally:
        engine.dispose()


def people_behind_the_two_doors(demo: Any, seed_module: Any) -> tuple[UUID | None, UUID | None]:
    """The person each door's subject reaches, resolved as each door resolves it."""
    from app.services.identity import identity_behind_a_launch, person_behind_a_web_login

    with production_session(demo) as session:
        launched = identity_behind_a_launch(
            session,
            {
                "iss": seed_module.MOCK_PLATFORM_ISSUER,
                "aud": seed_module.MOCK_PLATFORM_CLIENT_ID,
                "sub": LAUNCH_SUBJECT,
            },
        )
        signed_in = person_behind_a_web_login(
            session, {"iss": seed_module.mock_idp_issuer(demo.environment), "sub": WEB_SUBJECT}
        )
    return launched.person_id, signed_in


def tree_of(demo: Any, person: UUID, authz: Any) -> Any:
    from sqlalchemy import select

    from app.config import Settings
    from app.models.term import Term
    from app.services.rollups import rollup_tree

    with production_session(demo) as session:
        term_id = session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()
        scope = authz.resolve_scope(session, person_id=person)
        return rollup_tree(session, scope=scope, term_id=term_id, settings=Settings())


def test_both_doors_reach_one_person(
    seeded_demo: Any, demo_database: Any, seed_module: Any
) -> None:
    """The launch subject and the web-login subject resolve to the same `person`."""
    seeded(seeded_demo)
    launched, signed_in = people_behind_the_two_doors(demo_database, seed_module)
    assert launched is not None, f"A launch as {LAUNCH_SUBJECT!r} reaches no person."
    assert signed_in is not None, f"A web login as {WEB_SUBJECT!r} reaches no person."
    assert launched == signed_in


def test_the_worked_examples_tree_is_two_departments_and_one_led_course(
    seeded_demo: Any, demo_database: Any, seed_module: Any, authz: Any
) -> None:
    """Roots Biology, Mathematics and PSYC; under PSYC, PSYC 110 alone (SPEC §2.1).

    The assistant dean supervises the Mathematics and Biology chairs and leads
    PSYC 110 in a department whose chair reports to the dean, so PSYC 545 and
    the Psychology department are not theirs.
    """
    seeded(seeded_demo)
    person, _ = people_behind_the_two_doors(demo_database, seed_module)
    assert person is not None, f"A launch as {LAUNCH_SUBJECT!r} reaches no person."

    tree = tree_of(demo_database, person, authz)
    assert [(node.kind, node.name) for node in tree.hierarchy] == [
        ("department", "Biology"),
        ("department", "Mathematics"),
        ("prefix", "PSYC"),
    ]
    psyc = tree.hierarchy[2]
    assert [(node.kind, node.name) for node in psyc.children] == [
        ("course", "PSYC 110 — Introduction to Psychology")
    ]
    assert (psyc.course_count, psyc.section_count) == (1, 2)


def test_a_database_seeded_before_the_move_keeps_one_assistant_dean(
    demo_databases: Any, seed_module: Any
) -> None:
    """A re-seed moves the earlier shape over rather than writing a second person.

    Before the worked example could be entered by both doors, the assistant dean
    was linked to a `user` on the fictional platform and the provider's subject
    reached a separate mock-world person. A development database seeded then is
    put back in that shape and seeded again: there is still one assistant dean,
    and both doors reach them.
    """
    from sqlalchemy import text

    demo = demo_databases()
    seeded(demo.run())
    with demo.connect() as connection:
        connection.execute(
            text(
                """
                WITH fictional AS (
                    SELECT p.id FROM lti_platform p
                    JOIN "user" u ON u.lti_platform_id = p.id
                    WHERE u.lms_user_id LIKE 'pulse-demo-%' LIMIT 1
                ), earlier AS (
                    INSERT INTO "user" (lti_platform_id, lms_user_id)
                    SELECT id, 'pulse-demo-assistant-dean-arts-sciences' FROM fictional
                    RETURNING id
                )
                UPDATE person SET user_id = (SELECT id FROM earlier)
                WHERE identity_name = 'Demo Assistant Dean of Arts and Sciences'
                """
            )
        )
        copy = connection.execute(
            text(
                "INSERT INTO person (identity_name, category) "
                "VALUES ('Demo Mock-World Assistant Dean', 'Leadership') RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text("UPDATE web_login_subject SET person_id = :copy WHERE idp_subject = :subject"),
            {"copy": copy, "subject": WEB_SUBJECT},
        )
        connection.commit()

    seeded(demo.run())
    with demo.connect() as connection:
        named = connection.execute(
            text(
                "SELECT count(*) FROM person "
                "WHERE identity_name = 'Demo Assistant Dean of Arts and Sciences'"
            )
        ).scalar_one()
    launched, signed_in = people_behind_the_two_doors(demo, seed_module)
    assert named == 1
    assert launched is not None
    assert launched == signed_in
