"""No service opens a session against an identity table — ticket E0-11.

E0-11's acceptance criterion: "Every read helper in the module goes through the
E0-10 views; a test asserts no code path in `services/` opens a raw session
against an identity table."

SPEC §8 is what makes it an invariant rather than a layering preference:
"instructor/leadership read paths go through views that structurally cannot join
to `user` identity columns — enforced in the database, not just the application.
Only the Care role's queue path can reach identity, and only via the audited
reveal action."

**This is the application-side half of a guarantee whose other half is a grant.**
`tests/integration/test_identity_grants.py` asserts that the connection those
paths run on is *refused* `user_identity` by Postgres, which is the half that
holds against a careless query. This one catches the query before it is written,
and it reaches the two tables a grant does not stop: `person` and `user` are
readable by `pulse_app` for all this file knows, and `person` is where SPEC §2.1
keeps a name — "person records (name, category)". A leadership roll-up that joins
to `person` to label a row has leaked an instructor's name into a view §4 says
carries none, and no grant refuses it.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_care_is_not_reachable_from_a_claim.py` gives: a correct
implementation is very likely to *say* `user_identity` in a docstring, because
"this never joins to `user_identity`" is the sentence a careful implementer
writes next to the query. Searching the text would turn that sentence into a
failure and teach the next person to delete the comment. So comments are absent
from the tree entirely, and docstrings are subtracted by name below.

**What it cannot see**, stated so nothing here is cited as more than it is
(`docs/MISTAKES.md` entry 14): a table name assembled at run time, a relation
reached through a mapper this file does not know the name of, and any read that
goes through a helper in another package. It is a tripwire on the obvious way to
write the wrong thing. The proof-shaped assertion is the grant.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = REPO_ROOT / "backend" / "app" / "services"

# The relations that carry, or lead directly to, a person's identity. `user` and
# `user_identity` are ADR 0001's split — "`user` holds the key and platform
# reference; `user_identity` holds name and email" — and `person` is SPEC §2.1's
# Pulse-owned people graph, which holds a name outright. All three are named in
# E0-11's scope for this sweep.
IDENTITY_RELATIONS = ("user_identity", "person", "user")

# A relation reference in SQL: the name in the position a statement reads or
# writes it from, optionally schema-qualified and optionally quoted. The keyword
# is what keeps `person_id` and `lms_user_id` out — they are columns, and every
# resolver in E0-11 is written over them.
RELATION_REFERENCE = re.compile(
    r"\b(?:from|join|into|update|delete\s+from|table)\s+"
    r"(?:public\s*\.\s*)?\"?(" + "|".join(IDENTITY_RELATIONS) + r")\"?\b",
    re.IGNORECASE,
)

# The ORM route to the same rows, which carries no SQL text for the regex above
# to find. Class names rather than table names, because that is what a mapped
# query names. **This file's choice** of spelling, following the tables they map.
IDENTITY_MODELS = ("UserIdentity", "User", "Person")

# The calls that turn a mapped class into rows. A bare reference to a model — a
# type annotation, an `isinstance` — is not a read, and flagging one would make
# the sweep fire on code that never touches the database.
QUERY_CALLS = ("select", "query", "get", "delete", "update", "insert", "exists", "scalar")

# Samples the sweeps are run against before they are believed. A pattern searched
# against text is a test that can go blind and report success
# (`docs/MISTAKES.md` entry 3), and these are the cheapest way to notice: one of
# each shape that has to be caught, and one of each that has to be allowed.
# Nothing here is executed — they are subjects for a regex, never queries.
SQL_MUST_CATCH = (
    "SELECT * FROM user_identity WHERE id = :id",
    'SELECT name FROM public."user_identity"',
    "SELECT 1 FROM section_roster JOIN person ON true",
    "UPDATE person SET category = 'staff'",
    'INSERT INTO "user" (lms_user_id) VALUES (:sub)',
    "select * from PUBLIC . USER_IDENTITY",
)

# **Two samples left this list in E1's boundary fix round (finding M8), and their
# absence is the point.** They were `SELECT * FROM section_roster WHERE section_id
# = :section_id` and `SELECT * FROM section_enrollment_count WHERE course_id =
# :course_id`, and they said something true of *this* sweep — neither names an
# identity table — in a shape that read as the suite sanctioning the query. It is
# not sanctioned. `pulse_app` holds an unfiltered read on both relations, and
# `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` now polices
# them — along with base `enrollment`, which they are defined over — outside four
# locations: `services/authz.py`, ADR 0100's development console, the `views_sql/`
# package where the statements live, and `services/safety.py`, which revalidates
# the holds-Care rule on the Care credential. Anywhere else, that statement is
# exactly the bypass this repository has a chokepoint to prevent. A test that
# holds up a forbidden query as an example of
# permitted text teaches the next reader the wrong rule, and the samples that
# remain make the same point about the same matcher without doing that.
SQL_MUST_ALLOW = (
    "SELECT role, person_id FROM role_assignment WHERE person_id = :person_id",
    "SELECT * FROM public.reveal_student_identity(:actor, :subject, NULL)",
    "SELECT course_id FROM lead_faculty_mapping WHERE person_id = :person_id",
    # Prose, which is where the identity tables are *supposed* to be named.
    "This never joins to user_identity; the grant refuses it anyway.",
)

MODEL_QUERY_MUST_CATCH = (
    "rows = session.execute(select(Person)).all()",
    "identity = session.get(UserIdentity, key)",
    "names = session.execute(select(User.id, UserIdentity.email)).all()",
)

# `counts = session.execute(select(SectionEnrollmentCount)).all()` left this list
# in the same change and for the same reason as the two SQL samples above: it is
# the ORM spelling of a read the org-view sweep now forbids outside those four,
# and holding it up here as permitted text contradicted that rule. What it was
# doing for *this* sweep — showing that a mapped class which is not an identity
# model passes — `RoleAssignment` already does.
MODEL_QUERY_MUST_ALLOW = (
    "rows = session.execute(select(RoleAssignment)).all()",
    "person_id: UUID = scope.person_id",
)


def parsed_services() -> dict[Path, ast.Module]:
    """Every module under `backend/app/services/`, parsed.

    A file that does not parse is a failure of the sweep rather than a module to
    skip: it would drop silently out of both halves below, and the half that
    matters is the one reporting what it did *not* find.
    """
    found: dict[Path, ast.Module] = {}
    for path in sorted(SERVICES_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            found[path] = ast.parse(source, filename=str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
    return found


def docstring_constants(tree: ast.AST) -> set[int]:
    """The identity of every string node that is a docstring rather than a value.

    Subtracted from the sweep so that prose naming an identity table stays legal.
    A module that explains why it cannot read `user_identity` is doing the right
    thing, and a test that punished the explanation would be training the next
    reader to remove it.
    """
    found: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = list(getattr(node, "body", []))
        if not body or not isinstance(body[0], ast.Expr):
            continue
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(id(first))
    return found


def executable_strings(tree: ast.AST) -> list[str]:
    """Every string constant in a module that is not a docstring."""
    excluded = docstring_constants(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in excluded
    ]


def identity_relations_named(source: str) -> list[str]:
    """Which identity relations a statement reads or writes, if any."""
    return sorted({match.group(1).lower() for match in RELATION_REFERENCE.finditer(source)})


def identity_models_queried(tree: ast.AST) -> list[str]:
    """Which identity models a module turns into rows, if any.

    Only inside a call that produces rows, so a type annotation or an import is
    not mistaken for a read. `select(User.id)` counts, because the attribute's
    value is the class.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = getattr(callee, "id", None) or getattr(callee, "attr", None) or ""
        if name.lower() not in QUERY_CALLS:
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            for inner in ast.walk(argument):
                spelling = getattr(inner, "id", None) or getattr(inner, "attr", None)
                if spelling in IDENTITY_MODELS:
                    found.add(spelling)
    return sorted(found)


