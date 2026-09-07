"""E4-04's grants — what `pulse_app` may do with the comment path, and proof it can.

The work order settles the grants exactly: `pulse_app` gets `SELECT` on
`report_comment`, `SELECT` on `moderation_state`, and `SELECT, INSERT` on
`release_batch` and `release_batch_member` — and nothing wider. Every one of those
is a widening of the runtime role, recorded deliberately in
`RUNTIME_BASE_TABLE_PRIVILEGES` and `SANCTIONED_VIEW_COLUMNS` in
`tests/integration/test_identity_grants.py`, and the tables come out of
`test_report_schema.py`'s "no grant is spent here" list in the same change. E4-02
predicted this in as many words: "when this goes red for a good reason, which
will happen: … E4-04 grants the release path what it needs."

Three kinds of test:

  - **the ACL**, asked of `has_table_privilege` in both directions, with the
    privilege the role certainly holds as each probe's control
    (`docs/MISTAKES.md` entry 35 — a guard that only ever reports absence cannot
    say which mechanisms it can see);
  - **the read, driven over the application connection**, which is
    `docs/MISTAKES.md` entry 46's second sentence: "a suite that drives a service
    through the migrating engine has not tested the grant at all — where behaviour
    depends on one, at least one test reaches the code through the connection
    production uses, or the grant-shaped failure passes review as a green suite";
  - **the write, driven over the same connection**, because the cutter is the
    half that needs `INSERT` and every other release test in this epic runs as the
    migrating superuser, which passes every grant.

**Why the write half is not redundant with the read half.** A view executes with
its *owner's* privileges, so a `GRANT SELECT` on `report_comment` can be perfectly
in place and the read still fail at execution time if the owner cannot read
`answer` underneath. The cutter's `INSERT` is the opposite shape: it is the
role's own privilege on two base tables, and no grant on the view repairs it.
Neither test substitutes for the other.

**Nothing here attempts a write to the view.** `docs/disputes/E4-03-01.md`
measured it on the pinned server: PostgreSQL refuses a write to a view it cannot
make auto-updatable during *rewriting*, before the privilege check, so the
refusal is `55000` from a role holding nothing and from a role holding `ALL
PRIVILEGES` alike. The ACL is where that difference is visible, and it is asked
there.
"""

from typing import Any

import pytest
from fixtures.report_comments import (
    COMMENT_VIEW,
    MODERATION_STATE_TABLE,
    RELEASE_BATCH_MEMBER_TABLE,
    RELEASE_BATCH_TABLE,
    CommentWorld,
    ReleaseRows,
    comment_view_columns,
    require_comment_view,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The role `.env.example` gives `DB_APP_USER`, and the Care role beside it.
# Spelled here rather than imported from a sibling test module, for the reason
# `test_identity_grants.py` gives about its own copies.
APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"

HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:role, :relation, :privilege)"

# What the work order grants, as `(relation, privilege)`. The whole of it.
GRANTED = (
    (COMMENT_VIEW, "SELECT"),
    (MODERATION_STATE_TABLE, "SELECT"),
    (RELEASE_BATCH_TABLE, "SELECT"),
    (RELEASE_BATCH_TABLE, "INSERT"),
    (RELEASE_BATCH_MEMBER_TABLE, "SELECT"),
    (RELEASE_BATCH_MEMBER_TABLE, "INSERT"),
)

# Every table privilege Postgres knows, so "nothing wider" is asked of the whole
# set rather than of the three verbs somebody remembered. `GRANT ALL` confers all
# of them at once and is caught whichever is asked; a single stray `UPDATE` is
# caught only if `UPDATE` is in this tuple.
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

RELATIONS = (COMMENT_VIEW, MODERATION_STATE_TABLE, RELEASE_BATCH_TABLE, RELEASE_BATCH_MEMBER_TABLE)

WIDER = [
    (relation, privilege)
    for relation in RELATIONS
    for privilege in TABLE_PRIVILEGES
    if (relation, privilege) not in GRANTED
]

# A relation each role certainly reads, for the control every probe below has to
# pass first (`docs/MISTAKES.md` entry 35). **One per role, and that is the point
# rather than a detail**: `pulse_app` reads `classification` (granted by E0-13)
# and `pulse_care` does not read it at all — the Care role's whole grant list is
# `SELECT` on `role_assignment` plus the reveal's own definer path
# (`RUNTIME_BASE_TABLE_PRIVILEGES` in `test_identity_grants.py`). A control
# pointed at the wrong role's relation reports absence and would make every
# assertion below vacuous, which is exactly the failure a control exists to catch.
A_RELATION_THE_ROLE_CERTAINLY_READS = {
    APPLICATION_ROLE: "classification",
    CARE_ROLE: "role_assignment",
}

