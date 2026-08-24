"""E0-07 — reaching the section-code service without naming what it is made of.

`section_codes` is shared rather than written in a test module because two
modules ask the same question of it — the parsing unit tests and the derivation
integration tests — and E0-07 spells the service's *file* and none of its
callables, so "which function parses a code" is a rule that would drift if it
were written twice (`docs/MISTAKES.md` entry 13). What it does and what it
deliberately refuses to decide is written on the class.
"""

import importlib
import inspect
from collections.abc import Mapping
from types import ModuleType
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# E0-07 — reaching the section-code service without naming what it is made of.
# ---------------------------------------------------------------------------

# Spelled by E0-07's scope: "`backend/app/services/section_codes.py`". The
# package root is `backend/`, so the import path is `app.services....`.
SECTION_CODE_MODULE = "app.services.section_codes"

# What a value the tests can supply is *for*, matched against a parameter's
# name. E0-07 says the derivation takes "the code and the section's term" and
# says nothing about whether a session is passed, whether the term arrives as a
# model instance or a key, or what any of it is called — so the tests offer
# every value they have and let the signature take what it wants. Matching is by
# exact name or by `_`-suffix, longest alias first, so `section_code` is a code
# and `course_week` is a course week rather than a bare week.
SERVICE_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db"),
    "code": ("code", "section_code"),
    "term": ("term",),
    "term_id": ("term_id",),
    "section": ("section",),
    "course_week": ("course_week", "week"),
}


