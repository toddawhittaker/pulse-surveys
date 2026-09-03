"""E1-10 — launch-time provisioning: reaching it, and the ground it writes onto.

Four things live here, and each is here rather than in a test module because two
modules need all four: `tests/integration/test_launch_time_provisioning.py` and
`tests/integration/test_launch_provisioning_defects.py`.

**`provisioning` reaches E1-10's writer without naming its function.** The ticket
and its work order name the module — `backend/app/services/provisioning.py` — and
say what it does: it is called from the launch handler after `verified_launch`
succeeds, it reads the launch's claims, and it writes `course`, `section` and
`user` through `guard_write(table=…, sanction=…)`. Neither names the callable or
its signature, so it is discovered by a fragment of its name and its parameters
are filled by role, exactly as `SectionCodeService` in `fixtures/section_codes.py`
does for E0-07 and for the same reason: naming one here would make the implementer
build to this fixture instead of to the ticket.

**E1-11 adds a third role, `settings`, and fills it by default.** That ticket's
decision D13 closes deferred E1-10 items 5 and 2 by handing the writer the
configuration the door already holds — `provision_from_launch(session, claims,
settings)` — and deleting `_environment()`'s `os.environ` read. Every existing
call site here passes a session and claims and nothing else, so the role resolves
to a `Settings` built at call time unless a test names its own; a fixture that had
made the new parameter each caller's problem would have made this ticket's change
red in E1-10's suite for a reason that is not E1-10's (`docs/MISTAKES.md` entry
22).

**`launch_ground` seeds what a launch needs to resolve against**, committed. The
tool opens its own connection out of `DATABASE_URL` and sees nothing that has not
been committed, so a prefix, a term and a start-letter map row seeded inside
`db_session` would be invisible to a launch driven through the door. Every part
of it is optional and every option has a paired opposite — a term that contains
today and a term that does not, a map row for the launch's own start letter and a
map row for some other letter — because each defect E1-10 records is the absence
of one of these and each is only worth asserting beside its present-and-working
twin.

**`launch_driver` drives a whole launch at this project's own door**, and
`registered_platform` is the same platform with no door in front of it. Almost
everything E1-10 asserts is asserted through the first: the writer runs inside the
launch request, so a test that called it directly would say nothing about whether
the handler calls it at all. The second exists for the cases no mint can produce —
a context label carrying an out-of-band course number, and a *second, different*
platform title for one context — where the claims are still a real launch's, from
a registered platform, with the one member under test rewritten. The second states
its own `ENVIRONMENT`, because building no door means nothing else in that chain
sets one; the fixture says what running under the process's leftovers cost.

**`provisioning_contract` is the vocabulary those modules read a launch through**:
claim names, column names, the defect kinds `DEFECT_KINDS` enumerates, the mint
selectors, and the
helpers that split a context label into the three parts E1-10 parses. Test modules
reach it as a fixture rather than importing this file, because an import of a
fixtures module by name depends on where pytest put `tests/` on `sys.path` and an
import error is not a red.

**The claims-rewriting helpers own one rule between them.** `with_course_number`
is the only mutation the band-edge cases make, and
`test_rewriting_a_launchs_course_number_changes_only_the_labels_middle_part` in
the defects module is its control. **If that control is red, those tests are
broken rather than the code is.**
"""

import importlib
import inspect
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from fixtures.lti_services import CONTEXT_CLAIM, NRPS_CLAIM
from fixtures.supervision import require_column, require_table, single_primary_key

# ---------------------------------------------------------------------------
# Reaching the writer.
# ---------------------------------------------------------------------------

# Spelled by E1-10's work order: "One new module:
# `backend/app/services/provisioning.py`". The package root is `backend/`, so the
# import path is `app.services....`.
PROVISIONING_MODULE = "app.services.provisioning"

# What a value this suite can supply is *for*, matched against a parameter's name.
# The ticket says the writer is called "after `verified_launch` succeeds" with the
# claims that call returns, and says nothing about the signature — so the tests
# offer what they have and let the signature take what it wants. Longest alias
# first, so `launch_claims` is claims rather than a launch.
PROVISIONING_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db"),
    "claims": ("claims", "launch", "payload", "token_claims", "id_token_claims"),
    # E1-11's decision D13, closing deferred E1-10 items 5 and 2:
    # `provision_from_launch(session, claims)` becomes
    # `provision_from_launch(session, claims, settings)`, the door passes
    # `request.app.state.settings`, and `_environment()` and its `os.environ` read
    # are deleted. The role is filled by `ProvisioningService.settings` below
    # unless a test supplies its own, so E1-10's existing call sites keep working
    # unchanged — `docs/MISTAKES.md` entry 22 is what that avoids: a later
    # ticket's legitimate change making an earlier ticket's tests unrunnable, with
    # the repair on the far side of the test wall.
    "settings": ("settings", "config", "configuration"),
}