THE_WEEK = 7
HELD_WEEKS = (8, 9, 10)
A_BIG_WEEK_COMMENT = "the seminar discussion was worth more than the lecture that set it up"
A_HELD_COMMENT = "the deadline moved twice and the announcement only reached half the class"


def holds(session: Any, role: str, relation: str, privilege: str) -> bool:
    """Whether `role` holds `privilege` on `public.<relation>`, read from the ACL."""
    return bool(
        session.execute(
            text(HAS_TABLE_PRIVILEGE),
            {"role": role, "relation": f"public.{relation}", "privilege": privilege},
        ).scalar_one()
    )


def require_a_probe_that_can_see(session: Any, role: str) -> None:
    """The control: this probe finds a privilege the role certainly has."""
    relation = A_RELATION_THE_ROLE_CERTAINLY_READS[role]
    assert holds(session, role, relation, "SELECT"), (
        f"`has_table_privilege` says `{role}` holds no `SELECT` on `{relation}`, and this schema "
        "grants exactly that. So this probe reports absence whatever is granted, and everything it "
        "says about E4-04's relations is a fact about a blind probe "
        "(`docs/MISTAKES.md` entry 35)."
    )


@pytest.mark.parametrize(
    ("relation", "privilege"),
    GRANTED,
    ids=[f"{relation}-{privilege.lower()}" for relation, privilege in GRANTED],
)
def test_the_runtime_role_holds_the_privilege_the_comment_path_spends(
    db_session: Any, relation: str, privilege: str
) -> None:
    """Each grant E4-04 spends, asked of the ACL, one case per grant.

    E4-02 deliberately granted nothing on the report schema — "a privilege lands
    in the change that uses it" — so every one of these is new here and every one
    is a widening of the runtime role. A case per grant rather than one assertion
    over the set, because the failure output should name the relation and the verb
    that is missing: a missing `SELECT` on `moderation_state` is a read path that
    cannot tell a flagged comment from a published one, and a missing `INSERT` on
    `release_batch_member` is a cutter that computes the crossing and writes half
    of it.

    **The mutation it kills:** any one of the six left out of the grants file —
    `INSERT` on the membership table most likely of them, because the batch row is
    the one a reader thinks of and the membership is where the comments are.
    """
    require_a_probe_that_can_see(db_session, APPLICATION_ROLE)
    assert holds(db_session, APPLICATION_ROLE, relation, privilege), (
        f"`{APPLICATION_ROLE}` does not hold `{privilege}` on `public.{relation}`. E4-04's work "
        "order grants this role `SELECT` on the comment view and on `moderation_state`, and "
        "`SELECT, INSERT` on the two release tables — the read path cannot conceal a flag it "
        "cannot see, and the cutter cannot store a crossing it cannot write. E4-02 granted nothing "
        "on any of these on purpose, so the grants file this ticket ships is the whole of it."
    )


@pytest.mark.parametrize(
    ("relation", "privilege"),
    WIDER,
    ids=[f"{relation}-{privilege.lower()}" for relation, privilege in WIDER],
)
def test_the_runtime_role_holds_nothing_wider_than_the_comment_path_spends(
    db_session: Any, relation: str, privilege: str
) -> None:
    """ "And nothing wider" — every other table privilege, one case each.

    The two release tables are append-only by design: ADR 0146 says outright that
    "a comment cannot be un-released, because a released comment is a row and
    nothing in this schema deletes one", and a runtime role holding `UPDATE` or
    `DELETE` on either could move a comment into another batch — which is a
    comment given another release time, the per-comment timing SPEC §4 batches the
    release to remove. `moderation_state` is E6's to write and nobody's here: a
    connection that could insert one could publish a comment an instructor
    excluded.

    **The control is the read**, asked of the same probe, the same role and the
    same relation — so a case that passes because the function resolved something
    else fails here instead of passing silently.

    **The mutation it kills:** `GRANT ALL ON public.release_batch TO pulse_app`,
    which is what a grants file says when somebody was not sure which verbs the
    writer needed; and `GRANT INSERT ON public.moderation_state`, which is the
    single most tempting line in this ticket, since the read path joins that table
    on every call.
    """
    require_a_probe_that_can_see(db_session, APPLICATION_ROLE)
    assert holds(db_session, APPLICATION_ROLE, relation, "SELECT"), (
        f"`{APPLICATION_ROLE}` holds no `SELECT` on `public.{relation}` either, so this probe "
        "cannot see a privilege the work order does grant and its answer about "
        f"`{privilege}` says nothing. `test_the_runtime_role_holds_the_privilege_the_comment_path_"
        "spends` in this module is where that is diagnosed."
    )
    assert not holds(db_session, APPLICATION_ROLE, relation, privilege), (
        f"`{APPLICATION_ROLE}` holds `{privilege}` on `public.{relation}`, and E4-04's work order "
        "settles this ticket's grants as `SELECT` on the comment view and on `moderation_state` "
        "plus `SELECT, INSERT` on the two release tables, and nothing wider.\n\n"
        "ADR 0146: a released comment is a row and nothing in this schema deletes one. A runtime "
        "role that can update or delete a membership can move a comment into another batch, which "
        "gives it another `cut_at` — the per-comment release time SPEC §4 batches the release to "
        "remove. A role that can write `moderation_state` can publish a comment an instructor "
        "excluded, which is E6's decision and not the report's."
    )


