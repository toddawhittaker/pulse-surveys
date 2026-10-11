"""the response records and the staff name channel

Revision ID: 2c3d5a0de424
Revises: b7d2e94c1a05
Create Date: 2026-10-11 12:00:00.000000

E7-01, ADR 0191 and ADR 0192. Two append-only records and one read:

  - `instructor_response`: one published response to a section's course week,
    with the term both belong to (composite keys into `section (id, term_id)`
    and `week (id, term_id)`, as `response` has), its author as a `person` key
    (`RESTRICT`), the role the author wrote under, whether the text was seeded
    from an AI draft, the text, the time, and the database's `sequence`.
    `CHECK`s: the role is one of three; the text holds a character `str.strip()`
    would keep and is at most 4000 characters;
  - `response_policy`: one change to a prefix's policy, the person who set it
    (`RESTRICT`), the role they set it under, the mode, the time, and `sequence`.
    `CHECK`s: the role is one of two and the mode is one of two;
  - `response_loop_grants_v001.sql`: `pulse_app`'s `SELECT` on both, and its
    `INSERT` at column grain, without `id` or `sequence`; no `UPDATE` or `DELETE`;
  - `section_staff_names_v001.sql`: the staff-name definer, its NOLOGIN owner
    `pulse_staff_name_definer` and that owner's column reads;
  - `response_loop_guard_v001.sql` (the fix round): a `BEFORE INSERT` trigger on
    each table, owned by the NOLOGIN `pulse_response_guard_definer`, refusing a
    row whose author or setter does not hold the stated role there, and a second
    author for one section-week.

**The constraint text is spelled out rather than read from `app.models.loop`**:
a migration records what was applied on the day it ran (E6-01's reasoning).

**The downgrade refuses while either table holds a row.** Going down drops both
tables, which are the record of every response and every policy change (the
owner's ruling 7 for E7), so it raises `RuntimeError` before touching anything,
as `20261009_f14324ab936c` does. Over empty tables it drops the triggers and the
three functions, empties their owners (the role itself stays, inert, as every earlier definer owner
does: `DROP ROLE` fails against any object elsewhere in the cluster), and drops
both tables, which takes `pulse_app`'s grants on them with them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

revision: str = "2c3d5a0de424"
down_revision: str | Sequence[str] | None = "b7d2e94c1a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INSTRUCTOR_RESPONSE = "instructor_response"
RESPONSE_POLICY = "response_policy"

# Every character Python's `str.strip()` removes, by code point, as
# `20261010_e403cc44bfc0` writes it for `moderation_state.reason`.
NOT_ONLY_WHITESPACE = (
    "~ '[^\\u0009-\\u000d\\u001c-\\u001f \\u0085\\u00a0\\u1680\\u2000-\\u200a"
    "\\u2028\\u2029\\u202f\\u205f\\u3000]'"
)

DROP_THE_GUARDS = (
    "DROP TRIGGER instructor_response_is_written_by_its_role ON public.instructor_response",
    "DROP FUNCTION public.instructor_response_is_written_by_its_role()",
    "DROP TRIGGER response_policy_is_set_by_its_role ON public.response_policy",
    "DROP FUNCTION public.response_policy_is_set_by_its_role()",
)
DROP_THE_DEFINER = "DROP FUNCTION public.section_staff_names(uuid, uuid, uuid)"

# The guard owner's reads of `instructor_response` go with the table.
EMPTY_THE_GUARD_ROLE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_response_guard_definer'
    ) THEN
        REVOKE SELECT (person_id, role, section_id, department_id)
            ON public.role_assignment FROM pulse_response_guard_definer;
        REVOKE SELECT (person_id, course_id)
            ON public.lead_faculty_mapping FROM pulse_response_guard_definer;
        REVOKE SELECT (id, course_id) ON public.section FROM pulse_response_guard_definer;
        REVOKE SELECT (id, prefix_id) ON public.course FROM pulse_response_guard_definer;
        REVOKE SELECT (id, department_id) ON public.prefix FROM pulse_response_guard_definer;
    END IF;
END
$$;
"""