class ProvisioningService:
    """E1-10's writer, found rather than named. See the module docstring.

    Every failure below either names a deliverable the ticket asks for and that is
    not there, or names an interface question the ticket leaves open. Neither is
    guessed at quietly: a fixture that tried call shapes until one stopped raising
    would swallow a `TypeError` raised *inside* the writer and report a design
    nobody chose as working, which is `docs/MISTAKES.md` entry 3.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    @property
    def module(self) -> ModuleType:
        """`app.services.provisioning`, or a failure naming the missing file.

        A `ModuleNotFoundError` for some *other* module is re-raised untouched: a
        writer that exists and imports something absent and a writer that was
        never written need different fixes, and a test must not report them as the
        same thing. `import_app_module` and `SectionCodeService` both draw the same
        line for the same reason.
        """
        if self._module is None:
            try:
                self._module = importlib.import_module(PROVISIONING_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == PROVISIONING_MODULE or PROVISIONING_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{PROVISIONING_MODULE}` module. E1-10 puts launch-time "
                    "provisioning in `backend/app/services/provisioning.py` — the module that "
                    "parses the context claim, validates it, writes `course`, `section` and "
                    "`user` through `guard_write`, and records a defect when it refuses. SPEC "
                    "§13 gives `services/` that job."
                )
        return self._module

    def defined_callables(self) -> dict[str, Any]:
        """Every public callable the writer's module defines itself.

        Defines *itself*: a function imported from somewhere else is not part of
        this module's surface, and counting one would let an imported helper
        answer for the ticket's deliverable.
        """
        found: dict[str, Any] = {}
        for name, value in vars(self.module).items():
            if name.startswith("_"):
                continue
            if getattr(value, "__module__", None) != PROVISIONING_MODULE:
                continue
            if inspect.isfunction(value):
                found[name] = value
        return found

    @property
    def provision(self) -> Any:
        """The callable the launch handler calls once a launch has verified.

        Looked for by name fragment, ambiguity stopping rather than picking — the
        same contract `SectionCodeService.callable_named_after` keeps, because two
        candidates mean this cannot tell which one the ticket is about and
        choosing would be the test deciding.
        """
        defined = self.defined_callables()
        for fragment in ("provision", "ingest", "from_launch"):
            matches = {name: value for name, value in defined.items() if fragment in name.lower()}
            if len(matches) > 1:
                pytest.fail(
                    f"`{PROVISIONING_MODULE}` defines more than one public callable whose name "
                    f"carries {fragment!r} ({sorted(matches)}), so this cannot tell which one the "
                    "launch handler calls. Naming one here would pin an interface E1-10 leaves "
                    "open — say in the pull request which it is, and `ProvisioningService` in "
                    "tests/fixtures/provisioning.py is the one place that changes."
                )
            if matches:
                return next(iter(matches.values()))
        pytest.fail(
            f"`{PROVISIONING_MODULE}` defines no public callable whose name carries any of "
            f"{['provision', 'ingest', 'from_launch']} — it defines {sorted(defined)}. E1-10's "
            "work order: the module is 'called from the launch handler after `verified_launch` "
            "succeeds, before the landing response'. If the entry point is there under a name "
            "none of these fragments reaches, that is a defect in this fixture rather than in the "
            "writer, and this list is the one line that changes."
        )

    @property
    def settings(self) -> Any:
        """A `Settings` built from the environment **as of the call**, not of setup.

        Lazy on purpose. `registered_platform` sets `ENVIRONMENT` with a bare
        `setenv` after this fixture is constructed, and several tests set it
        themselves inside their own bodies, so a `Settings` built when the fixture
        was created would carry whatever the process happened to hold first — which
        is the class of failure `docs/MISTAKES.md` entry 40 records, arriving
        through the fixture that was supposed to close it.

        A test that wants a *particular* configuration passes `settings=` to
        `call` and this is never reached.
        """
        from app.config import Settings

        return Settings()

    @staticmethod
    def role_of(parameter_name: str) -> str | None:
        """Which of `PROVISIONING_ROLES` a parameter called `parameter_name` wants."""
        best: tuple[int, str] | None = None
        for role, aliases in PROVISIONING_ROLES.items():
            for alias in aliases:
                if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                    best is None or len(alias) > best[0]
                ):
                    best = (len(alias), role)
        return None if best is None else best[1]

    def call(self, function: Any, **available: Any) -> Any:
        """Call `function`, filling each parameter from the roles offered.

        A parameter no offered role matches, and that has no default, stops the
        test with a message naming it. That is either a defect in this fixture or
        an interface question for the ticket, and either way it is something to
        see rather than route around.
        """
        signature = inspect.signature(function)
        parameters = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        positional: list[Any] = []
        keyword: dict[str, Any] = {}
        offered = dict(available)
        for parameter in parameters:
            role = self.role_of(parameter.name)
            if role == "settings" and role not in offered:
                offered[role] = self.settings
            if role is None or role not in offered:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(function, '__qualname__', function)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}. E1-10 says the writer runs on the claims "
                    "`verified_launch` returns and spells no signature, so a required parameter "
                    "outside that is an interface question for the ticket — add the role to "
                    "`PROVISIONING_ROLES` in tests/fixtures/provisioning.py once the pull request "
                    "says what it is for."
                )
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(offered[role])
            else:
                keyword[parameter.name] = offered[role]
        return function(*positional, **keyword)


@pytest.fixture
def provisioning(configured_env: dict[str, str]) -> ProvisioningService:
    """E1-10's writer, reached by discovery. See `ProvisioningService` above.

    Depends on `configured_env` so the documented variables are laid down before
    `ProvisioningService.settings` builds a `Settings()`: E1-11 gave
    `provision_from_launch` a `settings` parameter, so the `settings` role is now
    reached where E1-10 never reached it, and a bare process environment — CI's,
    with no `.env` — fails the whole configuration. `registered_platform`'s
    `ENVIRONMENT` setenv rides on top of this (`docs/MISTAKES.md` entry 40).
    """
    return ProvisioningService()


# ---------------------------------------------------------------------------
# Reading a launch's context claim.
# ---------------------------------------------------------------------------

# The LTI 1.3 claims this fixture reads that `fixtures/lti_services.py` does not
# already spell. Transcriptions of the published constants, as every module in
# this suite spells them.
LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
ROLES_CLAIM = LTI_CLAIM + "roles"
DEPLOYMENT_ID_CLAIM = LTI_CLAIM + "deployment_id"

# The context label's shape, from E1-10's work order: "exactly `PREFIX-NUMBER-CODE`
# on hyphens (mock emits 'BIOL-215-R3WW')". Three parts, and the separator is not
# this suite's choice — it is what the platform sends.
LABEL_SEPARATOR = "-"
LABEL_PARTS = 3

# Where the NRPS claim carries the address SPEC §7.3 has a staff launch store.
# The member name is the NRPS 2.0 specification's, not this suite's.
MEMBERSHIPS_URL_MEMBER = "context_memberships_url"


class ContextLabel:
    """One context label's three parts, with the label itself kept beside them."""

    def __init__(self, label: str, prefix: str, number: str, code: str) -> None:
        self.label = label
        self.prefix = prefix
        self.number = number
        self.code = code

    @property
    def start_letter(self) -> str:
        """The section code's start position — §2.2's `{startLetter}{ordinal}{modality}`."""
        return self.code[:1]

    def __repr__(self) -> str:
        return f"ContextLabel({self.label!r})"


def parse_context_label(label: Any) -> ContextLabel:
    """A context label split the way E1-10 splits it, or a failure saying it cannot be.

    Used to build the fixture data a launch has to resolve against — a `prefix`
    row carrying the label's prefix, a start-letter map row carrying its code's
    start position — so this suite never transcribes `BIOL` or `R3WW`: it reads
    them off the launch the platform actually signed. A mock that changes its seed
    changes these tests' fixture data with it, rather than leaving them asserting
    against a course nobody launched.
    """
    if not isinstance(label, str) or label.count(LABEL_SEPARATOR) != LABEL_PARTS - 1:
        pytest.fail(
            f"The launch's context label is {label!r}, which is not the "
            f"`PREFIX{LABEL_SEPARATOR}NUMBER{LABEL_SEPARATOR}CODE` shape E1-10 parses. Every "
            "fixture row these tests seed — the prefix, the term's start-letter map entry — is "
            "built from those three parts, so a label of another shape leaves this suite unable "
            "to seed what the launch needs rather than able to assert anything about it."
        )
    prefix, number, code = label.split(LABEL_SEPARATOR)
    return ContextLabel(label, prefix, number, code)


def context_of(claims: Mapping[str, Any]) -> dict[str, Any]:
    """The launch's context claim, or a failure saying it carries none."""
    context = claims.get(CONTEXT_CLAIM)
    if not isinstance(context, dict):
        pytest.fail(
            f"The launch carries `{CONTEXT_CLAIM}` as {context!r} rather than an object. LTI 1.3 "
            "makes the context claim an object whose `id` is required, and E1-10 reads the course "
            "and the section out of it."
        )
    return dict(context)


def memberships_url_in(claims: Mapping[str, Any]) -> str:
    """The roster service address the launch advertises, or a failure naming its absence.

    SPEC §7.3: "The roster service address arrives as a claim on that launch and
    is **stored**, which is what gives the scheduled job the discovery it
    otherwise lacks." A test that asserted an address was *not* stored without
    first knowing there was one to store would be asserting nothing.
    """
    service = claims.get(NRPS_CLAIM)
    address = service.get(MEMBERSHIPS_URL_MEMBER) if isinstance(service, dict) else None
    if not isinstance(address, str) or not address:
        pytest.fail(
            f"The launch carries no `{MEMBERSHIPS_URL_MEMBER}` under `{NRPS_CLAIM}` (it carries "
            f"{service!r}). SPEC §7.3 has the roster service address arrive as a claim on a staff "
            "launch and be stored, so without one there is nothing for E1-10 to store and nothing "
            "for these tests to assert about."
        )
    return address