@pytest.mark.parametrize("relation", RELATIONS, ids=list(RELATIONS))
def test_the_care_role_holds_nothing_on_anything_this_ticket_grants(
    db_session: Any, relation: str
) -> None:
    """The Care role reads identity and the threat queue, and no report data at all.

    SPEC §6.2 scopes Care to the safety queue and the audited re-identification,
    and §4 puts traceability there "for safety, not oversight". A Care connection
    holding a read on the comment view would be a second path to every comment in
    the institution, outside the reveal's audit — which is the one channel §4
    admits.

    **The control is `pulse_app`'s own read on the same relation**, so this is not
    a probe that answers false to everything.

    **The mutation it kills:** `GRANT SELECT ON public.report_comment TO
    pulse_app, pulse_care` — the two roles named on one line, which is how a
    grants file usually widens.
    """
    require_a_probe_that_can_see(db_session, CARE_ROLE)
    assert holds(db_session, APPLICATION_ROLE, relation, "SELECT"), (
        f"`{APPLICATION_ROLE}` holds no `SELECT` on `public.{relation}`, so this relation may not "
        "exist yet and the Care role's silence about it means nothing."
    )
    held = [
        privilege
        for privilege in TABLE_PRIVILEGES
        if holds(db_session, CARE_ROLE, relation, privilege)
    ]
    assert not held, (
        f"`{CARE_ROLE}` holds {held} on `public.{relation}`. SPEC §6.2 scopes the Care role to the "
        "threat queue and the audited re-identification, and §4 puts traceability there for safety "
        "rather than oversight. A Care connection that can read the comment view has every "
        "comment in the institution outside the one audited channel §4 admits."
    )


def test_the_read_path_answers_over_the_application_connection(
    migrated_engine: Any,
    application_engine: Any,
    application_session: Any,
    committed_rows: Any,
    committed_comment_world: CommentWorld,
    comment_contract: Any,
) -> None:
    """One reading of real rows through the connection production opens.

    `docs/MISTAKES.md` entry 46: "a suite that drives a service through the
    migrating engine has not tested the grant at all". Every other read test in
    this ticket runs as the migrating superuser, because that is the only
    connection that can see rows inside a rolled-back transaction. This one
    commits its world and reads it as `pulse_app`.

    **The control is `current_user`**, and it is not ceremony: every assertion in
    this module is about what a restricted role may do, and a fixture that quietly
    handed back a superuser connection would make all of them pass while measuring
    nothing.

    **The mutation it exists to survive**: the `GRANT SELECT` on `report_comment`
    missing from the grants file, and — the one no ACL test can see — the view
    left owned by a role that holds nothing on `answer` or `response`, which
    refuses at execution time with the grant on the view itself perfectly in
    place, and empties the report for every instructor in the product.
    """
    contract = comment_contract
    world = committed_comment_world
    threshold = contract.threshold()

    world.build()
    world.close_week(THE_WEEK)
    world.week_of_comments(
        term_week=THE_WEEK,
        texts=[f"{A_BIG_WEEK_COMMENT} ({index + 1})" for index in range(threshold)],
        stream=contract.instructor_stream,
    )
    committed_rows.commit()

    with migrated_engine.connect() as connection:
        require_comment_view(connection)
    seeded = world.responses_in(term_week=THE_WEEK)
    assert seeded == threshold, (
        f"The committed week holds {seeded} responses and the threshold is {threshold}, so the "
        "read below would be empty for a reason that is not about a grant."
    )

    with application_engine.connect() as probe:
        role = probe.execute(text("SELECT current_user")).scalar_one()
        assert role == APPLICATION_ROLE, (
            f"This connection reports itself as {role!r} rather than as {APPLICATION_ROLE!r}, so "
            "nothing below is a statement about a grant."
        )
        assert comment_view_columns(probe), (
            f"The application connection cannot see `public.{COMMENT_VIEW}` in `pg_catalog` at "
            "all, which is a different failure from a missing grant."
        )

    try:
        as_the_application = contract.visible()(
            application_session,
            section_id=world.section_id(),
            week_id=world.week_id(THE_WEEK),
            stream=contract.instructor_stream,
        )
    except DatabaseError as refused:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"Reading the week's comments as `{APPLICATION_ROLE}` was refused: {refused}\n\n"
            "Two failures answer to this and the SQLSTATE tells them apart. `42501` naming "
            f"`{COMMENT_VIEW}` is a missing `GRANT` on the view; `42501` naming `moderation_state` "
            "is the read path's own join, which E4-04 grants separately; `42501` naming a *table* "
            "the view selects from is the view's owner lacking a read on the survey tables, which "
            "no grant on the view repairs and which a test running as the migrating identity would "
            "never see."
        )

    assert len(as_the_application) == threshold, (
        f"Read as `{APPLICATION_ROLE}`, a week of {threshold} committed responses returned "
        f"{len(as_the_application)} comments. An empty answer here over rows the migrating "
        "connection can count is the grant-shaped failure: a view executes with its owner's "
        "privileges, so an owner that cannot read the survey tables empties the report without "
        "emptying the database."
    )


