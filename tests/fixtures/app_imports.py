"""Importing a package called `app`, whichever of the three is meant.

**Every `sys.meta_path` manipulation in the suite is here, and so is every shared
fixture that saves and restores the `app` package in `sys.modules`.** This
repository's backend, `mock-lms/` and `mock-idp/` all answer to the name `app`
(SPEC §13), so an import of one is a decision about which program is under test,
and the save/restore contracts interact: `mock_package_resolved` drops the whole
package before installing its finder and puts back what it found, and
`import_app_module` does the same for the backend's. Two implementations of that
dance would be two copies of one rule (`docs/MISTAKES.md` entry 13), and a
`sys.meta_path` entry left behind by one would silently redirect the other.

Two things deliberately live elsewhere and neither touches this rule.
`fixtures/seed.py` registers `scripts/seed.py` in `sys.modules` under a name of
its own, `pulse_demo_seed`, which no package answers to; and
`tests/unit/test_db_engine_configuration.py` and `test_care_engine_configuration.py`
each drop the backend's `app` modules inside a test whose subject is what a
module builds at import. Both say why where they stand.
"""

import importlib
import inspect
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from importlib.machinery import PathFinder
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from fixtures.database import environment
from fixtures.lti_platform import (
    APPLICATION_FACTORY_NAMES,
    MOCK_LMS_DIR,
    MOCK_LMS_MODULES,
    MOCK_PACKAGE,
)


