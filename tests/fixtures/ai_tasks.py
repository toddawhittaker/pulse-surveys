"""Reaching the comment-validity task without naming it — E2-07's tool side.

E2-07's second acceptance criterion is asserted "from the tool side": the mock
answers wrongly on purpose and what a test measures is the *gateway's* reaction,
row by row of ADR 0056's taxonomy. That means calling the validity task, and no
ticket has ever spelled its name.

**So the task is found rather than imported.** SPEC §13 places the module —
"`ai/tasks.py` — validity / moderation / summary / draft / draft-check calls" —
and the callable is matched by a word from the task's own name, then called by
filling its parameters from what a test has, by parameter name. Pinning a name
here would make the implementer build to this fixture instead of to the ticket.
A parameter no offered role matches stops the test with a message naming it,
which is an interface question for the ticket rather than something to guess at.

**This is the second copy of that mechanism, and the duplication is deliberate
rather than unnoticed.** `tests/integration/test_ai_gateway_validity_roundtrip.py`
holds E0-13's, inside the module that wrote it, and the alternative to a copy
here was importing one test module from another — a dependency on where pytest
put `tests/` on `sys.path` for the *test* modules, which
`tests/integration/test_mock_lms_wrong_launches.py` refuses for its own reasons
and which turns a rename in an E0 module into a collection error in an E2 one. An
import error is not a red. What keeps the two from drifting into disagreement is
that neither holds an expectation: both discover the same public callable, and if
they ever find different ones that is a defect in `app.ai.tasks` rather than in
either file. Folding E0-13's module onto this one is a tidy-up for a ticket whose
subject is that module.

**The failure classes are named rather than discovered**, and that is the
opposite choice for a good reason: ADR 0056 settles all four by name, records
that "the four classes are the interface E2 branches on", and E2-07's whole
second criterion is about telling two of them apart. A test that discovered them
would agree with a gateway that had collapsed them into one.
"""

import asyncio
import inspect
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import Any

import pytest

from fixtures.mock_ai import ALL_VERDICTS

# SPEC §13's placement for both modules.
TASKS_MODULE = "app.ai.tasks"
GATEWAY_MODULE = "app.ai.gateway"

# The four classes ADR 0056's table names, and their common base. Transcribed
# from the ADR, which is the record that settles them.
GATEWAY_ERROR_BASE = "AIGatewayError"
UNAVAILABLE_ERROR = "AIProviderUnavailableError"
UNREACHABLE_ERROR = "AIProviderUnreachableError"
REFUSED_ERROR = "AIProviderRefusedError"
RESPONSE_INVALID_ERROR = "AIResponseInvalidError"
TAXONOMY_ERRORS = (
    GATEWAY_ERROR_BASE,
    UNAVAILABLE_ERROR,
    UNREACHABLE_ERROR,
    REFUSED_ERROR,
    RESPONSE_INVALID_ERROR,
)

# How the validity task is recognised, and what a value this fixture can supply
# is for. Both are `test_ai_gateway_validity_roundtrip.py`'s lists, kept
# identical on purpose: two discoveries that looked for different callables would
# be two tickets testing two different programs.
VALIDITY_FRAGMENTS = ("validity", "valid", "classify_comment")
CALL_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db", "database"),
    "comment": ("comment", "text", "body", "content", "answer", "comment_text"),
}


def defined_callables(module: ModuleType) -> dict[str, Any]:
    """Every public callable the module defines itself.

    Defines *itself*: a function imported from somewhere else is not part of this
    module's surface. Module-level functions and the `classmethod`/`staticmethod`
    members of module-level classes both count.
    """
    found: dict[str, Any] = {}
    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if getattr(value, "__module__", None) != module.__name__:
            continue
        if inspect.isfunction(value):
            found[name] = value
        elif inspect.isclass(value):
            for attribute, member in vars(value).items():
                if attribute.startswith("_") or not isinstance(member, classmethod | staticmethod):
                    continue
                bound = getattr(value, attribute, None)
                if callable(bound):
                    found[f"{name}.{attribute}"] = bound
    return found


def validity_task(import_app_module: Callable[[str], ModuleType | None]) -> Any:
    """The one callable in `app.ai.tasks` that runs the comment-validity task."""
    module = import_app_module(TASKS_MODULE)
    if module is None:
        pytest.fail(
            f"There is no `{TASKS_MODULE}` module, so there is no tool side to assert E2-07's "
            "second criterion from. SPEC §13 places it and E0-13 shipped it."
        )
    defined = defined_callables(module)
    for fragment in VALIDITY_FRAGMENTS:
        matches = {
            name: value
            for name, value in defined.items()
            if fragment in name.rsplit(".", maxsplit=1)[-1].lower()
        }
        if len(matches) > 1:
            unqualified = {name: value for name, value in matches.items() if "." not in name}
            if len(unqualified) == 1:
                return next(iter(unqualified.values()))
            pytest.fail(
                f"`{TASKS_MODULE}` defines more than one callable whose name carries "
                f"{fragment!r} ({sorted(matches)}), so this cannot tell which one is the "
                "comment-validity task. `VALIDITY_FRAGMENTS` in this file is the one line that "
                "changes."
            )
        if matches:
            return next(iter(matches.values()))
    pytest.fail(
        f"`{TASKS_MODULE}` defines no callable whose name carries any of "
        f"{list(VALIDITY_FRAGMENTS)} — it defines {sorted(defined)}."
    )


