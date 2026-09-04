"""E3-04 — the AGS client, reached without naming its entry points, and the gradebook it works on.

Four things live here, and each is here rather than in a test module because more
than one module will need it once E3-05 and E3-06 arrive.

**`AgsClient` reaches E3-04's module without naming its callables.** The ticket and
its work order name the module — `backend/app/lti/ags.py` (settled decision 1) — and
they name a constant, a label and a maximum. They do **not** name the function that
finds or creates the line item, nor the one that posts a score, so those two are
**discovered** by the roles their parameters play, exactly as
`fixtures/roster_sync.py::RosterSyncService` discovers E1-11's two entry points and
for the same reason: naming one here would make the implementer build to this
fixture instead of to the ticket. Every failure below either names a deliverable the
ticket asks for and that is not there, or names an interface question the ticket
leaves open, and says which.

**The module is imported inside the test body, never in a fixture.** `ags_module()`
is a plain function and every method here calls it, so an absent `app.lti.ags` is a
**failed test** naming the deliverable rather than an error in setup — the
distinction `docs/MISTAKES.md` entry 44 is about, and the one that decides whether an
unbuilt tree reads as red or as broken. An `ImportError` from *inside* a module that
exists is re-raised untouched: a client that was never written and one that imports
something absent are different failures with different fixes, and reading one as the
other sends the next person to the wrong file. This is the shape
`tests/fixtures/grading.py` uses for E3-03.

**`GradebookSection` is a registered platform, a section carrying the AGS container
address, and the wire between them.** It is `fixtures/roster_sync.py`'s
`roster_platforms` with the two gradebook columns E3-02 added written onto the
section afterwards — reused rather than rebuilt, because everything a conformant
service call needs is already assembled there: the platform verifies the tool's
`client_assertion` against the key set the tool publishes, the tool publishes it out
of the `tool_signing_key` row, and the sync's `ServiceWire` is the transport both
travel over. What this adds is the AGS address, which is the one thing that file has
no reason to know about.

**The platform profile (§7.3) is discovered the same way the callables are.** The
work order settles what the seam *is* — `activity_progress`, `grading_progress`, a
page limit, resolved by registration issuer through a small registry with the
conformant default for an unknown issuer — and settles neither the registry's name
nor the profile type's. So the resolver is found by what it answers, and a
substituted profile is built from the real default rather than from a stand-in class
of this file's own, because a client that narrows on the profile's type would refuse
a duck (`docs/MISTAKES.md`'s record of a fork whose identical class names defeated
`isinstance`).

**Nothing here computes a percentage, a ledger or a timestamp.** Every one of those
is a *value the caller hands the client*, which is the whole subject of criterion 3:
the string that arrives at the platform is the string the caller supplied. A fixture
that derived any of them would be a second implementation for the tests to agree
with (`docs/MISTAKES.md` entry 19), and the comparison criterion 3 asks for would be
between two things this file made up.
"""

import dataclasses
import importlib
import inspect
from collections.abc import Callable, Iterator, Mapping, Sequence
from types import ModuleType
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.supervision import require_table, single_primary_key

# ---------------------------------------------------------------------------
# The module contract E3-04's work order settles, spelled once.
# ---------------------------------------------------------------------------

# Settled decision 1: "The client lives at `backend/app/lti/ags.py`. SPEC §13 names
# that home and `backend/app/lti/__init__.py`'s docstring already promises it.
# Platform profiles live at `backend/app/lti/platforms/` (`base.py`, `mock.py`,
# `__init__.py`), also per §13." The package root is `backend/`, so the import paths
# are `app.lti.…`.
AGS_MODULE = "app.lti.ags"
PLATFORMS_PACKAGE = "app.lti.platforms"
PLATFORM_BASE_MODULE = f"{PLATFORMS_PACKAGE}.base"
PLATFORM_MOCK_MODULE = f"{PLATFORMS_PACKAGE}.mock"

# Settled decision 7 and the work order's identifiers section, verbatim: match by id,
# then by `resourceId`, never by label; `PULSE_RESOURCE_ID = "pulse-participation"`,
# label `"Pulse Participation"`, `scoreMaximum` 100.
PULSE_RESOURCE_ID = "pulse-participation"
PULSE_LABEL = "Pulse Participation"
PULSE_SCORE_MAXIMUM = 100

# The AGS member the resource id is carried in and the two others a created line item
# is asserted against. AGS 2.0's own camel-case spelling, which is also what the mock
# stores and serves.
RESOURCE_ID_MEMBER = "resourceId"
LABEL_MEMBER = "label"
SCORE_MAXIMUM_MEMBER = "scoreMaximum"
LINE_ITEM_ID_MEMBER = "id"