@pytest.fixture
def import_app_module() -> Iterator[Callable[[str], ModuleType | None]]:
    """Import an `app.*` module against the environment the test has just set.

    A module that builds something out of `Settings` reads the environment once,
    at import time, and `sys.modules` then keeps the result for the rest of the
    session. So a test that sets `REDIS_URL` and imports `app.jobs.celery_app`
    gets the value it set only if nothing imported that module earlier — and if
    something did, the test passes or fails for a reason it did not choose,
    which is `docs/MISTAKES.md` entry 3 in its purest form. Every `app.*` module
    is therefore dropped from `sys.modules` before the test body runs, and the
    set that was there is put back afterwards, so the interpreter is left as it
    was found.

    The returned callable answers `None` for a module that does not exist, so a
    test reports a failed assertion naming the missing deliverable rather than a
    collection error — the same choice `load_yaml` makes above, for the same
    reason. An `ImportError` raised *inside* a module that does exist propagates
    untouched: a module that is broken and a module that was never written need
    different fixes, and a test must not report them as the same thing.
    """
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "app" or name.startswith("app.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    def import_module(name: str) -> ModuleType | None:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            absent = exc.name
            if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                return None
            raise

    try:
        yield import_module
    finally:
        for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


class MockPackageFinder:
    """Resolve the `app` package out of one mock's directory for the length of an import.

    A mock is a second application whose package is *also* called `app`
    (SPEC §13), and this repository's own `app` is importable in the test
    process. Putting `mock-lms/` on `sys.path` is not enough to win that
    collision: an editable install of the backend registers a meta-path finder,
    and `sys.meta_path` is consulted before `sys.path` is, so a plain
    `import app` would return the backend's package on a developer's machine and
    possibly the mock's in CI — the same test measuring two different programs
    depending on how the project was installed.

    So the resolution is made explicit and temporary: this finder goes on the
    front of `sys.meta_path`, answers for `app` and everything under it out of
    the directory it was given, and comes off again. Nothing outside the import
    sees it.

    **It takes the directory as an argument**, which it did not when E0-14 wrote
    it, because E0-16 adds a second mock with exactly the same collision. Two
    copies of this class would be two copies of one rule about `sys.meta_path`,
    which is the shape `docs/MISTAKES.md` entry 13 is about.
    """

    def __init__(self, root: Path, package: str = MOCK_PACKAGE) -> None:
        self.root = root
        self.package = package

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != self.package and not fullname.startswith(f"{self.package}."):
            return None
        parts = fullname.split(".")
        if len(parts) == 1:
            search = [str(self.root)]
        else:
            parent = sys.modules.get(".".join(parts[:-1]))
            search = list(getattr(parent, "__path__", []))
        return PathFinder.find_spec(fullname, search)


@contextmanager
def mock_package_resolved(root: Path, package: str = MOCK_PACKAGE) -> Iterator[None]:
    """Resolve `package` out of `root` for the body, and put `sys.modules` back after.

    Split out of `import_mock_application` below when E0-16 needed to import a
    *class* out of a mock rather than its application — the settings object whose
    redirect-URI validation has no HTTP surface to be tested through. The finder
    dance is the same either way and a second copy of it would be two copies of
    one rule about `sys.meta_path` (`docs/MISTAKES.md` entry 13).

    **Held open for the whole of the caller's work, not just the import.** A class
    taken out of a mock and used after the resolution closed would re-resolve any
    lazy import against this repository's own `app`, which is a different program;
    keeping the finder in place until the caller is finished means a method that
    imports something at call time still gets the mock's module.
    """
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == package or name.startswith(f"{package}.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    finder = MockPackageFinder(root, package)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        for name in [n for n in list(sys.modules) if n == package or n.startswith(f"{package}.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def import_mock_application(
    root: Path,
    modules: Sequence[str],
    values: Mapping[str, str],
    *,
    absent_directory: str,
    nothing_found: str,
    package: str = MOCK_PACKAGE,
) -> Any:
    """Import one mock fresh, under `values`, and return its ASGI application.

    Fresh every time, and that is the property the per-run key tests on both
    mocks rest on: "keys are generated per run" is only observable if a second
    start really is a second start. Every module of the mock's package is dropped
    before the import and the previous set is put back after, exactly as
    `import_app_module` does above and for the same reason — a module cached in
    `sys.modules` answers with the environment some earlier test set.

    What is found is a `FastAPI` instance at module level, or a factory that
    returns one. Both are legal — `uvicorn --factory` is how this repository
    starts its own — and neither mock's ticket names one, so naming one here
    would make the implementer build to this fixture instead of to the ticket.

    The two failure messages are arguments rather than text written here, because
    the mechanism is shared between the mocks and the *ticket* a missing
    deliverable belongs to is not.
    """
    from fastapi import FastAPI

    if not root.is_dir():
        pytest.fail(absent_directory)

    imported: list[ModuleType] = []
    with mock_package_resolved(root, package), environment(dict(values)):
        for name in modules:
            try:
                module = importlib.import_module(name)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                    continue
                raise
            imported.append(module)
            for attribute in sorted(vars(module)):
                candidate = getattr(module, attribute, None)
                if isinstance(candidate, FastAPI):
                    return candidate
            for attribute in APPLICATION_FACTORY_NAMES:
                factory = getattr(module, attribute, None)
                if callable(factory) and not inspect.isclass(factory):
                    built = factory()
                    if isinstance(built, FastAPI):
                        return built

    pytest.fail(nothing_found.format(imported=[m.__name__ for m in imported] or "nothing"))


def import_mock_lms_application(values: Mapping[str, str]) -> Any:
    """The mock platform's ASGI application. See `import_mock_application` above."""
    return import_mock_application(
        MOCK_LMS_DIR,
        MOCK_LMS_MODULES,
        values,
        absent_directory=(
            f"{MOCK_LMS_DIR} does not exist. E0-14's scope is a `mock-lms/` FastAPI application "
            "with a Dockerfile, added to Compose as `mock-lms` (SPEC §13 puts it at "
            "`mock-lms/app/`, and §9.2 says what it is for)."
        ),
        nothing_found=(
            "Nothing under `mock-lms/app/` exposes a FastAPI application. Looked for a "
            f"module-level instance, then a factory named one of {list(APPLICATION_FACTORY_NAMES)}"
            f", in {list(MOCK_LMS_MODULES)}; imported {{imported}}. E0-14's scope is a "
            "`mock-lms/` FastAPI application; if it is reachable under a spelling none of those "
            "covers, that is a defect in `MockPlatform` in tests/fixtures/lti_services.py rather "
            "than in the mock, and MOCK_LMS_MODULES in tests/fixtures/lti_platform.py is the one "
            "line that changes."
        ),
    )