def test_the_sweeps_in_this_file_catch_what_they_claim_to_and_allow_what_they_must() -> None:
    """Both matchers, run against both directions, before either is believed.

    `docs/MISTAKES.md` entry 3's rule for a pattern searched against text: "run it
    against the text you claim it catches *and* against the text you claim it
    allows". The allow side is the one that costs something here. Every read path
    E0-11 builds runs SQL naming `role_assignment` and `lead_faculty_mapping`, and
    half of those statements carry `person_id` in a `WHERE` clause — a sweep that
    fired on the column would be red against every correct implementation, and the
    fix somebody reaches for is to delete the sweep.

    **The E0-10 view samples are gone from that list, deliberately** (E1's
    boundary review, finding M8; the comment on `SQL_MUST_ALLOW` says why). They
    were legal text for this matcher and a forbidden query everywhere else, and an
    allow-list is read as a list of things it is fine to write. Removing them
    costs this test nothing: `role_assignment` and `lead_faculty_mapping` carry the
    `person_id` near miss that the allow side exists for.
    """
    for sample in SQL_MUST_CATCH:
        assert identity_relations_named(sample), (
            f"The relation sweep found no identity table in {sample!r}, which names one in the "
            "position a statement reads it from. A sweep that has gone blind reads exactly like a "
            "sweep that found nothing wrong."
        )
    for sample in SQL_MUST_ALLOW:
        found = identity_relations_named(sample)
        assert not found, (
            f"The relation sweep read {found} out of {sample!r}, which names no identity table in "
            "any position a statement reads one from. `person_id` is a column on "
            "`role_assignment` and every purview query in E0-11 is written over it, so a sweep "
            "that matches it is red against every correct implementation."
        )

    for sample in MODEL_QUERY_MUST_CATCH:
        assert identity_models_queried(
            ast.parse(sample)
        ), f"The model sweep found no identity model in {sample!r}, which turns one into rows."
    for sample in MODEL_QUERY_MUST_ALLOW:
        found = identity_models_queried(ast.parse(sample))
        assert (
            not found
        ), f"The model sweep read {found} out of {sample!r}, which queries no identity model."