def relabelled(claims: Mapping[str, Any], label: str) -> dict[str, Any]:
    """`claims` with the context claim's `label` replaced and nothing else touched.

    The one mutation the band-edge tests make. It is written as a copy rather than
    an in-place edit so that a caller holding the original still holds the
    original — two parametrised cases sharing one template would otherwise see
    each other's number.
    """
    changed = dict(claims)
    context = context_of(claims)
    context["label"] = label
    changed[CONTEXT_CLAIM] = context
    return changed


def with_course_number(claims: Mapping[str, Any], number: str) -> dict[str, Any]:
    """`claims` with the context label's middle part replaced by `number`."""
    parsed = parse_context_label(context_of(claims).get("label"))
    return relabelled(claims, LABEL_SEPARATOR.join((parsed.prefix, number, parsed.code)))


def with_section_code(claims: Mapping[str, Any], code: str) -> dict[str, Any]:
    """`claims` with the context label's last part replaced by `code`.

    A platform that renames a context keeps the context's `id` and changes what it
    is called, which is the case the round-3 ruling turns into a recorded
    `context_collision` rather than a silent second section.
    """
    parsed = parse_context_label(context_of(claims).get("label"))
    return relabelled(claims, LABEL_SEPARATOR.join((parsed.prefix, parsed.number, code)))


def with_context_id(claims: Mapping[str, Any], context_id: str) -> dict[str, Any]:
    """`claims` with the context claim's `id` replaced and its label left alone.

    The one mutation the collision tests make, and the shape of the finding they
    are about: a Canvas course copy carries the source course's section code in a
    brand-new context. Everything a launch parses stays identical and the only
    thing that differs is the identity the platform gave the context.
    """
    changed = dict(claims)
    context = context_of(claims)
    context["id"] = context_id
    changed[CONTEXT_CLAIM] = context
    return changed


def with_context_title(claims: Mapping[str, Any], title: str) -> dict[str, Any]:
    """`claims` with the context claim's `title` replaced.

    Carried alongside a changed address in the collision tests, because the
    finding is that a colliding launch rewrites *both* — the stored roster address
    and the LMS's own course title — and a test that changed only one could not
    say the other was left alone.
    """
    changed = dict(claims)
    context = context_of(claims)
    context["title"] = title
    changed[CONTEXT_CLAIM] = context
    return changed


def with_memberships_url(claims: Mapping[str, Any], address: str) -> dict[str, Any]:
    """`claims` with the NRPS claim's roster address replaced and nothing else touched.

    The mutation the address tests make. The service claim is copied rather than
    edited in place for the same reason `relabelled` copies the context claim: two
    parametrised cases sharing one launch would otherwise see each other's URL.
    """
    changed = dict(claims)
    service = claims.get(NRPS_CLAIM)
    replaced = dict(service) if isinstance(service, dict) else {}
    replaced[MEMBERSHIPS_URL_MEMBER] = address
    changed[NRPS_CLAIM] = replaced
    return changed


# ---------------------------------------------------------------------------
# The vocabulary a test names a launch by.
# ---------------------------------------------------------------------------

# The LIS v2 membership vocabulary, spelled as the specification spells it — the
# same two URIs `tests/integration/test_lti_launch_door.py` reads.
MEMBERSHIP_VOCABULARY = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URN = f"{MEMBERSHIP_VOCABULARY}Instructor"
LEARNER_ROLE_URN = f"{MEMBERSHIP_VOCABULARY}Learner"

# E1-07's near-miss and edge mints, by the names `app.wrong_launches` answers to.
# Copied rather than imported, for the reason ADR 0088's consequences give: both
# mocks declare a package named `app`, so importing either by name from outside
# its own package depends on which is on `sys.path` first.
ONLY_TEACHING_ASSISTANT_ROLE = "only_teaching_assistant_role"
ONLY_MENTOR_ROLE = "only_mentor_role"
TITLELESS_CONTEXT = "titleless_context"
TITLELESS_CONTEXT_WITH_LABEL = "titleless_context_with_label"

# ---------------------------------------------------------------------------
# The ground a launch resolves against, committed.
# ---------------------------------------------------------------------------

# The column carrying a prefix's code. SPEC §8 spells it — "`prefix.code` is
# unique across the whole table" — and the alternatives are here for the same
# reason every other candidate list in this suite is: a deliberate rename should
# be one line rather than a rewrite.
PREFIX_CODE_COLUMNS = ("code", "prefix_code", "name")

# Candidates, not names, exactly as `tests/integration/test_section_date_derivation.py`
# carries them: E0-06 gives `term` and `start_letter_map` a length in weeks and a
# start date without spelling any of the columns.
TERM_LENGTH_COLUMNS = ("length_weeks", "length")
TERM_START_COLUMNS = ("start_date", "starts_on", "start")
TERM_END_COLUMNS = ("end_date", "ends_on", "end")
LETTER_LENGTH_COLUMNS = ("length_weeks", "length")
LETTER_START_COLUMNS = ("start_date", "starts_on", "start")

# Spelled by E0-06: "**The letter column is named `letter`.**"
LETTER_COLUMN = "letter"

# The term this suite seeds around the day of the launch. **Every number is this
# suite's choice** and each one is chosen so that no assertion depends on when the
# suite is run: 18 weeks is §2.2's fall length, and starting three weeks before
# today leaves today comfortably inside it whatever the institution's timezone
# says the date is.
TERM_WEEKS = 18
TERM_STARTS_WEEKS_BEFORE_TODAY = 3

# The length the seeded start-letter map row gives the launch's own start letter.
# 12 weeks from the term's first day ends on day 83 of a 126-day term, so a
# section derived from it sits inside its term — which is what ADR 0021 requires
# before `apply_section_code` will write it at all.
LETTER_LENGTH_WEEKS = 12

# A start position the launch's own code certainly does not use, for the paired
# opposite of "the term's map holds a row for this code". Resolved against the
# launch's real start letter at seeding time rather than asserted to differ from
# it, so a mock that changes its section code cannot make this row collide with
# the one it is supposed to be unlike.
OTHER_START_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# How far from today a term that does **not** contain the day of the launch sits.
# A whole year, so no rounding, no timezone and no term length can bring it back.
DISTANT_TERM_YEARS = 1


def monday_on_or_before(day: date) -> date:
    """The Monday of `day`'s week.

    Every term and every start-letter row in this suite begins on a Monday, which
    is the convention `tests/integration/test_section_date_derivation.py` argues
    from §2.2's own seed map and §3.1's Sunday close.
    """
    return day - timedelta(days=day.weekday())


