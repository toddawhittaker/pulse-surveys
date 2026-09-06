"""Nothing under `backend/` names a student to a callee any more — ticket E4-01.

E4-01's first acceptance criterion has two halves. The behavioural half — the
signature refuses the call — is
`tests/integration/test_the_reveal_derives_its_subject.py`. This is the other
half, in the ticket's own words: "a grep for the old parameter name over
`backend/` comes back empty outside history."

**Why a sweep rather than trusting the signature test.** The criterion is that
*no code path* carries a caller-supplied identifier into the reveal as its
subject. A signature test answers for one function; a second caller written
against a helper of its own, or a shim kept for a later migration, is exactly the
"compatibility shim" the ticket's scope forbids and is invisible from the
signature. A sweep answers for the tree.

**What is flagged, and why it is not a text search.** Two shapes, read off the
syntax tree: a **function parameter** spelled `subject_user_id`, and a **call
keyword** spelled `subject_user_id`. Both are somebody naming a student across a
boundary. Everything else that mentions those characters is left alone on
purpose, and the allowed sample below is built out of the four real ones:

  - `sa.Column("subject_user_id", …)` and `ForeignKeyConstraint(["subject_user_id"])`
    — the `audit_log` column, which is SPEC §8's and is not touched by this
    ticket. §4 requires the record to name the student who was revealed; the
    column is the record, not the caller;
  - `row.subject_user_id` — reading that column back;
  - `subject_user_id: Mapped[UUID]` — declaring it on the model;
  - `in_subject_user_id` — the `record_identity_reveal` definer's own parameter
    (E0-26 item 1 settled that signature, and E4-01's ADR keeps the database
    function's contract deliberately untouched, its narrowing belonging to E10
    with the case model). It is a **different name**, and a sweep that matched it
    would demand a change the ticket says not to make.

**A red control means these tests are broken, not the code.** The four control
tests at the foot of this module run the sweep over sources whose answer is known
— two it must flag, one it must leave alone, and one asserting it read real files
at all. `docs/MISTAKES.md` entry 3 is the rule they exist for: a pattern searched
against a file is run against the text you claim it catches *and* against the text
you claim it allows, and given a canary, so that a search which has gone blind
says so. An empty offender list from a sweep that parsed nothing is a green that
means nothing at all.
"""

import ast
from pathlib import Path

import pytest
from fixtures.care_subject import DELETED_SUBJECT_PARAMETER

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

# The module the reveal lives in, used as this sweep's canary: it is certainly
# under `backend/`, so a sweep that does not reach it has not read the tree.
CARE_SERVICE = BACKEND_ROOT / "app" / "services" / "safety.py"

# The definer's parameter, which is a different name and must stay reachable.
DEFINER_PARAMETER = f"in_{DELETED_SUBJECT_PARAMETER}"

FLAGGED_AS_A_PARAMETER = (
    "def reveal_identity(*, actor_person_id, subject_user_id, case_id=None):\n" "    return None\n"
)

FLAGGED_AS_A_CALL_KEYWORD = (
    "from app.services.safety import reveal_identity\n"
    "\n"
    "def render(scope, row):\n"
    "    return reveal_identity(actor_person_id=scope.person_id, subject_user_id=row.user_id)\n"
)

ALLOWED = (
    "import sqlalchemy as sa\n"
    "from sqlalchemy import text\n"
    "\n"
    "audit_log = sa.Table(\n"
    '    "audit_log",\n'
    "    sa.MetaData(),\n"
    '    sa.Column("subject_user_id", sa.Uuid()),\n'
    ")\n"
    "\n"
    "class AuditLog:\n"
    "    subject_user_id: str\n"
    "\n"
    "def record(connection, actor, subject):\n"
    "    statement = text(\n"
    '        "SELECT public.record_identity_reveal("\n'
    '        ":in_actor_person_id, :in_subject_user_id, :in_case_id)"\n'
    "    )\n"
    "    row = connection.execute(\n"
    "        statement.bindparams(in_actor_person_id=actor, in_subject_user_id=subject)\n"
    "    ).one()\n"
    "    return row.subject_user_id\n"
)