class SectionCodeService:
    """E0-07's service, found rather than named.

    **Every identifier inside the module is discovered.** The ticket names the
    file and the four values the derivation produces — `length_weeks`,
    `start_date`, `end_date`, `modality` — and nothing else: not the parse
    function, not the derivation function, not the offset function, not the error
    classes, not the shape a parsed code comes back in. Naming any of them here
    would make the implementer build to this fixture instead of to the ticket,
    which is the failure `tests/integration/test_term_calendar_schema.py`'s
    `week_producer` avoids the same way.

    So a callable is looked up by a fragment of its name, and the answer has to
    be unambiguous: none, or two that this cannot choose between, is a failure
    that lists what the module defines and says which choice would settle it.
    Module-level functions and the `classmethod`/`staticmethod` members of
    module-level classes both count, because `SectionCode.parse` and
    `parse_section_code` are equally reasonable and the ticket rules out neither.

    **What this does not do is decide anything.** Where a test needs a name that
    E0-07 leaves open it fails saying so, rather than guessing quietly and
    passing against a design the ticket never asked for.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    # -- reaching the module and its callables ------------------------------

    @property
    def module(self) -> ModuleType:
        """`app.services.section_codes`, or a failure naming the missing file.

        A `ModuleNotFoundError` for some *other* module is re-raised untouched:
        a service that exists and imports something absent and a service that
        was never written need different fixes, and a test must not report them
        as the same thing. `import_app_module` above makes the same distinction
        for the same reason.
        """
        if self._module is None:
            try:
                self._module = importlib.import_module(SECTION_CODE_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == SECTION_CODE_MODULE or SECTION_CODE_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{SECTION_CODE_MODULE}` module. E0-07's scope puts the parser "
                    "and the date derivation in `backend/app/services/section_codes.py` (SPEC "
                    "§13 gives `services/` that job, and the ticket names the file)."
                )
        return self._module

    def defined_callables(self) -> dict[str, Any]:
        """Every public callable the service module defines itself.

        Defines *itself*: a function imported from somewhere else is not part of
        this module's surface, and counting one would let an imported `parse`
        from the standard library answer for the ticket's deliverable.
        """
        found: dict[str, Any] = {}
        for name, value in vars(self.module).items():
            if name.startswith("_"):
                continue
            if getattr(value, "__module__", None) != SECTION_CODE_MODULE:
                continue
            if inspect.isfunction(value):
                found[name] = value
            elif inspect.isclass(value):
                for attribute, member in vars(value).items():
                    if attribute.startswith("_") or not isinstance(
                        member, classmethod | staticmethod
                    ):
                        continue
                    bound = getattr(value, attribute, None)
                    if callable(bound):
                        found[f"{name}.{attribute}"] = bound
        return found

    def callable_named_after(self, fragments: tuple[str, ...], purpose: str, quoting: str) -> Any:
        """The one callable whose name carries one of `fragments`.

        Fragments are tried in order, so a module that spells the derivation
        `derive_section_calendar` is found by "deriv" without "calendar" ever
        being consulted. A fragment matching more than one callable stops rather
        than picking: two candidates mean this cannot tell which one the ticket
        is about, and choosing would be the test deciding. A module-level
        function is preferred over a class member of the same name, since a
        `SectionCode.parse` that delegates to `parse` is one deliverable and not
        two.
        """
        defined = self.defined_callables()
        for fragment in fragments:
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
                    f"`{SECTION_CODE_MODULE}` defines more than one callable whose name carries "
                    f"{fragment!r} ({sorted(matches)}), so this cannot tell which one {purpose}. "
                    "Naming one here would pin an interface E0-07 leaves open — say in the pull "
                    "request which it is, and `SectionCodeService` in tests/conftest.py is the "
                    "one place that changes."
                )
            if matches:
                return next(iter(matches.values()))
        pytest.fail(
            f"`{SECTION_CODE_MODULE}` defines no callable whose name carries any of "
            f"{list(fragments)} — it defines {sorted(defined)}. E0-07's scope: {quoting} The "
            "callable is looked for by name rather than imported under an agreed one because no "
            "ticket spells it; if it is there under a name none of these fragments reaches, that "
            "is a defect in this fixture rather than in the service."
        )

    @property
    def parse(self) -> Any:
        """The callable that turns a section code into its three parts."""
        return self.callable_named_after(
            ("parse", "from_code"),
            "parses a section code",
            "'parse a code into start letter, ordinal, and modality; reject malformed codes with "
            "a specific error naming what failed'.",
        )

    @property
    def derive(self) -> Any:
        """The callable that turns a code plus a term into a section's calendar."""
        return self.callable_named_after(
            ("deriv", "calendar", "dates"),
            "derives a section's calendar",
            "'Derive `length_weeks`, `start_date`, `end_date`, and `modality` from the code and "
            "the section's term, reading `start_letter_map`'.",
        )

    @property
    def writer(self) -> Any:
        """The callable that puts a derived calendar onto a section.

        E0-07's scope: "Add the derived section columns and populate them through
        this service, so there is exactly one path that sets them." That sentence
        names a writer and, like everything else here, does not name the
        function — so it is found the same way, by a fragment of its name, with
        "apply" first because applying a code to a section is what the ticket
        describes it doing.
        """
        return self.callable_named_after(
            ("apply", "populate", "assign", "fill", "write"),
            "writes a derived calendar onto a section",
            "'Add the derived section columns and populate them through this service, so there "
            "is exactly one path that sets them'.",
        )

    @property
    def offset(self) -> Any:
        """The callable that relates a section's course weeks to its term's weeks."""
        return self.callable_named_after(
            ("offset", "term_week", "week"),
            "converts between the course-week and term-week axes",
            "'The offset arithmetic belongs here', and the last acceptance criterion: "
            "'Course-week to term-week offset is computed and tested for a section that starts "
            "five weeks into a term'.",
        )

    # -- calling one --------------------------------------------------------

    @staticmethod
    def role_of(parameter_name: str) -> str | None:
        """Which of `SERVICE_ROLES` a parameter called `parameter_name` wants."""
        best: tuple[int, str] | None = None
        for role, aliases in SERVICE_ROLES.items():
            for alias in aliases:
                if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                    best is None or len(alias) > best[0]
                ):
                    best = (len(alias), role)
        return None if best is None else best[1]

    def call(self, function: Any, **available: Any) -> Any:
        """Call `function`, filling each parameter from the roles offered.

        Binding by parameter name rather than by position, and never by
        `try: ... except TypeError:`, is deliberate. A helper that retried
        several call shapes until one stopped raising would swallow a `TypeError`
        raised *inside* the service, and would report a design the ticket never
        chose as working — the shape of `docs/MISTAKES.md` entry 3. This way a
        parameter that no offered role matches stops the test with a message
        naming it, which is a defect in this fixture or an interface question for
        the ticket, and either way something to see rather than route around.

        One narrow accommodation: a single-parameter callable is handed the one
        value the caller offered, whatever it is named. `parse(raw)` and
        `parse(code)` are the same deliverable, and the parameter's name is not
        something E0-07 decides.
        """
        signature = inspect.signature(function)
        parameters = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        if len(parameters) == 1 and len(available) == 1:
            only = next(iter(available.values()))
            if parameters[0].kind is parameters[0].POSITIONAL_ONLY:
                return function(only)
            return function(**{parameters[0].name: only})

        positional: list[Any] = []
        keyword: dict[str, Any] = {}
        for parameter in parameters:
            role = self.role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(function, '__qualname__', function)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}. E0-07 says the derivation takes 'the code and the "
                    "section's term' and spells no signature, so a parameter outside that is an "
                    "interface question for the ticket — add the role to `SERVICE_ROLES` in "
                    "tests/conftest.py once the pull request says what it is for."
                )
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]
        return function(*positional, **keyword)

    # -- reading what came back ---------------------------------------------

    @staticmethod
    def part(subject: Any, candidates: tuple[str, ...], label: str) -> Any:
        """One named part of a parsed or derived result, however it is carried.

        A mapping key or an attribute, because E0-07 does not say whether the
        result is a dataclass, a Pydantic model, a `NamedTuple` or a dict, and
        all four answer to a name. A plain tuple does not, and is a failure here
        rather than an index this file invents an order for.
        """
        for candidate in candidates:
            if isinstance(subject, Mapping) and candidate in subject:
                return subject[candidate]
            if hasattr(subject, candidate):
                return getattr(subject, candidate)
        pytest.fail(
            f"{subject!r} carries none of {list(candidates)}, so this test cannot read the "
            f"{label} out of it. E0-07 names the parts — 'start letter, ordinal, and modality', "
            "and `length_weeks`, `start_date`, `end_date`, `modality` — without saying what "
            "carries them; the candidates are a constant in the test module and a deliberate "
            "rename is a one-line change there."
        )

    @staticmethod
    def raised_by_the_service(failure: BaseException) -> bool:
        """Whether `failure` is an error this project defines, not one that leaked.

        E0-07's definition of done: section codes arrive from the LMS, so confirm
        "no exception type that escapes as a 500". A `KeyError` off a letter-map
        lookup, an `IndexError` off a short string and a `ValueError` out of
        `int()` are all what an unguarded parser raises, and none of them is
        something a caller can catch on purpose.
        """
        return type(failure).__module__.split(".")[0] == "app"


@pytest.fixture
def section_codes() -> SectionCodeService:
    """E0-07's service, reached by discovery. See `SectionCodeService` above."""
    return SectionCodeService()