# The four members a score body carries that these tests read back. AGS 2.0's, and
# `comment` is the one SPEC §3.4 puts the per-week ledger in.
SCORE_USER_MEMBER = "userId"
SCORE_GIVEN_MEMBER = "scoreGiven"
SCORE_MAXIMUM_SENT_MEMBER = "scoreMaximum"
SCORE_COMMENT_MEMBER = "comment"
SCORE_TIMESTAMP_MEMBER = "timestamp"
ACTIVITY_PROGRESS_MEMBER = "activityProgress"
GRADING_PROGRESS_MEMBER = "gradingProgress"

# The two attributes settled decision 9 names on the profile, and the conformant
# values it fixes: "the conformant defaults the client consults on every score post
# (`activity_progress` = "Completed", `grading_progress` = "FullyGraded")".
ACTIVITY_PROGRESS_ATTRIBUTE = "activity_progress"
GRADING_PROGRESS_ATTRIBUTE = "grading_progress"
CONFORMANT_ACTIVITY_PROGRESS = "Completed"
CONFORMANT_GRADING_PROGRESS = "FullyGraded"

# The two values a substituted profile carries. **This suite's choice**, and the only
# requirement on them is that each is inside AGS 2.0's own vocabulary — a value
# outside it is refused by the mock (`one_of`), so the seam test would go red on the
# platform's validation rather than on the profile never being read. Different from
# the conformant pair in both members, because a substitution that differed in one
# would leave the other's default indistinguishable from a hardcoded string.
SUBSTITUTED_ACTIVITY_PROGRESS = "Submitted"
SUBSTITUTED_GRADING_PROGRESS = "PendingManual"

# E3-02's two gradebook columns on `section`, spelled by that ticket's work order and
# already pinned in `tests/unit/test_registration_address_constraints.py`.
# `lms_ags_line_items_url` is the AGS line-item container a launch advertises,
# `lms_`-marked because the platform supplies it; `ags_line_item_url` is the id of the
# line item this tool creates in that container, which is Pulse's own.
SECTION_CONTAINER_COLUMN = "lms_ags_line_items_url"
SECTION_LINE_ITEM_COLUMN = "ags_line_item_url"

# E3-02's call log, at SPEC §6.1's grain of one HTTP call. The required members are
# `tests/integration/test_the_passback_tables_record_one_post_per_row.py`'s
# `AGS_CALL_REQUIRED`, transcribed rather than imported for the reason that module
# gives about not importing an expectation out of what it measures.
AGS_CALL_TABLE = "ags_call"
AGS_CALL_URL_COLUMN = "url"
AGS_CALL_RESPONSE_CODE_COLUMN = "response_code"
AGS_CALL_CALLED_AT_COLUMN = "called_at"

# The four AGS scopes, as the specifications spell them. The client asks for exactly
# the one its call needs (settled decision 4), never a union, so these are what a
# test reads off a grant to say which call it was for.
LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
LINE_ITEM_READONLY_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
RESULT_READONLY_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

# The media type an AGS line-item container is served under, for the one container
# this suite composes itself.
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"

# ---------------------------------------------------------------------------
# What a value this suite can supply is *for*, matched against a parameter's name.
# The same device `fixtures/roster_sync.py::SYNC_ROLES` uses, and the same rule:
# longest alias wins, so `requests_session` is the transport and `session` is the
# database session — the one collision that would otherwise hand the client a
# `requests.Session` to write rows through.
#
# **Six of these roles are E3-04's own and none of them is named by the ticket.** The
# client is handed a section, a user, a canonical score string, a ledger string and a
# timestamp; what those parameters are *called* is the implementer's, and this table
# is the one place that changes when the pull request says which. A parameter no role
# here matches stops the test with a message saying so rather than being filled with
# a guess.
# ---------------------------------------------------------------------------

AGS_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db", "db_session"),
    "section_id": ("section_id", "section"),
    "http": ("http", "requests_session", "requests", "http_session", "transport", "client"),
    "settings": ("settings", "config", "configuration"),
    "resolve": ("resolve", "resolver", "resolve_host", "resolve_addresses"),
    "profile": ("profile", "platform_profile"),
    "line_item": ("line_item", "lineitem", "line_item_url", "line_item_id"),
    "user_id": ("user_id", "lms_user_id", "sub", "subject"),
    "score": ("score", "score_given", "percentage", "value"),
    "ledger": ("ledger", "comment", "ledger_lines"),
    "timestamp": ("timestamp", "posted_at", "stamped_at", "at"),
}

# The roles that identify the score poster rather than the line-item resolver. A
# callable taking any of these is posting a grade; the find-or-create takes none of
# them, because it has no grade to carry.
SCORE_ROLES = ("score", "ledger", "user_id")