def role_of(parameter_name: str) -> str | None:
    """Which of `CALL_ROLES` a parameter called `parameter_name` wants."""
    best: tuple[int, str] | None = None
    for role, aliases in CALL_ROLES.items():
        for alias in aliases:
            if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                best is None or len(alias) > best[0]
            ):
                best = (len(alias), role)
    return None if best is None else best[1]


def call_task(task: Any, **available: Any) -> Any:
    """Call `task`, filling each parameter from the values offered, by name.

    Binding by parameter name and never by `try: ... except TypeError:`: a helper
    that retried call shapes until one stopped raising would swallow a
    `TypeError` raised *inside* the task and report a design nobody chose as
    working. A coroutine function is awaited, because nothing settles whether the
    gateway's entry point is synchronous and choosing here would decide it from
    the test side.
    """
    signature = inspect.signature(task)
    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]

    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    if len(parameters) == 1 and role_of(parameters[0].name) is None:
        only = available["comment"]
        if parameters[0].kind is parameters[0].POSITIONAL_ONLY:
            positional.append(only)
        else:
            keyword[parameters[0].name] = only
    else:
        for parameter in parameters:
            role = role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(task, '__qualname__', task)}` requires a parameter "
                    f"`{parameter.name}` that this fixture has nothing to fill from. It is "
                    f"offering {sorted(available)}. Add the role to `CALL_ROLES` in "
                    "tests/fixtures/ai_tasks.py once the pull request says what it is for."
                )
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]

    outcome = task(*positional, **keyword)
    if inspect.isawaitable(outcome):
        return asyncio.run(_awaited(outcome))
    return outcome


async def _awaited(outcome: Any) -> Any:
    return await outcome


def verdict_token(result: Any) -> str:
    """The verdict a returned contract object carries, as the token it stores.

    Found by value rather than by field name, because §7.4 settles the three
    tokens and no ticket settles the field. ADR 0030 makes a member's value "the
    token stored, serialised and compared everywhere outside Python", so a JSON
    dump is where the token is.
    """
    dump = getattr(result, "model_dump", None)
    if not callable(dump):
        pytest.fail(
            f"The validity task returned {result!r}, which is not a Pydantic model. SPEC §7.4: "
            "'every task declares its output as a Pydantic model rather than parsed JSON'."
        )
    found = [value for value in dump(mode="json").values() if value in ALL_VERDICTS]
    if len(found) != 1:
        pytest.fail(
            f"The object the validity task returned carries {found} of §7.4's verdicts "
            f"{list(ALL_VERDICTS)} — it dumps as {dump(mode='json')!r}. This fixture reads the "
            "verdict by value because no ticket spells the field's name."
        )
    return str(found[0])


@pytest.fixture
def verdict_of_result() -> Callable[[Any], str]:
    """Hand `verdict_token` to a test, so the reading is done in one place."""
    return verdict_token


@pytest.fixture
def classify_comment(
    import_app_module: Callable[[str], ModuleType | None],
    db_session: Any,
) -> Callable[[str], Any]:
    """Run the comment-validity task over a comment, against whatever is configured.

    The task is discovered inside the call rather than at fixture setup, so a test
    that points `AI_PROVIDER_BASE_URL` somewhere in its own body is pointing the
    module that is about to be imported: `import_app_module` drops every `app.*`
    module first, and a gateway that builds something out of `Settings` at import
    time then builds it out of what the test set (`docs/MISTAKES.md` entry 3).
    """

    def run(comment: str) -> Any:
        return call_task(validity_task(import_app_module), session=db_session, comment=comment)

    return run


@pytest.fixture
def gateway_errors(
    import_app_module: Callable[[str], ModuleType | None],
) -> Iterator[Callable[[str], type[BaseException]]]:
    """Look one of ADR 0056's failure classes up by name, or fail saying it is missing.

    Named rather than discovered: ADR 0056 makes the four classes "the interface
    E2 branches on", and a test that discovered them would agree with a gateway
    that had collapsed them into one — which is precisely the state that record
    exists to have left behind.
    """

    def named(name: str) -> type[BaseException]:
        module = import_app_module(GATEWAY_MODULE)
        if module is None:
            pytest.fail(f"There is no `{GATEWAY_MODULE}` module. SPEC §13 places it.")
        found = getattr(module, name, None)
        if not (isinstance(found, type) and issubclass(found, BaseException)):
            pytest.fail(
                f"`{GATEWAY_MODULE}` exposes no exception class `{name}` (it exposes "
                f"{sorted(n for n in vars(module) if not n.startswith('_'))}). ADR 0056's table "
                f"names {list(TAXONOMY_ERRORS)}, and E2-07's second criterion is about telling "
                "two of them apart."
            )
        return found

    yield named