def test_the_cutter_writes_its_batch_over_the_application_connection(
    application_session: Any,
    committed_rows: Any,
    committed_comment_world: CommentWorld,
    committed_release_rows: ReleaseRows,
    comment_contract: Any,
) -> None:
    """The write half of `docs/MISTAKES.md` entry 46, over the same connection.

    The cutter is the only thing in this ticket that writes, and `INSERT` on
    `release_batch` and `release_batch_member` is the only privilege it needs that
    a read cannot cover. Driven as the migrating superuser — which every other
    release test in this epic is — a missing `INSERT` is invisible: the superuser
    passes every grant, the suite is green, and the beat entry fails on the first
    Monday of the term with an integrity-free `42501` nobody is watching for.

    **The rows are read back on the same session**, before it is rolled back, so
    what is asserted is what that connection actually wrote rather than what the
    seeding connection can see.

    **The mutation it exists to survive**: `GRANT SELECT` written where `GRANT
    SELECT, INSERT` was meant on either release table — which is exactly the shape
    a grants file takes when it is copied from a read view's.
    """
    contract = comment_contract
    world = committed_comment_world
    threshold = contract.threshold()

    world.build()
    planted = 0
    while planted < threshold:
        week = HELD_WEEKS[planted % len(HELD_WEEKS)]
        world.close_week(week)
        world.week_of_comments(
            term_week=week,
            texts=[f"{A_HELD_COMMENT} (week {week}, response {planted + 1})"],
            stream=contract.instructor_stream,
        )
        planted += 1
    for week in HELD_WEEKS:
        count = world.responses_in(term_week=week)
        assert 0 < count < threshold, (
            f"Term week {week} holds {count} responses and the threshold is {threshold}, so it "
            "holds nothing the cutter may release and this test would assert a grant over an "
            "empty walk."
        )
    committed_rows.commit()

    assert committed_release_rows.members() == [], (
        "Something had already released this section's comments before the cutter ran, so a "
        "membership found afterwards would not be evidence that this connection could write one."
    )

    try:
        answered = contract.cut()(application_session)
    except DatabaseError as refused:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"The cutter was refused over the `{APPLICATION_ROLE}` connection: {refused}\n\n"
            "`42501` on `release_batch` or `release_batch_member` is the missing `INSERT`. E4-02 "
            "granted nothing on either table on purpose — 'a privilege lands in the change that "
            "uses it' — so E4-04's grants file is the whole of what this writer holds."
        )

    assert answered == 1, (
        f"The cutter reported {answered} batches over the application connection for a section "
        f"whose term volume is {threshold}, the configured threshold."
    )
    written = ReleaseRows(application_session, world.tables).members()
    assert len(written) == threshold, (
        f"The application connection's own session holds {len(written)} memberships after the "
        f"cutter ran and the section held {threshold} comments under the threshold. This is read "
        "back on the writing session rather than on the seeding one, so what it reports is what "
        "that connection actually wrote."
    )