def ags_module() -> ModuleType:
    """`app.lti.ags`, imported where a test can fail on it rather than error.

    Called from a test body, never from a fixture, so that on a tree where E3-04 is
    unbuilt every module using this goes red on its own criterion with this sentence
    attached instead of erroring in setup on somebody's missing import
    (`docs/MISTAKES.md` entry 44).

    An import error *inside* a module that exists is re-raised rather than reported
    as an absent deliverable: those are different failures and reading one as the
    other sends the next person to the wrong file.
    """
    return _module_or_named_absence(
        AGS_MODULE,
        "E3-04 ships the AGS client there (SPEC §13, and `backend/app/lti/__init__.py`'s "
        "docstring already promises it): a connector on the roster sync's shape, a "
        "client-credentials token per scope, the registration resolved from the section's own "
        "deployment, line-item find-or-create for "
        f"{PULSE_LABEL!r} by `{RESOURCE_ID_MEMBER}` {PULSE_RESOURCE_ID!r}, and a score post "
        "carrying the caller's own score string and ledger string byte-for-byte.",
    )


def platforms_module() -> ModuleType:
    """`app.lti.platforms`, imported the same way and for the same reason."""
    return _module_or_named_absence(
        PLATFORMS_PACKAGE,
        "E3-04 ships the `PlatformProfile` seam there (SPEC §7.3, SPEC §13): "
        f"`{PLATFORM_BASE_MODULE}` defines the profile and the conformant defaults the client "
        f"consults on every score post, and `{PLATFORM_MOCK_MODULE}` is the one written profile — "
        "the mock's, deviating in nothing, which is the point. Resolution is by registration "
        "issuer, with the conformant default for an issuer nothing is written for.",
    )