def test_no_service_module_names_an_identity_table_in_a_statement_it_runs() -> None:
    """The criterion, over the SQL a service carries.

    §4's first line is that identity "is never displayed to instructors or any
    leadership role, in any view, including CSV exports", and §8 puts the
    enforcement in the database. The application-side rule is what keeps the
    database's job small: if no service names these tables, no view has to be
    audited for what a service might have joined to it.

    **The mutation this exists to survive** is a `JOIN person p ON p.id =
    a.person_id` added to a leadership query so a roll-up row can show a chair's
    name — SPEC §2.1's own display labels ask for exactly that ("department rows
    `N prefixes · N sections · Chair: {name}`"), so it is a change somebody makes
    on purpose, with a ticket behind it, in a service nobody is auditing. Where a
    name is genuinely required, it comes from a view that E0-10's rules have been
    applied to, not from a join written in `services/`.
    """
    modules = parsed_services()
    assert modules, (
        f"There are no Python modules under {SERVICES_ROOT.relative_to(REPO_ROOT)}, so this sweep "
        "looked at nothing and would report success. SPEC §13 puts the real application there — "
        "'`api/` routers stay thin and all real behavior lives in `services/`' — and E0-07 and "
        "E0-10 have already shipped modules into it."
    )

    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(
            {
                relation
                for statement in executable_strings(tree)
                for relation in identity_relations_named(statement)
            }
        )
        for path, tree in modules.items()
    }
    naming = {path: found for path, found in offenders.items() if found}
    assert not naming, (
        f"{naming} run SQL naming an identity table. E0-11: 'Every read helper in the module goes "
        "through the E0-10 views; a test asserts no code path in `services/` opens a raw session "
        "against an identity table.' SPEC §8: only the Care queue path may reach identity, and "
        "only through the audited reveal. Two of these three tables are not protected by a grant "
        "— `person` holds a name outright (§2.1) and nothing refuses `pulse_app` a read of it — "
        "so this sweep is the only thing between a roll-up label and a name in a leadership view."
    )


def test_no_service_module_turns_an_identity_model_into_rows() -> None:
    """The same rule by the route that carries no SQL for the sweep above to read.

    `select(Person)` is the shorter way to write the join the previous test
    forbids, and it is the way somebody working in a service that already imports
    the models will write it. Neither test implies the other: one reads strings,
    one reads calls, and a module can do either without doing the other.
    """
    modules = parsed_services()
    assert modules, (
        f"There are no Python modules under {SERVICES_ROOT.relative_to(REPO_ROOT)} to sweep; the "
        "test above diagnoses that."
    )

    querying = {
        str(path.relative_to(REPO_ROOT)): identity_models_queried(tree)
        for path, tree in modules.items()
        if identity_models_queried(tree)
    }
    assert not querying, (
        f"{querying} query an identity model directly. The read paths in `services/` go through "
        "the E0-10 views (SPEC §8, E0-11's third criterion); a mapped query goes to the table, "
        "and the view exists precisely because the table cannot be trusted to be joined "
        "carefully."
    )