class LaunchGround:
    """The committed rows a launch has to resolve against, and what was seeded.

    Held as an object rather than returned as a tuple so a test can assert
    against the *seeded* values — this term's identifier, this map row's start
    date and length — rather than against a recomputation of the derivation it is
    checking. A test that recomputed would agree with a wrong implementation that
    made the same mistake (`docs/MISTAKES.md` entry 19).
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables
        self.chain: dict[str, Any] = {}
        self.prefix_row: Any = None
        self.term_row: Any = None
        self.letter_row: Any = None

    # -- what was seeded ----------------------------------------------------

    def key_of(self, table_name: str, row: Any) -> Any:
        return row[single_primary_key(require_table(self.tables, table_name))]

    @property
    def prefix_id(self) -> Any:
        if self.prefix_row is None:
            pytest.fail(
                "This ground was seeded with `prefix=False`, so there is no prefix to look a "
                "course up under. A test posing `unknown_prefix` asserts that nothing was written "
                "at all rather than that no row exists under a prefix that does not exist."
            )
        return self.key_of("prefix", self.prefix_row)

    @property
    def college_id(self) -> Any:
        """The `college` this launch's prefix hangs under, out of the chain that seeded it.

        Added by E2-02, whose condition is about which containment node a launcher's
        assignment is scoped to: a dean's grant is their college (SPEC §2.1), so a test
        that means to place a dean *over the launched context* needs the college above
        the launched prefix and no other. Two modules ask that question — the purview
        pair and the leadership-limb module next door — so it is answered once here
        rather than twice there (`docs/MISTAKES.md` entry 13).

        Read off the ancestors `seed_prefix` built, which is this fixture's own
        bookkeeping; that the answer really is the college above the seeded prefix is
        asserted independently, by walking `prefix` → `department` → `college` in the
        database, in the control at the head of
        `tests/integration/test_a_staff_launch_binds_only_inside_the_launchers_purview.py`.
        """
        if "college" not in self.chain:
            pytest.fail(
                "The chain this ground seeded holds no college (it holds "
                f"{sorted(self.chain)}), so there is no node to scope a dean's assignment to. "
                "SPEC §2.1 puts a prefix inside a department inside a college, and `seed_prefix` "
                "builds every ancestor the prefix row requires — a chain without one means the "
                "link is nullable and was left null, which would scope an assignment to nothing."
            )
        return self.key_of("college", self.chain["college"])

    @property
    def term_id(self) -> Any:
        return self.key_of("term", self.term_row)

    @property
    def letter_start(self) -> date:
        table = require_table(self.tables, "start_letter_map")
        return self.letter_row[require_column(table, LETTER_START_COLUMNS)]

    @property
    def letter_length_weeks(self) -> int:
        column = require_column(
            require_table(self.tables, "start_letter_map"), LETTER_LENGTH_COLUMNS
        )
        return int(self.letter_row[column])

    # -- seeding ------------------------------------------------------------

    def seed_prefix(self, code: str) -> Any:
        table = require_table(self.tables, "prefix")
        column = require_column(table, PREFIX_CODE_COLUMNS)
        self.prefix_row = self.rows.seed("prefix", self.chain, **{column: code})
        return self.prefix_row

    def seed_term(self, *, containing_today: bool) -> Any:
        table = require_table(self.tables, "term")
        # `datetime.now(UTC).date()` rather than `date.today()`: ruff's `DTZ` rules
        # refuse the naive form, and the margin here — a term starting three weeks
        # ago and running eighteen — is far wider than any timezone offset, so
        # which day boundary this lands on cannot change what the test asserts.
        today = datetime.now(UTC).date()
        start = monday_on_or_before(today) - timedelta(weeks=TERM_STARTS_WEEKS_BEFORE_TODAY)
        if not containing_today:
            start = start - timedelta(days=365 * DISTANT_TERM_YEARS)
        end = start + timedelta(days=TERM_WEEKS * 7 - 1)
        self.term_row = self.rows.seed(
            "term",
            self.chain,
            **{
                require_column(table, TERM_LENGTH_COLUMNS): TERM_WEEKS,
                require_column(table, TERM_START_COLUMNS): start,
                require_column(table, TERM_END_COLUMNS): end,
            },
        )
        return self.term_row

    def seed_term_starting(self, start: date, weeks: int = TERM_WEEKS) -> Any:
        """One term beginning on `start`, running `weeks`, with its end derived.

        Added by E1-11 for deferred E1-10 item 2, whose whole question is which
        *day* a launch happens on: a term seeded around "today" by the calendar
        above spans eighteen weeks and therefore contains both candidate dates,
        so it cannot tell the two apart. The end is derived from the length rather
        than passed in, so a schema that relates the two agrees with itself.
        """
        table = require_table(self.tables, "term")
        self.term_row = self.rows.seed(
            "term",
            self.chain,
            **{
                require_column(table, TERM_LENGTH_COLUMNS): weeks,
                require_column(table, TERM_START_COLUMNS): start,
                require_column(table, TERM_END_COLUMNS): start + timedelta(days=weeks * 7 - 1),
            },
        )
        return self.term_row

    def seed_letter(self, letter: str) -> Any:
        table = require_table(self.tables, "start_letter_map")
        start_column = require_column(table, LETTER_START_COLUMNS)
        term_start = self.term_row[
            require_column(require_table(self.tables, "term"), TERM_START_COLUMNS)
        ]
        self.letter_row = self.rows.seed(
            "start_letter_map",
            self.chain,
            **{
                LETTER_COLUMN: letter,
                require_column(table, LETTER_LENGTH_COLUMNS): LETTER_LENGTH_WEEKS,
                start_column: term_start,
            },
        )
        return self.letter_row


@pytest.fixture
def launch_ground(
    committed_rows: Any, metadata_tables: dict[str, Any]
) -> Callable[..., LaunchGround]:
    """Seed and commit the rows a launch resolves against, with each part optional.

    Every option has a paired opposite, because three of E1-10's seven defects are
    the absence or the mismatch of one of these rows and none of them is worth
    asserting except beside the case where the same launch provisions correctly:

      - `prefix=False` — the launch's prefix does not exist in `prefix`, which
        the work order makes `unknown_prefix`. §2.1 builds the org top-down, so a
        launch cannot invent the containment chain.
      - `term="past"` — a term exists and does not contain the day of the launch,
        which is `no_term_for_launch_date`. Deliberately *a term that exists*
        rather than no term at all: "the one term whose dates contain the day of
        the launch" is a different rule from "any term", and an empty table
        satisfies both.
      - `letter=False` — the term's start-letter map holds a row, for some other
        start position, and none for this launch's code. Again a row rather than
        an empty map, for the same reason: ADR 0021 refuses a code whose start
        position the term's map has no row for, and `section_code_underivable` is
        that refusal reaching the defect record.

    Committed, because the tool opens its own connection out of `DATABASE_URL`.
    """

    def seed(
        label: ContextLabel,
        *,
        prefix: bool = True,
        term: str = "current",
        letter: bool = True,
        term_starts_on: date | None = None,
    ) -> LaunchGround:
        ground = LaunchGround(committed_rows, metadata_tables)
        if prefix:
            ground.seed_prefix(label.prefix)
        if term_starts_on is not None:
            # E1-11, deferred E1-10 item 2: a term whose edges the caller chose, so
            # that exactly one of "today in UTC" and "today in the institution's
            # zone" falls inside it. `term` is ignored here rather than combined —
            # the two are different ways of answering the same question and a
            # caller that passed both would get whichever this file happened to
            # apply last.
            ground.seed_term_starting(term_starts_on)
        else:
            ground.seed_term(containing_today=term == "current")
        if letter:
            ground.seed_letter(label.start_letter)
        else:
            unlike = next(
                candidate
                for candidate in OTHER_START_LETTERS
                if candidate != label.start_letter.upper()
            )
            ground.seed_letter(unlike)
        committed_rows.commit()
        return ground

    return seed


# ---------------------------------------------------------------------------
# Reading back what provisioning wrote.
# ---------------------------------------------------------------------------

# Not this suite's choice: E0-05 created these columns under these names, and its
# own criterion is that LMS-owned columns carry the `lms_` prefix.
COURSE_NUMBER_COLUMN = "lms_number"
COURSE_TITLE_COLUMN = "lms_title"
SECTION_CODE_COLUMN = "lms_section_code"

# Spelled by E1-10's work order, which settles both: "`course.title_is_fallback`
# boolean NOT NULL default false" and "`section.lms_context_memberships_url`
# nullable text — LMS-owned, `lms_` marked".
TITLE_IS_FALLBACK_COLUMN = "title_is_fallback"
SECTION_ADDRESS_COLUMN = "lms_context_memberships_url"

# The binding the round-3 ruling adds to `section`: the platform's own identifier
# for the context a section was discovered from, and the registration scope that
# identifier is unique within. `lms_`-marked because the platform supplies it and
# Pulse never edits it (ADR 0014); the deployment is a foreign key, which the
# E0-35 rule-1 sweep accounts for as structural. Together they are what makes a
# section resolvable by *who said so* rather than by what its label parses to.
SECTION_CONTEXT_ID_COLUMN = "lms_context_id"

# Spelled by the work order too: the append-only record E11 reads, and its five
# fields beside the key.
DEFECT_TABLE = "launch_defect"
DEFECT_COLUMNS = frozenset({"id", "kind", "issuer", "deployment_id", "context_id", "created_at"})

UNPARSEABLE_CONTEXT_LABEL = "unparseable_context_label"
UNKNOWN_PREFIX = "unknown_prefix"
OUT_OF_BAND_COURSE_NUMBER = "out_of_band_course_number"
NO_TERM_FOR_LAUNCH_DATE = "no_term_for_launch_date"
SECTION_CODE_UNDERIVABLE = "section_code_underivable"

# The two the round-3 security review added. `context_collision` is the HIGH: a
# launch whose parsed identity names a section some *other* context is bound to,
# which before the fix repointed that section's stored roster address and rewrote
# its course's title. `roster_address_refused` is the MEDIUM: an address the
# registration-address rules refuse, which leaves the section provisioned and its
# address NULL — SPEC §7.3's never-synced state, which is a state and not a fault.
CONTEXT_COLLISION = "context_collision"
ROSTER_ADDRESS_REFUSED = "roster_address_refused"

# E2-02's, and the E1 boundary review's M9 reaching the record: a launch admitted by
# §7.3's leadership limb whose context sits outside the launching person's own grant.
# The section is not bound and the discovered roster address is not stored — the launch
# lands the person all the same, exactly as every other kind here does. Asserted in
# `tests/integration/test_a_staff_launch_binds_only_inside_the_launchers_purview.py`.
CONTEXT_OUTSIDE_PURVIEW = "context_outside_purview"

DEFECT_KINDS = (
    UNPARSEABLE_CONTEXT_LABEL,
    UNKNOWN_PREFIX,
    OUT_OF_BAND_COURSE_NUMBER,
    NO_TERM_FOR_LAUNCH_DATE,
    SECTION_CODE_UNDERIVABLE,
    CONTEXT_COLLISION,
    ROSTER_ADDRESS_REFUSED,
    CONTEXT_OUTSIDE_PURVIEW,
)


class ProvisionedRows:
    """What is in the tables E1-10 writes, read on a connection that sees commits.

    Every method answers with rows rather than counts. Criterion 1 asks for
    idempotence "asserted on row identity, not just count", and a helper that
    could only count would make that criterion unassertable through it.
    """

    def __init__(self, session: Any, tables: dict[str, Any], *, refresh: bool) -> None:
        self.session = session
        self.tables = tables
        self.refresh = refresh

    def _table(self, name: str) -> Any:
        table = self.tables.get(name)
        if table is None:
            pytest.fail(
                f"There is no `{name}` table (there are {sorted(self.tables)}). E1-10's migration "
                "adds `launch_defect`; E0-05 creates `course` and `section`, and E0-08 `user`."
            )
        return table

    def key(self, name: str) -> str:
        """The name of one table's single primary key column (ADR 0016 makes it one uuid)."""
        return single_primary_key(self._table(name))

    def link(self, name: str, target: str) -> str:
        """The column on `name` whose foreign key points at `target`.

        Found by following the key rather than guessed from a naming convention.
        `course.prefix_id` and `section.course_id` are almost certainly spelled
        that way, and "almost certainly" is how a test ends up asserting `None ==
        None` — a `row.get("prefix_id")` that answers `None` for every row makes a
        filter match nothing, and "no course was created" is what this suite reads
        that as.
        """
        table = self._table(name)
        found = sorted(
            {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
        )
        if len(found) != 1:
            pytest.fail(
                f"`{name}` has {len(found)} foreign keys to `{target}` ({found}); it references "
                f"{sorted({key.column.table.name for key in table.foreign_keys})}. SPEC §8 gives "
                "this schema one path from a section to its course and one from a course to its "
                "prefix, and these tests address rows through it."
            )
        return found[0]

    def all_of(self, name: str) -> list[Any]:
        """Every row of one table, as mappings.

        `refresh` decides whether the read transaction is ended first, and the two
        cases are opposite rather than a preference. Reading what a launch driven
        through the *door* wrote means reading a commit made on another
        connection, and this session has been open since it seeded — so its
        transaction has to end before the next statement can see it. Reading what
        the writer wrote on *this* session means reading uncommitted work, and a
        rollback there would discard the very rows under test.
        """
        table = self._table(name)
        if self.refresh:
            self.session.rollback()
        return list(self.session.execute(table.select()).mappings())

    def courses(self) -> list[Any]:
        return self.all_of("course")

    def sections(self) -> list[Any]:
        return self.all_of("section")

    def users(self) -> list[Any]:
        return self.all_of("user")

    def defects(self) -> list[Any]:
        return self.all_of(DEFECT_TABLE)

    def addresses(self) -> list[Any]:
        """Every roster address stored on any section, ignoring the sections with none."""
        return [
            row[SECTION_ADDRESS_COLUMN]
            for row in self.sections()
            if row.get(SECTION_ADDRESS_COLUMN)
        ]


@pytest.fixture
def provisioned_rows(committed_rows: Any, metadata_tables: dict[str, Any]) -> ProvisionedRows:
    """What a launch driven through the door wrote, read on `committed_rows`'s connection.

    The same connection that seeded, deliberately: its transaction is ended before
    each read, so it sees what the tool committed on its own connection, and its
    teardown removes whatever appeared — including rows this suite never wrote.
    """
    return ProvisionedRows(committed_rows.session, metadata_tables, refresh=True)


class ProvisioningContract:
    """Every name and helper E1-10's two test modules read a launch through.

    Handed over as a fixture rather than imported, for the reason
    `tests/integration/test_mock_lms_launch.py` gives about every fixtures import:
    an import of a fixtures module by name depends on where pytest put `tests/` on
    `sys.path`, and an import error is not a red. Several modules need all of it —
    `test_launch_time_provisioning.py`, `test_launch_provisioning_defects.py` and,
    from E2-02, `test_a_staff_launch_binds_only_inside_the_launchers_purview.py` —
    so a copy in each would be as many copies of one rule (`docs/MISTAKES.md` entry
    13) about what a context label is made of.
    """

    context_claim = CONTEXT_CLAIM
    nrps_claim = NRPS_CLAIM
    roles_claim = ROLES_CLAIM
    deployment_id_claim = DEPLOYMENT_ID_CLAIM
    memberships_url_member = MEMBERSHIPS_URL_MEMBER
    label_separator = LABEL_SEPARATOR

    course_number_column = COURSE_NUMBER_COLUMN
    course_title_column = COURSE_TITLE_COLUMN
    title_is_fallback_column = TITLE_IS_FALLBACK_COLUMN
    section_code_column = SECTION_CODE_COLUMN
    section_address_column = SECTION_ADDRESS_COLUMN
    section_context_id_column = SECTION_CONTEXT_ID_COLUMN

    defect_table = DEFECT_TABLE
    defect_columns = DEFECT_COLUMNS
    defect_kinds = DEFECT_KINDS
    unparseable_context_label = UNPARSEABLE_CONTEXT_LABEL
    unknown_prefix = UNKNOWN_PREFIX
    out_of_band_course_number = OUT_OF_BAND_COURSE_NUMBER
    no_term_for_launch_date = NO_TERM_FOR_LAUNCH_DATE
    section_code_underivable = SECTION_CODE_UNDERIVABLE
    context_collision = CONTEXT_COLLISION
    roster_address_refused = ROSTER_ADDRESS_REFUSED
    context_outside_purview = CONTEXT_OUTSIDE_PURVIEW

    instructor_role_urn = INSTRUCTOR_ROLE_URN
    learner_role_urn = LEARNER_ROLE_URN

    only_teaching_assistant_role = ONLY_TEACHING_ASSISTANT_ROLE
    only_mentor_role = ONLY_MENTOR_ROLE
    titleless_context = TITLELESS_CONTEXT
    titleless_context_with_label = TITLELESS_CONTEXT_WITH_LABEL

    parse_label = staticmethod(parse_context_label)
    context_of = staticmethod(context_of)
    memberships_url_in = staticmethod(memberships_url_in)
    relabelled = staticmethod(relabelled)
    with_course_number = staticmethod(with_course_number)
    with_section_code = staticmethod(with_section_code)
    with_context_id = staticmethod(with_context_id)
    with_context_title = staticmethod(with_context_title)
    with_memberships_url = staticmethod(with_memberships_url)

    @staticmethod
    def label_of(claims: Mapping[str, Any]) -> ContextLabel:
        """The launch's context label, split into the three parts E1-10 parses."""
        return parse_context_label(context_of(claims).get("label"))

    @staticmethod
    def title_of(claims: Mapping[str, Any]) -> Any:
        """The platform's own title for the context, whatever it is."""
        return context_of(claims).get("title")

    @staticmethod
    def context_id_of(claims: Mapping[str, Any]) -> Any:
        """The context claim's `id`, which the defect record carries and nothing else does."""
        return context_of(claims).get("id")

    @staticmethod
    def fallback_title(label: ContextLabel) -> str:
        """The title E1-10 stores when the platform sends none.

        Todd's ruling of 2026-08-26: "'BIOL 215' style — prefix and number parsed
        from the label". One space, because that is how SPEC §2.1 writes a course
        throughout — "Course (e.g., BIOL 215)".
        """
        return f"{label.prefix} {label.number}"


@pytest.fixture
def provisioning_contract() -> ProvisioningContract:
    """The names and helpers E1-10's tests read a launch through. See the class above."""
    return ProvisioningContract()


@pytest.fixture
def insert_statement_for(
    metadata_tables: dict[str, Any],
) -> Callable[..., tuple[str, dict[str, Any]]]:
    """A textual `INSERT` for one table, with values invented for whatever it requires.

    For the grant tests, which have to *provoke* a write on the application
    connection rather than seed one: `seed_row` runs on the superuser session and
    would answer the wrong question. The column list comes from `Base.metadata` and
    the values from the same walker every other fixture here seeds with, so a
    column added to the table later is filled rather than omitted.

    **It refuses to build ancestors.** A required foreign key means the caller
    wants a row under a parent that has to exist, and inventing one on the
    application connection would be testing a grant nobody asked about. The
    failure says to copy a seeded row instead.
    """
    from fixtures.supervision import invented_value

    def build(name: str, **overrides: Any) -> tuple[str, dict[str, Any]]:
        table = require_table(metadata_tables, name)
        values: dict[str, Any] = dict(overrides)
        for column in table.columns:
            if column.name in values:
                continue
            if column.computed is not None or column.identity is not None:
                continue
            if column.server_default is not None or column.default is not None:
                continue
            if column.nullable:
                continue
            if column.foreign_keys:
                pytest.fail(
                    f"`{name}.{column.name}` is a required foreign key, so a row cannot be built "
                    "here without seeding a parent. Copy the values off a row seeded through "
                    "`committed_rows` instead, which is what the `user` case in the grant tests "
                    "does."
                )
            values[column.name] = invented_value(table, column)
        columns = ", ".join(f'"{column}"' for column in values)
        binds = ", ".join(f":{column}" for column in values)
        # S608 is for SQL assembled out of a variable, and every name interpolated
        # here comes from `Base.metadata` rather than from anything a test or a
        # request supplies.
        statement = f'INSERT INTO public."{name}" ({columns}) VALUES ({binds})'  # noqa: S608
        return statement, values

    return build


# ---------------------------------------------------------------------------
# Driving a whole launch at this project's own door.
# ---------------------------------------------------------------------------

# The mock platform's configuration surface, from `mock-lms/app/config.py` and
# spelled as `tests/integration/test_lti_launch_door.py` spells it.
MOCK_LMS_TOOL_LOGIN_URL_VARIABLE = "MOCK_LMS_TOOL_LOGIN_URL"
MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE = "MOCK_LMS_TOOL_LAUNCH_URL"

# Where this platform's registration sends a browser to begin a launch. Chosen so
# that no implementation could arrive at it by accident; `.invalid` is RFC 2606's.
REGISTERED_AUTHORIZATION_ENDPOINT = "http://lti-platform.invalid/e1-10-configured-authorize"

# Where E1-08's door sends a browser once a launch has verified. Only the prefix
# is asserted here: which role segment follows is E1-08's rule, asserted in that
# ticket's own suite, and nothing E1-10 does may change it either way.
LANDING_PREFIX = "/app/"

# E1-13's calm page, by the testid E1-15's browser proof addresses it by. The
# second of the two answers a *verified* launch can get, and the one a subject
# Pulse holds no assignment and no live enrollment for is met with. Spelled here
# as `tests/fixtures/landing.py` spells it; see `LaunchDriver.accepted`.
NO_ACCESS_TESTID = "no-access"

# `ENVIRONMENT`, spelled as `tests/unit/test_docs_exposure.py` and the launch-door
# suite spell it. **Wherever an application is built, it is set through
# `tool_doors`** rather than with a bare `setenv`, so a module that builds something
# out of `Settings` at import is built under the value the test chose
# (`docs/MISTAKES.md` entry 3). `registered_platform` below builds no application
# and sets it directly; that fixture says why, and why the distinction holds there.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"


class LaunchDriver:
    """One tool, one registered mock platform, and whole launches through both.

    Here rather than in a test module because E1-10 has two of them and the
    machinery is identical: a second copy of "how a launch reaches this door"
    would be a second thing to fix when the door changes (`docs/MISTAKES.md`
    entry 13), and the door has already changed once under E1-08.

    **Every launch travels the real route.** E1-08's door judges a launch against
    the `state` and `nonce` it issued at `/lti/login`, so a launch minted
    independently of the tool is refused for the handshake and for nothing else —
    whatever E1-07 defect it was minted with. So `launch` drives the login leg for
    real and hands the platform back the tool's own values to mint against, which
    is what `mint_defect` in the launch-door suite does and for the same reason.
    """

    def __init__(self, tool: Any, contract: Any, platform: Any, registration: Any = None) -> None:
        self.tool = tool
        self.contract = contract
        self.platform = platform
        # The `lti_platform` and `lti_deployment` rows this platform's launches
        # resolve to. Kept so a test can assert what a section was *bound* to
        # rather than only what it was called: the round-3 ruling makes
        # `(lti_deployment_id, lms_context_id)` the identity a section is looked
        # up by, and the deployment half of that pair is a row nothing else here
        # holds a handle on.
        self.registration = registration

    def offers(self) -> list[Any]:
        return self.platform.require_offers()

    def offer_for_role(self, role_uri: str) -> Any:
        """The launch this platform offers whose *signed* roles claim carries `role_uri`.

        Found by minting rather than by naming a seeded user, so nothing here is a
        copy of `mock-lms/app/seed.py`'s identifiers and nothing goes stale against
        a reseeding. The offer's own form parameters carry no roles, so the signed
        token is the only place this question can be answered.
        """
        seen: list[Any] = []
        for offer in self.offers():
            roles = self.platform.mint(offer).claims.get(ROLES_CLAIM) or []
            seen.append(roles)
            if role_uri in roles:
                return offer
        pytest.fail(
            f"No launch the mock platform offers carries the role {role_uri!r}. What it offers: "
            f"{seen}. E0-14's criterion 7 is that the platform provides both a student launch and "
            "an instructor launch, and E1-10's staff rule is about telling them apart."
        )

    def claims_of(self, offer: Any) -> dict[str, Any]:
        """One launch's claims, minted without involving the tool.

        Used to read a launch's context label *before* seeding the rows that
        launch will need — the prefix it names, the term's map row for its code.
        Nothing is delivered to the door, so this consumes no handshake.
        """
        return dict(self.platform.mint(offer).claims)

    def launch(self, offer: Any, defect: str | None = None) -> tuple[Any, Any]:
        """One whole launch, from the platform's form to the tool's answer.

        Answers the tool's response and the launch that was delivered, so a test
        asserts against the claims the platform actually signed rather than
        against values written down in a test module.
        """
        if self.tool is None:
            pytest.fail(
                "This driver was built by `registered_platform`, which starts and registers a "
                "platform and builds no tool in front of it. Ask for `launch_driver` instead: a "
                "test that drives a whole launch needs the door."
            )
        started = self.tool.post(self.contract.lti_login, data=offer.parameters)
        assert started.status_code in (302, 303, 307), (
            f"`POST {self.contract.lti_login}` answered {started.status_code} rather than a "
            f"redirect to the platform's authorization endpoint. Body begins "
            f"{started.text[:300]!r}."
        )
        location = started.headers.get("location") or ""
        parameters = dict(parse_qsl(urlsplit(location).query))
        assert parameters.get("state") and parameters.get("nonce"), (
            f"The tool's login initiation redirected to {location!r}, which carries no "
            "`state`/`nonce` for the platform to mint against — so every launch would be refused "
            "for a handshake mismatch rather than judged on what a test is about."
        )
        signed = self.platform.mint(
            offer, state=parameters["state"], nonce=parameters["nonce"], defect=defect
        )
        body = {"id_token": signed.id_token}
        if signed.state is not None:
            body["state"] = signed.state
        return self.tool.post(self.contract.lti_launch, data=body), signed

    @staticmethod
    def landed(response: Any, what: str) -> None:
        """The launch was accepted and the person was sent to a view.

        Asserted on every launch these modules drive, and it is not decoration:
        E1-10's work order rules that "a provisioning refusal NEVER fails the
        launch or the person's landing". A test that only read the rows could not
        tell a launch that provisioned nothing from a launch the door refused.

        **Since E1-13 this says more than it used to**, and its callers had to be
        sorted into two groups. The landing comes from the launching person's own
        live assignments now, so a launch by a subject Pulse holds nothing about is
        answered with the calm no-access page rather than a role route. A module
        that asserts *this* has to seed its subject a landing — the door suites do,
        through `landing_ground` in `tests/fixtures/landing.py`. A module that only
        ever needed "the launch was not refused" asserts `accepted` below instead,
        and every provisioning suite is in that group: each of them asserts over
        the very tables a landing would have to be built out of.
        """
        assert response.status_code in (302, 303, 307), (
            f"{what} answered {response.status_code} rather than the redirect E1-08's door issues "
            f"for a launch that verified. Body begins {response.text[:400]!r}."
        )
        location = response.headers.get("location") or ""
        assert location.startswith(LANDING_PREFIX), (
            f"{what} redirected to {location!r}, which does not begin `{LANDING_PREFIX}`. E1-08 "
            "lands a verified launch on a role-named route; E1-10 must not change that, whatever "
            "it did or did not write."
        )

    @staticmethod
    def accepted(response: Any, what: str) -> None:
        """The door did not **refuse** this launch, whichever of its two answers it gave.

        E1-10's rule is that "a provisioning refusal NEVER fails the launch", and
        until E1-13 there was one shape that satisfied it: a redirect to a role
        route. There are two now — that redirect, and the calm no-access page a
        person whose rows entitle them to no view is met with — and both mean the
        same thing here: the token verified, the writer ran, and nothing about the
        context stopped the request.

        **It is deliberately weaker than `landed`**, and the modules that use it
        say why in their own docstrings. Three reasons recur. A test that asserts
        `course`, `section` or `user` is *empty* cannot seed a landing, because
        every route to one writes into at least one of those. A test that asserts
        exactly one section exists cannot either. And a test whose subject is the
        `user` row a *first* launch writes cannot seed the row it is about
        (`docs/MISTAKES.md` entry 30) — a first-ever launch by anybody reaches the
        calm page by construction, since the `user` row an enrollment would hang
        off does not exist yet.

        **What it gives up, stated plainly**: this would pass against a door that
        had stopped landing anybody at all. That is not left uncovered — it is
        covered where it belongs, by `tests/integration/test_lti_launch_door.py`,
        `test_the_launch_views_name_nobody.py`, `test_dual_door_identity_merge.py`
        and `test_landing_resolves_from_assignments.py`, all of which seed rows and
        assert `landed` or a route by name.
        """
        assert response.status_code in (200, 302, 303, 307), (
            f"{what} answered {response.status_code}. A 4xx is the door refusing the launch, and "
            "E1-10's work order rules that a provisioning refusal never fails one. Body begins "
            f"{response.text[:400]!r}."
        )
        if response.status_code == 200:
            assert NO_ACCESS_TESTID in response.text, (
                f"{what} answered 200 with a page carrying no `{NO_ACCESS_TESTID}` testid (body "
                f"begins {response.text[:400]!r}). The only 200 either door answers a verified "
                "entry with is E1-13's calm page; anything else is a shape nobody has decided on."
            )
            return
        location = response.headers.get("location") or ""
        assert location.startswith(
            LANDING_PREFIX
        ), f"{what} redirected to {location!r}, which does not begin `{LANDING_PREFIX}`."


@pytest.fixture
def provisioning_platform(mock_platforms: Any, door_contract: Any) -> Any:
    """A mock platform pointed at this tool's own login and launch URLs."""
    return mock_platforms(
        {
            MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_login}"
            ),
            MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_launch}"
            ),
        }
    )