def _module_or_named_absence(name: str, why: str) -> ModuleType:
    """Import `name`, or fail naming the deliverable and what it owes."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == name or name.startswith(f"{absent}.")):
            raise
        pytest.fail(f"`{name}` does not exist. {why}")


class AgsClient:
    """E3-04's client, found rather than named. See the module docstring.

    A fixture that tried call shapes until one stopped raising would swallow a
    `TypeError` raised *inside* the client and report a design nobody chose as
    working, which is `docs/MISTAKES.md` entry 3. So every lookup here either answers
    or fails with a message naming what it could not find and which record left it
    open.
    """

    @property
    def module(self) -> ModuleType:
        return ags_module()

    def defined_callables(self) -> dict[str, Any]:
        """Every public callable the client's module defines itself.

        Defines *itself*: a function imported from somewhere else is not part of this
        module's surface, and counting one would let an imported helper answer for
        the ticket's deliverable.
        """
        module = self.module
        return {
            name: value
            for name, value in vars(module).items()
            if not name.startswith("_")
            and inspect.isfunction(value)
            and getattr(value, "__module__", None) == AGS_MODULE
        }

    def parameters_of(self, function: Any) -> list[Any]:
        return [
            parameter
            for parameter in inspect.signature(function).parameters.values()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]

    def roles_of(self, function: Any) -> set[str]:
        found = {self.role_of(parameter.name) for parameter in self.parameters_of(function)}
        return {role for role in found if role is not None}

    @property
    def find_or_create_line_item(self) -> Any:
        """The callable that answers the section's "Pulse Participation" line item.

        Found by what it *takes* rather than by what it is called: it names a section
        and carries no grade. Ambiguity stops rather than picks, the contract every
        discovery fixture in this suite keeps — two candidates mean this cannot tell
        which one the ticket is about, and choosing would be the test deciding.
        """
        return self._one(
            lambda roles: "section_id" in roles and not (set(SCORE_ROLES) & roles),
            "answers the section's line item, creating it where the container holds none",
            ("line", "item"),
        )

    @property
    def post_score(self) -> Any:
        """The callable that posts one student's score to that line item."""
        return self._one(
            lambda roles: bool(set(SCORE_ROLES) & roles),
            "posts one score, carrying the caller's own score string and ledger string",
            ("post", "score"),
        )

    def _one(
        self,
        wanted: Callable[[set[str]], bool],
        purpose: str,
        narrowing: tuple[str, ...],
    ) -> Any:
        defined = self.defined_callables()
        candidates = {
            name: value for name, value in defined.items() if wanted(self.roles_of(value))
        }
        if len(candidates) > 1:
            narrowed = {
                name: value
                for name, value in candidates.items()
                if all(word in name.lower() for word in narrowing)
            }
            candidates = narrowed or candidates
        if len(candidates) > 1:
            pytest.fail(
                f"`{AGS_MODULE}` defines more than one public callable that {purpose} "
                f"({sorted(candidates)}), so this cannot tell which one the ticket is about. "
                "E3-04's work order names the module and leaves both entry points open, so "
                "pinning one here would settle an interface the ticket does not — say in the "
                "pull request which it is, and `AGS_ROLES` and `AgsClient` in "
                "tests/fixtures/ags_client.py are the one place that changes."
            )
        if not candidates:
            pytest.fail(
                f"`{AGS_MODULE}` defines no public callable that {purpose} — it defines "
                f"{sorted(defined)}, whose parameter roles are "
                f"{ {name: sorted(self.roles_of(value)) for name, value in defined.items()} }.\n\n"
                "The roles this suite can fill are "
                f"{sorted(AGS_ROLES)}, matched against parameter names by the aliases in "
                "`AGS_ROLES` (tests/fixtures/ags_client.py). If the entry point is there under a "
                "shape this cannot see, that is a defect in this fixture and `AGS_ROLES` is the "
                "line that changes, once the pull request says what the parameter is called."
            )
        return next(iter(candidates.values()))

    @staticmethod
    def role_of(parameter_name: str) -> str | None:
        """Which of `AGS_ROLES` a parameter called `parameter_name` wants.

        Longest alias wins, which is the rule `SYNC_ROLES` keeps and for the reason
        it records: `requests_session` and `session` are two roles and one of them
        would otherwise be handed the other's value.
        """
        best: tuple[int, str] | None = None
        for role, aliases in AGS_ROLES.items():
            for alias in aliases:
                if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                    best is None or len(alias) > best[0]
                ):
                    best = (len(alias), role)
        return None if best is None else best[1]

    def call(self, function: Any, **available: Any) -> Any:
        """Call `function`, filling each parameter from the roles offered.

        A required parameter no offered role matches stops the test with a message
        naming it. That is either a defect in this fixture or an interface question
        for the ticket, and either way it is something to see rather than route
        around.
        """
        positional: list[Any] = []
        keyword: dict[str, Any] = {}
        for parameter in self.parameters_of(function):
            role = self.role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(function, '__qualname__', function)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}.\n\n"
                    "If the missing role is the outbound HTTP transport, that is the seam this "
                    "whole suite rests on and it is the library's own: `ServiceConnector"
                    "(registration, requests_session=…)` takes a `requests.Session`, and neither "
                    "the mock platform's address nor the tool's resolves over a network in this "
                    "process — so a client that builds its own session internally cannot be driven "
                    "against the mock at all, by this suite or by any other. Otherwise add the "
                    "role to `AGS_ROLES` in tests/fixtures/ags_client.py once the pull request "
                    "says what it is for."
                )
                continue
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]
        return function(*positional, **keyword)

    # -- the platform profile seam (§7.3, settled decision 9) -----------------

    def profile_resolver(self) -> tuple[ModuleType, str, Any]:
        """The registry entry point, its name, and the module it was found on.

        The work order settles what the seam does — resolved "by registration issuer
        through a small registry, unknown issuer → the conformant default" — and
        settles neither its name nor the profile type's. So it is found by what it
        *answers*: the one public callable on `app.lti.platforms` that takes a single
        required argument and hands back something carrying both progress attributes.

        Answering with the module as well as the name is what lets a test substitute
        the profile without knowing how the client imported it — see
        `substituting_the_profile` below.
        """
        module = platforms_module()
        candidates: dict[str, Any] = {}
        for name, value in vars(module).items():
            if name.startswith("_") or not callable(value):
                continue
            try:
                required = [
                    parameter
                    for parameter in inspect.signature(value).parameters.values()
                    if parameter.default is parameter.empty
                    and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
                ]
            except (TypeError, ValueError):  # pragma: no cover - not a resolver
                continue
            if len(required) == 1:
                candidates[name] = value
        if len(candidates) != 1:
            pytest.fail(
                f"`{PLATFORMS_PACKAGE}` exposes {sorted(candidates)} as callables taking exactly "
                "one required argument, and this needs exactly one: the registry that resolves a "
                "profile from a registration issuer (E3-04's settled decision 9 — 'Resolution: by "
                "registration issuer through a small registry, unknown issuer → the conformant "
                f"default'). The package exposes {sorted(n for n in vars(module) if not n.startswith('_'))}. "
                "The ticket leaves the name open, so say in the pull request which it is and "
                "`AgsClient.profile_resolver` in tests/fixtures/ags_client.py is the one place "
                "that changes."
            )
        name, resolver = next(iter(candidates.items()))
        return module, name, resolver

    def profile_for(self, issuer: str) -> Any:
        """The profile the client would use for `issuer`, through the registry itself."""
        _module, name, resolver = self.profile_resolver()
        profile = resolver(issuer)
        for attribute in (ACTIVITY_PROGRESS_ATTRIBUTE, GRADING_PROGRESS_ATTRIBUTE):
            assert hasattr(profile, attribute), (
                f"`{PLATFORMS_PACKAGE}.{name}({issuer!r})` answered {profile!r}, which carries no "
                f"`{attribute}`. Settled decision 9 makes the profile the thing the client "
                "consults on every score post, and those two attributes are what it consults it "
                "for — a profile without them is a file the code cannot read anything out of."
            )
        return profile

    def substituted_profile(self, issuer: str) -> Any:
        """The same profile with both progress values changed, and nothing else.

        Built from the real one rather than from a stand-in class of this file's own,
        for two reasons. A client that narrows on the profile's type would refuse a
        duck, and the test would then report a seam that *is* consulted as one that
        is not. And a profile carrying only two attributes would break a client that
        reads a third — the page limit settled decision 9 also puts there — which is
        a failure about this fixture wearing the shape of a failure about the client.
        """
        profile = self.profile_for(issuer)
        changes = {
            ACTIVITY_PROGRESS_ATTRIBUTE: SUBSTITUTED_ACTIVITY_PROGRESS,
            GRADING_PROGRESS_ATTRIBUTE: SUBSTITUTED_GRADING_PROGRESS,
        }
        if dataclasses.is_dataclass(profile) and not isinstance(profile, type):
            return dataclasses.replace(profile, **changes)
        copied = {
            name: getattr(profile, name)
            for name in dir(profile)
            if not name.startswith("_") and not callable(getattr(profile, name, None))
        }
        copied.update(changes)
        return type("SubstitutedProfile", (), copied)()