def names_a_student(tree: ast.AST) -> set[str]:
    """Every place in one parsed source that spells `subject_user_id` as a name.

    A parameter or a call keyword: the two shapes in which one piece of code
    hands a student's identifier to another. A string, an attribute and an
    annotated assignment are none of those, which is what keeps the `audit_log`
    column and the definer's own parameter out of the answer.

    Answers a set of short descriptions rather than a bare count, so a failure
    says which shape it found.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            arguments = node.args
            declared = [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                *([arguments.vararg] if arguments.vararg else []),
                *([arguments.kwarg] if arguments.kwarg else []),
            ]
            name = getattr(node, "name", "<lambda>")
            found |= {
                f"parameter of {name}()"
                for argument in declared
                if argument.arg == DELETED_SUBJECT_PARAMETER
            }
        if isinstance(node, ast.Call):
            found |= {
                "keyword argument in a call"
                for keyword in node.keywords
                if keyword.arg == DELETED_SUBJECT_PARAMETER
            }
    return found


def backend_sources() -> dict[Path, ast.AST]:
    """Every Python file under `backend/`, parsed.

    Parsed rather than read as text for the reason
    `tests/unit/test_care_session_is_bound_to_the_care_service.py` gives about its
    own sweep: a correct implementation is very likely to *say*
    `subject_user_id` in a comment or a docstring — "the caller no longer names a
    `subject_user_id`" is the sentence a careful author writes, and this ticket
    invites it — and a text search would turn that sentence into a failure and
    teach the next person to delete the explanation.
    """
    return {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(BACKEND_ROOT.rglob("*.py"))
    }


def test_no_function_and_no_call_under_backend_names_a_student_as_the_reveals_subject() -> None:
    """Criterion 1: the old parameter name is gone from the tree, not only from one signature.

    E4-01's scope: "Every existing caller and test of `reveal_identity` moves to
    the new signature in the same PR; no compatibility shim stays behind." A shim
    is precisely a second function that still takes the old parameter and forwards
    it, and it is what this catches and the signature test does not.

    **The canary runs first**: the Care service's own module has to be among the
    files this parsed. A sweep pointed at a path that does not exist, or one whose
    glob stopped matching, reports a clean tree exactly as a correct tree does
    (`docs/MISTAKES.md` entry 3).

    **The mutation this kills**: `def reveal_identity_by_user(*, actor_person_id,
    subject_user_id)` kept beside the new call for E10 to migrate later — green
    against every behavioural test in this ticket, and the composition the carried
    entry describes still reachable. **The near miss it tolerates**, deliberately:
    `in_subject_user_id`, the database function's parameter, which E4-01's ADR
    leaves untouched, and every mention of the `audit_log` column that the record
    is made of.
    """
    sources = backend_sources()
    assert CARE_SERVICE in sources, (
        f"{CARE_SERVICE.relative_to(REPO_ROOT)} is not among the {len(sources)} files this sweep "
        "parsed, so the sweep is not reading the tree it claims to answer for and an empty result "
        "below would mean nothing. E0-10 names that path and SPEC §13 gives it the Care queue."
    )

    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)}: {sorted(names_a_student(tree))}"
        for path, tree in sources.items()
        if names_a_student(tree)
    )
    assert not offenders, (
        f"These name `{DELETED_SUBJECT_PARAMETER}` as a parameter or a call keyword: "
        f"{offenders}.\n\n"
        "E4-01 deletes that parameter rather than deprecating it, because a reveal that accepts a "
        "bare student key is the composition `docs/tickets/e1/carried-from-e0.md` records: "
        "`section_roster` hands instructor-scoped code the `user_id` of every enrolled student, "
        "and the reveal used to take exactly that value from whoever called it. The subject is "
        f"derived server-side from the record instead.\n\n"
        f"`{DEFINER_PARAMETER}` — the `record_identity_reveal` definer's own parameter — is a "
        "different name and is not flagged: E4-01's ADR keeps the database function's contract "
        "deliberately untouched, and narrowing it belongs to E10 with the case model."
    )


# ---------------------------------------------------------------------------
# The controls. **These must be green, always.** A red one means this module is
# broken rather than the code under it: the sweep has stopped seeing what it
# claims to see, or has started seeing what it claims to allow, and until it is
# fixed the test above is not evidence of anything.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sample", "described"),
    (
        (FLAGGED_AS_A_PARAMETER, "a function declaring it as a parameter"),
        (FLAGGED_AS_A_CALL_KEYWORD, "a caller passing it as a keyword"),
    ),
)
def test_the_sweep_flags_the_two_shapes_it_claims_to_catch(sample: str, described: str) -> None:
    """Control: run the sweep over the text it must catch, and require it to say so.

    Both shapes, because they are two different criteria wearing one name: the
    first is the reveal still accepting a student key, and the second is a caller
    still supplying one. A sweep that caught only the declaration would report a
    clean tree over a module that calls a shim in another file.
    """
    found = names_a_student(ast.parse(sample))
    assert found, (
        f"The sweep reports nothing over {described}:\n\n{sample}\n"
        "It is therefore blind to the shape it exists to find, and its silence over `backend/` "
        "says nothing about the tree."
    )


def test_the_sweep_allows_the_column_the_record_is_made_of_and_the_definers_parameter() -> None:
    """Control: the four legitimate mentions stay legitimate.

    `audit_log.subject_user_id` is SPEC §8's column and §4's record — the reveal
    writes it, which is the whole point of the door — and `in_subject_user_id` is
    the definer's parameter, which this ticket deliberately does not touch. A
    sweep that flagged either would demand a change the ticket forbids, and the
    cheapest way to make it pass would be to delete the record.
    """
    assert not names_a_student(ast.parse(ALLOWED)), (
        f"The sweep flags this source:\n\n{ALLOWED}\n"
        "Every mention in it is either the `audit_log` column being declared, read or written by "
        f"name, or `{DEFINER_PARAMETER}` — the database function's own parameter. Flagging them "
        "makes the sweep an argument for removing §4's record, which is the opposite of what E4-01 "
        "is for."
    )