@pytest.fixture
def provisioning_jwks_url(provisioning_platform: Any) -> str:
    """Where that platform publishes the key set a launch has to verify against."""
    document = provisioning_platform.discovery()
    advertised = (document or {}).get("jwks_uri")
    assert isinstance(advertised, str) and advertised, (
        "The mock platform's discovery document advertises no `jwks_uri` (it carries "
        f"{sorted(document or {})}), so there is nothing to register and no launch can verify."
    )
    return advertised


@pytest.fixture
def launch_driver_in(
    tool_doors: Any,
    door_contract: Any,
    provisioning_platform: Any,
    provisioning_jwks_url: str,
    register_platform: Any,
) -> Callable[..., LaunchDriver]:
    """Build the launch door under a named `ENVIRONMENT`, registering the platform once.

    A factory, because one of E1-10's rules only exists outside development: the
    roster address a launch advertises is judged by
    `app.models.lti.refuse_invalid_registration_addresses`, and every rule that
    function applies is switched off under the development name so the demo stack
    can seed the mock's own cleartext addresses
    (`tests/unit/test_registration_address_constraints.py`). A test about a
    refused address has to run somewhere a refusal happens, and setting the
    variable through `tool_doors` is what makes it true both at import — for
    anything built out of `Settings` — and at call time.

    **The registration is written once however many tools are built.** Two rows
    registering one issuer would leave the door choosing between them, and which
    one it chose would decide the result of every test using it.
    """
    written: list[Any] = []

    def build(environment: str | None = None) -> LaunchDriver:
        if not written:
            written.append(
                register_platform(
                    provisioning_platform.require_offers()[0],
                    provisioning_jwks_url,
                    REGISTERED_AUTHORIZATION_ENDPOINT,
                )
            )
        values = {door_contract.settings["public_base_url"]: door_contract.public_base_url}
        if environment is not None:
            values[ENVIRONMENT_VARIABLE] = environment
        tool = tool_doors(values, {urlsplit(provisioning_jwks_url).hostname: provisioning_platform})
        return LaunchDriver(tool, door_contract, provisioning_platform, written[0])

    return build