@pytest.fixture
def ags_client() -> AgsClient:
    """E3-04's client, reached by discovery. See `AgsClient` above."""
    return AgsClient()


# ---------------------------------------------------------------------------
# The gradebook a client works on: a section carrying the container address.
# ---------------------------------------------------------------------------


class AgsSection(NamedTuple):
    """One registered platform, its section, and the two gradebook addresses on it.

    `advertised` is the container URL the platform's own AGS claim carries, kept
    beside `container` — which is whatever the section actually holds — so that a
    test posing a refusal on a hostile stored address can put the real one back and
    assert the accepted half on the same platform.
    """

    synced: Any
    container: str | None
    advertised: str
    line_item_url: str | None
    context: Any

    @property
    def id(self) -> Any:
        return self.synced.id

    @property
    def platform(self) -> Any:
        return self.synced.platform

    @property
    def host(self) -> str | None:
        """The **platform's** host, never the stored container's.

        Deliberately not read off `container`: a test that stores a loopback address
        on the section is asking whether the client dials it, and a driver that
        mounted the stored host on the wire would answer that request with the mock
        platform — turning "refused before it was dialled" into a test that could not
        fail (`docs/MISTAKES.md` entry 3).
        """
        return self.synced.host

    @property
    def subjects(self) -> list[str]:
        """Every `sub` this platform will sign a launch for in this context, sorted.

        Learned by driving launches rather than by reading a roster, which is what
        makes it independent ground truth: a score posted for one of these is a score
        for a student the platform demonstrably knows.
        """
        return sorted(self.context.subjects)


def rewrite_section(rows: Any, tables: Mapping[str, Any], section_id: Any, **values: Any) -> None:
    """Set columns on one committed `section` row, and commit.

    The same shape `fixtures/doors.py::PlatformRegistration.rewrite` uses. It runs on
    `committed_rows`' own connection, which is bound to the migrating engine rather
    than to `pulse_app` — E3-05 is the ticket that spends the application role's
    `UPDATE` grant on `ags_line_item_url`, and a fixture that needed that grant now
    would be asserting E3-05's work from inside E3-04's setup.
    """
    table = require_table(dict(tables), "section")
    missing = [name for name in values if name not in table.c]
    if missing:
        pytest.fail(
            f"`section` declares no {missing} (it declares "
            f"{[column.name for column in table.columns]}). E3-02 adds "
            f"`{SECTION_CONTAINER_COLUMN}` — the AGS line-item container a launch advertises — and "
            f"`{SECTION_LINE_ITEM_COLUMN}`, the id of the line item this tool creates in it. "
            "Without them there is nowhere for a launch to have stored a gradebook address and "
            "nothing for this client to resolve."
        )
    key = single_primary_key(table)
    rows.session.execute(table.update().where(table.c[key] == section_id).values(**values))
    rows.commit()