EMPTY_THE_DEFINER_ROLE = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_staff_name_definer') THEN
        REVOKE SELECT (id, identity_name) ON public.person FROM pulse_staff_name_definer;
        REVOKE SELECT (person_id, role, section_id, department_id)
            ON public.role_assignment FROM pulse_staff_name_definer;
        REVOKE SELECT (person_id, course_id)
            ON public.lead_faculty_mapping FROM pulse_staff_name_definer;
        REVOKE SELECT (user_id, section_id, started_on, ended_on)
            ON public.enrollment FROM pulse_staff_name_definer;
        REVOKE SELECT (id, course_id) ON public.section FROM pulse_staff_name_definer;
        REVOKE SELECT (id, prefix_id) ON public.course FROM pulse_staff_name_definer;
        REVOKE SELECT (id, department_id) ON public.prefix FROM pulse_staff_name_definer;
    END IF;
END
$$;
"""


def upgrade() -> None:
    """Apply this revision: the two records, their grants and the staff-name definer."""
    op.create_table(
        INSTRUCTOR_RESPONSE,
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("week_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("author_person_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("ai_seeded", sa.Boolean(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('INSTRUCTOR', 'LEAD_FACULTY', 'CHAIR')",
            name=op.f("ck_instructor_response_role_is_a_responding_role"),
        ),
        sa.CheckConstraint(
            f"length(body) <= 4000 AND body {NOT_ONLY_WHITESPACE}",
            name=op.f("ck_instructor_response_body_is_stated_and_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["author_person_id"],
            ["person.id"],
            name=op.f("fk_instructor_response_author_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "term_id"],
            ["section.id", "section.term_id"],
            name=op.f("fk_instructor_response_section_id_term_id_section"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["week_id", "term_id"],
            ["week.id", "week.term_id"],
            name=op.f("fk_instructor_response_week_id_term_id_week"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instructor_response")),
    )
    op.create_index(
        "ix_instructor_response_section_id_week_id",
        INSTRUCTOR_RESPONSE,
        ["section_id", "week_id"],
        unique=False,
    )

    op.create_table(
        RESPONSE_POLICY,
        sa.Column("prefix_id", sa.Uuid(), nullable=False),
        sa.Column("set_by_person_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('LEAD_FACULTY', 'CHAIR')",
            name=op.f("ck_response_policy_role_is_a_policy_role"),
        ),
        sa.CheckConstraint(
            "mode IN ('ENCOURAGED', 'REQUIRED')",
            name=op.f("ck_response_policy_mode_is_a_policy_mode"),
        ),
        sa.ForeignKeyConstraint(
            ["prefix_id"],
            ["prefix.id"],
            name=op.f("fk_response_policy_prefix_id_prefix"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["set_by_person_id"],
            ["person.id"],
            name=op.f("fk_response_policy_set_by_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_response_policy")),
    )
    op.create_index(
        "ix_response_policy_prefix_id_set_by_person_id_role_sequence",
        RESPONSE_POLICY,
        ["prefix_id", "set_by_person_id", "role", "sequence"],
        unique=False,
    )

    op.execute(read_sql("response_loop_grants_v001"))
    op.execute(read_sql("section_staff_names_v001"))
    op.execute(read_sql("response_loop_guard_v001"))


def downgrade() -> None:
    """Reverse this revision.

    Raises `RuntimeError`, having changed nothing, when `instructor_response` or
    `response_policy` holds a row: going down would destroy them.
    """
    connection = op.get_bind()
    held = {
        table: connection.execute(sa.text(f"SELECT count(*) FROM public.{table}")).scalar_one()  # noqa: S608
        for table in (INSTRUCTOR_RESPONSE, RESPONSE_POLICY)
    }
    if any(held.values()):
        counts = ", ".join(f"{count} in `public.{table}`" for table, count in held.items())
        raise RuntimeError(
            f"This database holds response-loop rows ({counts}). Going below this revision drops "
            "`instructor_response`, the record of every response students were shown and who "
            "wrote it, and `response_policy`, the record of every policy change and who made it, "
            "so it would destroy them. Nothing was changed. Keep the database at this revision, "
            "or export those rows and remove them deliberately first."
        )
    for statement in DROP_THE_GUARDS:
        op.execute(statement)
    op.execute(EMPTY_THE_GUARD_ROLE)
    op.execute(DROP_THE_DEFINER)
    op.execute(EMPTY_THE_DEFINER_ROLE)

    op.drop_index(
        "ix_response_policy_prefix_id_set_by_person_id_role_sequence", table_name=RESPONSE_POLICY
    )
    op.drop_table(RESPONSE_POLICY)
    op.drop_index("ix_instructor_response_section_id_week_id", table_name=INSTRUCTOR_RESPONSE)
    op.drop_table(INSTRUCTOR_RESPONSE)