@pytest.fixture
def launch_driver(launch_driver_in: Callable[..., LaunchDriver]) -> LaunchDriver:
    """This project's launch door, with one registered mock platform behind it.

    Built with no `ENVIRONMENT` override, so it runs under whatever
    `configured_env` laid down — the development name, which is what every test
    about the ordinary path wants.
    """
    return launch_driver_in()


@pytest.fixture
def registered_platform(
    monkeypatch: pytest.MonkeyPatch,
    provisioning_platform: Any,
    provisioning_jwks_url: str,
    register_platform: Any,
) -> LaunchDriver:
    """The same platform, registered, with no tool built in front of it.

    For the cases E1-10 has to drive at the writer directly rather than through
    the door — the course-number bands, because no mint produces a launch carrying
    an out-of-band number and E1-07's mint list is closed. The platform is still
    registered, and the claims a test rewrites are still a launch this platform
    signed, so what the writer is handed differs from a door's in exactly the one
    member the test changed.

    `launch` is unavailable on what this returns, deliberately: a test that means
    to drive the whole route should ask for `launch_driver` and get the door.

    **It runs under the development `ENVIRONMENT`, and the name is chosen here
    rather than inherited.** Every other route to the writer states its
    environment: a door-driven test gets the development name from `configured_env`
    through `tool_doors`, and
    `tests/integration/test_a_roster_address_is_judged_by_the_registration_rules.py`
    asks `launch_driver_in` for a deployment's. This chain builds no door, so
    before this line it ran under whatever the process happened to be holding —
    which was a developer's `.env`, loaded into `os.environ` by the in-process
    Alembic run (`whole_environment_restored` in `tests/fixtures/database.py` has
    that incident). Locally that meant `development` and the band tests passed; in
    CI, which has no `.env`, `ENVIRONMENT` was unset, and an unset value is a
    deployment — `.env.example`: "Anything other than `development` is a
    deployment". The registration-address rules were then in force, the mock's own
    cleartext `http://mock-lms:8000/...` roster address was refused, and every
    in-band course number was recorded as a `roster_address_refused` defect.

    **A bare `setenv` is sound *here*, where the comment on `ENVIRONMENT_VARIABLE`
    above says it is not in general.** That comment is about a module which builds
    something out of `Settings` at import: nothing below re-imports the
    application, so such a module would not see this. This fixture builds no
    application at all — no `create_app`, no door — and the only reader is the
    writer the test calls directly, in the test body, after this has run. If that
    ever stopped being true the band tests would go red rather than quietly assert
    something else, which is how this was found in the first place.

    **The pin narrows what a band case can fail on; it does not soften it.** SPEC
    §8's bands hold in every environment, and what the development name switches
    off is a different rule, about the addresses this container fetches, asserted
    under a deployment's name in the module quoted above. So the only defect an
    in-band case can record is one about its number, which is what it claims to be
    about (`docs/MISTAKES.md` entry 3).
    """
    from app.config import DEVELOPMENT_ENVIRONMENT

    assert isinstance(DEVELOPMENT_ENVIRONMENT, str) and DEVELOPMENT_ENVIRONMENT.strip(), (
        f"`app.config.DEVELOPMENT_ENVIRONMENT` is {DEVELOPMENT_ENVIRONMENT!r}, so the name pinned "
        "below is not a development environment and every test using this fixture would run under "
        "a deployment without saying so. `tests/unit/test_registration_address_constraints.py` "
        "reads the same constant; its non-emptiness is proved there, by a control of its own."
    )
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT_ENVIRONMENT)

    registration = register_platform(
        provisioning_platform.require_offers()[0],
        provisioning_jwks_url,
        REGISTERED_AUTHORIZATION_ENDPOINT,
    )
    return LaunchDriver(None, None, provisioning_platform, registration)


@pytest.fixture
def rows_on(metadata_tables: dict[str, Any]) -> Callable[[Any], ProvisionedRows]:
    """The same reader, on a session the caller drove the writer with directly.

    A factory rather than a fixture of its own because the session in question is
    the one the test handed to `provisioning.call`, and nothing here should be
    choosing which session that is.
    """

    def build(session: Any) -> ProvisionedRows:
        return ProvisionedRows(session, metadata_tables, refresh=False)

    return build