@pytest.fixture
def ags_sections(
    roster_platforms: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> Iterator[Callable[..., AgsSection]]:
    """Start a platform, register it, seed a section, and store its gradebook address.

    `roster_platforms` does everything that is not about AGS — the platform, the
    registration, the tool's published key set, the section bound to its own
    deployment, and the `ServiceWire` all of it is reachable over — and this adds the
    one thing it has no reason to know: the AGS line-items container the launch
    advertises, written onto the section the way E3-02's launch-time writer writes it.

    `container` chooses what is stored there: `True` for the address the platform
    actually advertises, `False` for a section with no gradebook at all (SPEC §7.3's
    never-synced shape, one service over), and a string for an address a test wrote —
    which is how the loopback refusal is posed, because no mock platform will
    advertise one.

    `line_item` stores an id on the section, which is the first branch of settled
    decision 7's find-or-create. Left `None`, the section holds none and the client
    has to read the container.
    """
    started: list[AgsSection] = []

    def start(
        issuer: str | None = None,
        *,
        container: str | bool = True,
        line_item: str | None = None,
    ) -> AgsSection:
        synced = roster_platforms(issuer)
        contexts = synced.platform.seeded_contexts()
        assert contexts, (
            "The mock platform offers no launch, so it advertises no AGS endpoint claim and there "
            "is no line-items container to store on a section. E0-14 seeds the launches and E0-15 "
            "the gradebook behind them."
        )
        matching = [found for found in contexts if found.context_id == synced.context_id]
        assert matching, (
            f"No seeded context matches the section's own {synced.context_id!r} (the platform "
            f"seeds {[found.context_id for found in contexts]}), so the AGS claim this reads the "
            "container out of would belong to a different section."
        )
        context = matching[0]
        advertised = synced.platform.line_items_url(context.launches[0])
        stored = advertised if container is True else container
        rewrite_section(
            committed_rows,
            metadata_tables,
            synced.id,
            **{
                SECTION_CONTAINER_COLUMN: None if stored is False else str(stored),
                SECTION_LINE_ITEM_COLUMN: line_item,
            },
        )
        section = AgsSection(
            synced=synced,
            container=None if stored is False else str(stored),
            advertised=str(advertised),
            line_item_url=line_item,
            context=context,
        )
        started.append(section)
        return section

    def store_line_item(section: AgsSection, identifier: str | None) -> AgsSection:
        """Put an id in the section's `ags_line_item_url`, committed.

        The state every section is in after its first posting run, and the first
        branch of settled decision 7's find-or-create. It is written here rather than
        by the client, because **the client persists nothing**: the application role
        holds no `UPDATE` on this column and E3-05 is the ticket that spends it.
        """
        rewrite_section(
            committed_rows,
            metadata_tables,
            section.id,
            **{SECTION_LINE_ITEM_COLUMN: identifier},
        )
        return section._replace(line_item_url=identifier)

    def repoint(section: AgsSection, container: str) -> AgsSection:
        """Store a different container address on a section that already exists.

        What it is for is the accepted half of a refusal pair, posed on the **same**
        platform and the same section. Starting a second platform to hold the good
        address would put two platforms on one host — `roster_platforms` mounts by
        host and the second would replace the first — so the two halves would be
        answered by different applications and the pair would prove nothing
        (`docs/MISTAKES.md` entry 3).
        """
        rewrite_section(
            committed_rows,
            metadata_tables,
            section.id,
            **{SECTION_CONTAINER_COLUMN: container},
        )
        return section._replace(container=container)

    start.wire = roster_platforms.wire  # type: ignore[attr-defined]
    start.repoint = repoint  # type: ignore[attr-defined]
    start.store_line_item = store_line_item  # type: ignore[attr-defined]
    yield start


@pytest.fixture
def ags_section(ags_sections: Any) -> AgsSection:
    """One registered platform and one section carrying its AGS container address."""
    return ags_sections()


class AgsRows:
    """What is in `ags_call`, read on a connection that sees commits."""

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables

    def table(self) -> Any:
        if AGS_CALL_TABLE not in self.tables:
            pytest.fail(
                f"There is no `{AGS_CALL_TABLE}` table (there are {sorted(self.tables)}). SPEC §8 "
                "names it beside `nrps_call` and §6.1 promises 'NRPS and AGS call logs with "
                "response codes'; E3-02 is the ticket that builds it, and E3-04's criterion 8 is "
                "what writes to it."
            )
        return require_table(self.tables, AGS_CALL_TABLE)

    def link(self) -> str:
        """The column on `ags_call` whose foreign key names a `section` row."""
        table = self.table()
        found = sorted(
            {key.parent.name for key in table.foreign_keys if key.column.table.name == "section"}
        )
        if len(found) != 1:
            pytest.fail(
                f"`{AGS_CALL_TABLE}` has {len(found)} foreign keys to `section` ({found}); it "
                f"references {sorted({key.column.table.name for key in table.foreign_keys})}. "
                "E3-02 gives it exactly one, and §6.1's console reads this log per section."
            )
        return found[0]

    def calls(self) -> list[dict[str, Any]]:
        """Every `ags_call` row, after ending the read transaction so commits are visible."""
        self.rows.session.rollback()
        return [dict(row) for row in self.rows.session.execute(self.table().select()).mappings()]

    def calls_for(self, section_id: Any) -> list[dict[str, Any]]:
        link = self.link()
        return [row for row in self.calls() if row.get(link) == section_id]


@pytest.fixture
def ags_rows(committed_rows: Any, metadata_tables: dict[str, Any]) -> AgsRows:
    """What the client wrote to `ags_call`, read on `committed_rows`' own connection."""
    return AgsRows(committed_rows, metadata_tables)


# ---------------------------------------------------------------------------
# The values a caller hands the client. **None of them is derived here.**
# ---------------------------------------------------------------------------


class PostedGrade(NamedTuple):
    """One caller's score string, ledger string, user and timestamp, exactly as handed over.

    A value object rather than four arguments threaded through every test, and the
    point of it is criterion 3: what arrives at the platform is compared against
    *this*, never against a second rendering of the same numbers
    (`docs/MISTAKES.md` entry 19).
    """

    user_id: str
    score: str
    ledger: str
    timestamp: str


# An awkward percentage string and a several-line ledger. **This suite's choice, and
# each is chosen to be a string a re-derivation gets wrong.**
#
#   - `61.5` renders as `61.5`, `61.50` or `0.615` depending on who formats it, and
#     a poster that re-derived the number would produce one of the other two —
#     which ADR 0052's retry identity cannot survive, because "a value the poster
#     re-derives is not provably the value it is retrying".
#   - the ledger is more than one line, so a carriage that took the first line, or
#     joined with a comma, or re-wrapped, is visible. Its lines are SPEC §3.4's
#     format and the numbers in them are this file's, not a computation.
#   - the trailing week with `0 of 5` is the missed week §3.4 requires in the
#     denominator, so a ledger that dropped empty weeks is visible too.
A_SCORE_STRING = "61.5"
A_LEDGER = "Week 1: 4 of 5 items\nWeek 2: 5 of 5 items\nWeek 3: 0 of 5 items"

# An RFC 3339 instant with an explicit offset, spelled `+00:00` rather than `Z`. Both
# halves matter: the offset is required by the mock's own grammar, and the spelling
# is the fact — a client that round-tripped the value through a `datetime` and
# re-rendered it would send `Z` and the byte-exact comparison would catch it.
A_TIMESTAMP = "2026-03-02T14:05:09+00:00"

# A later instant, for the score a platform already holds when the 409 is planted.
A_LATER_TIMESTAMP = "2026-03-09T14:05:09+00:00"

# The value the platform holds in that case, distinct from `A_SCORE_STRING` so the
# typed error can be required to carry it and be carrying *something*.
A_NEWER_SCORE = 88.5


def a_grade(
    user_id: str,
    *,
    score: str = A_SCORE_STRING,
    ledger: str = A_LEDGER,
    timestamp: str = A_TIMESTAMP,
) -> PostedGrade:
    """One grade a caller hands the client, with the caller choosing every part."""
    return PostedGrade(user_id=user_id, score=score, ledger=ledger, timestamp=timestamp)


def a_line_item_document(
    identifier: str, *, resource_id: str = PULSE_RESOURCE_ID
) -> dict[str, Any]:
    """One AGS line item as a container serves it, for the container this suite composes."""
    return {
        LINE_ITEM_ID_MEMBER: identifier,
        LABEL_MEMBER: PULSE_LABEL,
        SCORE_MAXIMUM_MEMBER: PULSE_SCORE_MAXIMUM,
        RESOURCE_ID_MEMBER: resource_id,
    }


def a_resource_id(label: str) -> str:
    """A `resourceId` nothing else in this run uses, for a line item that is not Pulse's."""
    return f"e3-04-{label}-{uuid4().hex[:12]}"


def member_of(value: Any, member: str, subject: str) -> Any:
    """One member of a line item the client answered with, however it carries it.

    The ticket says the client "returns the line item" and does not say whether that
    is the AGS document or an object over it, so both are read. This tolerance is
    deliberate and bounded: it reads, it never decides, and every assertion that
    could be made against the *platform* instead is made there — a line item the
    client claims to have created is checked by listing the container, not by
    believing what came back.
    """
    if isinstance(value, Mapping) and member in value:
        return value[member]
    for attribute in (member, _snake(member)):
        if hasattr(value, attribute):
            return getattr(value, attribute)
    pytest.fail(
        f"{subject} answered {value!r}, which carries no `{member}` as a key or as an attribute. "
        "E3-04's find-or-create answers the line item and leaves persisting it to the caller, so "
        f"whatever it answers has to be able to say what its `{member}` is."
    )


def _snake(member: str) -> str:
    """`scoreMaximum` as `score_maximum`, so an object over the document reads too."""
    return "".join(f"_{letter.lower()}" if letter.isupper() else letter for letter in member)


def scores_posted(platform: Any, line_item_url: str) -> list[dict[str, Any]]:
    """Every score body the platform recorded against `line_item_url`, verbatim, in order.

    Read through `GET /mock/posted-scores`, which ADR 0047 makes the only surface that
    can say what the tool *sent*: a conformant `Result` carries no timestamp and no
    progress members, so the fields criterion 3 is about cannot come back through the
    protocol at all. Nothing in `backend/` may know this route exists; only a test.
    """
    return [
        dict(entry.get("score") or {})
        for entry in platform.posted_scores()
        if entry.get("lineItem") == line_item_url
    ]


@pytest.fixture
def ags_contract() -> Any:
    """The names E3-04's test modules read the client's work through.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: an import of a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class AgsContract:
        module = AGS_MODULE
        platforms_package = PLATFORMS_PACKAGE
        base_module = PLATFORM_BASE_MODULE
        mock_module = PLATFORM_MOCK_MODULE

        resource_id = PULSE_RESOURCE_ID
        label = PULSE_LABEL
        score_maximum = PULSE_SCORE_MAXIMUM

        resource_id_member = RESOURCE_ID_MEMBER
        label_member = LABEL_MEMBER
        score_maximum_member = SCORE_MAXIMUM_MEMBER
        line_item_id_member = LINE_ITEM_ID_MEMBER
        user_member = SCORE_USER_MEMBER
        given_member = SCORE_GIVEN_MEMBER
        maximum_sent_member = SCORE_MAXIMUM_SENT_MEMBER
        comment_member = SCORE_COMMENT_MEMBER
        timestamp_member = SCORE_TIMESTAMP_MEMBER
        activity_member = ACTIVITY_PROGRESS_MEMBER
        grading_member = GRADING_PROGRESS_MEMBER

        activity_attribute = ACTIVITY_PROGRESS_ATTRIBUTE
        grading_attribute = GRADING_PROGRESS_ATTRIBUTE
        conformant_activity = CONFORMANT_ACTIVITY_PROGRESS
        conformant_grading = CONFORMANT_GRADING_PROGRESS
        substituted_activity = SUBSTITUTED_ACTIVITY_PROGRESS
        substituted_grading = SUBSTITUTED_GRADING_PROGRESS

        container_column = SECTION_CONTAINER_COLUMN
        line_item_column = SECTION_LINE_ITEM_COLUMN

        call_table = AGS_CALL_TABLE
        call_url_column = AGS_CALL_URL_COLUMN
        call_response_code_column = AGS_CALL_RESPONSE_CODE_COLUMN
        call_called_at_column = AGS_CALL_CALLED_AT_COLUMN

        line_item_scope = LINE_ITEM_SCOPE
        line_item_readonly_scope = LINE_ITEM_READONLY_SCOPE
        result_readonly_scope = RESULT_READONLY_SCOPE
        score_scope = SCORE_SCOPE
        container_media_type = LINE_ITEM_CONTAINER_MEDIA_TYPE

        a_score = A_SCORE_STRING
        a_ledger = A_LEDGER
        a_timestamp = A_TIMESTAMP
        a_later_timestamp = A_LATER_TIMESTAMP
        a_newer_score = A_NEWER_SCORE

        grade = staticmethod(a_grade)
        line_item_document = staticmethod(a_line_item_document)
        resource_id_for = staticmethod(a_resource_id)
        member = staticmethod(member_of)
        scores_posted = staticmethod(scores_posted)
        logged_text = staticmethod(logged_text)

    return AgsContract()


def logged_text(records: Sequence[Any]) -> str:
    """Everything a run of the client logged, as one string, arguments included.

    `record.getMessage()` renders the format arguments in, which is where a value
    hides from a check made against `record.msg` alone — `logger.info("posted %s",
    score)` has a template with no score in it. The `args` are folded in as well for
    the shape that formats nothing, and `exc_text` because a traceback carries the
    arguments a raise was built from.
    """
    parts: list[str] = []
    for record in records:
        parts.append(str(record.getMessage()))
        parts.append(repr(getattr(record, "args", None)))
        parts.append(str(getattr(record, "exc_text", "") or ""))
    return "\n".join(parts)
