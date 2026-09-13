"""Nothing under `frontend/src/` reaches the clock except four named files — ticket E4-11.

**What this widens, and why E4-11 owns the widening.** E4-08 shipped the first
version of this rule as a vitest case inside `PulseTrendChart.test.tsx`: it reads
four source files by name — `PulseTrendChart.tsx`, `TrendPair.tsx`, `WeekNav.tsx`
and `instructorReportTrendCopy.ts` — and refuses, among other reaches, the three
forms that reach the `Date` built-in. That guard is a good one and stays: it is
about *those* components being props-in, DOM-out, and it also refuses `fetch`,
storage, the cookie jar and an import from `../api`, none of which this file has
any business refusing of a tree that legitimately contains an API client.

What it could not say is anything about the rest of `frontend/src/`. A
hand-listed inventory answers only for what is on the list, and the list was
written before the report page existed — so the derivation SPEC §2.2 forbids
could arrive in any file nobody thought to add. E4-11 is the ticket that adds
the report page and the surface around it, so it is the ticket that widens the
inventory to a walk.

**Why the clock is the thing being refused.** SPEC §2.2 gives course-level pages
two week axes and says the second cannot be computed from the first: "a section
that began in the term's fourth week, or paused over a break week, breaks any
offset a chart might compute". Both numbers ride on the payload for exactly that
reason (`app.schemas.report.WeekView`), and E4-08's known trap was a frontend
that recomputes them. Every recomputation needs today's date, so refusing the
clock refuses the whole family at once — a sharper rule than refusing arithmetic,
because arithmetic has a hundred spellings and `Date` has three.

The instructor's Monday report is the surface this most nearly happened on: it
draws a week axis, it navigates across weeks, and it renders no timestamp at all.
The page is required to construct no `Date`, and this is what holds it to that
after the ticket has merged.

**Four files may, each for the same reason, and each is named rather than
patterned.** They format an instant the server sent into words a person reads —
a window's closing time — which is display, not derivation: the value comes from
the answer, and nothing about a week is computed from the machine's clock. The
fifth is a test that holds the reaches as data. A file is on that list or it is
refused; there is no shape of code that exempts itself.

**Both directions, before either verdict** (`docs/MISTAKES.md` entries 3 and 35).
Every refused shape is run against a source that certainly carries it and sources
that certainly do not, so a pattern that has gone blind says so rather than
reporting a clean tree. And every allowed file is required to *actually trip* a
shape: an allowance for a file that no longer reaches the clock is an allowance
that would cover the day it starts again, and nothing else would notice.

**Disclosed limits, stated rather than discovered.**

  - **Comments are read like code**, exactly as the sibling sweep reads them. A
    clock read written in prose is inert, so a hit inside a comment is a false
    positive — a loud one, in a named line, and cheaper than a parser that could
    be wrong about where a comment ends. The corollary is that prose about the
    *concept* must not trip a shape: "no `Date` is constructed" is a sentence two
    of these files write about themselves, and it is a control below.
  - **The clock reached through an alias** (`const clock = Date;`) or through
    `globalThis` is not seen. Neither is a way anybody arrives here by accident,
    which is the arrival this guard is for — E4-08's own note says the same of
    its narrower version.
  - **`performance.now()` is not refused.** It is a monotonic timer with no
    relation to a calendar, so no week can be derived from it.
  - **`Intl.DateTimeFormat` is not refused**, and must not be: it formats an
    instant its caller already holds, which is precisely what the four allowed
    files do with the server's answer.
  - This reads files. It cannot see a clock read assembled at runtime, and
    nothing here claims otherwise.
"""

import re
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SOURCE = REPO_ROOT / "frontend" / "src"
SOURCE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")

# Two files E4-11 names in its own text, required to be among what the walk read
# before any silence about the rest counts. A moved directory, a renamed suffix
# or an `rglob` that matched nothing would otherwise make this module's whole
# claim true of an empty reading (`docs/MISTAKES.md` entry 3).
FILES_THE_WALK_MUST_FIND = (
    "frontend/src/routes/instructor/InstructorMondayReport.tsx",
    "frontend/src/components/WeekEyebrow.tsx",
)


class Allowed(NamedTuple):
    """One file that may reach the clock, and the sentence that says why."""

    path: str
    why: str


# The whole allowance, and there is no other. Each entry is a file that turns an
# instant **the server sent** into words a person reads; none of them computes a
# week, a length or a calendar, and none of them reads the clock to find out what
# time it is now.
MAY_READ_THE_CLOCK = (
    Allowed(
        "frontend/src/components/WeekEyebrow.tsx",
        "formats `OpenSurvey.closes_at` — the instant the survey window shuts — in the reader's "
        "own timezone. The instant is the API's; what is done to it here is display.",
    ),
    Allowed(
        "frontend/src/components/WeekEyebrow.test.tsx",
        "renders the eyebrow and formats the same instant itself, to say what the component "
        "should have written. It is checking a rendering, not deriving a week.",
    ),
    Allowed(
        "frontend/src/routes/student/StudentWeeklySurvey.tsx",
        "formats `EnrolledSection.next_window_opens_at` in the institution's timezone for "
        "FIX-01 item 4's dated sentence. Same instant-to-words job, one screen up.",
    ),
    Allowed(
        "frontend/src/components/PulseTrendChart.test.tsx",
        "is E4-08's narrower guard and holds these very reaches as data — the patterns it "
        "refuses and the lines it proves them against. A sweep that refused it would refuse "
        "the guard it widens.",
    ),
)


class RefusedShape(NamedTuple):
    """One way of reaching the clock, its one pattern, and its two controls.

    `certainly` and `certainly_not` are sources written here rather than quoted
    from `frontend/src/`: a control copied out of the tree being swept goes blind
    with it.

    **One pattern, not a tuple of them.** The control test proves a *shape*
    against its own sources, so a shape holding two patterns could carry a blind
    one indefinitely behind its sibling. A new mechanism is a new entry, with the
    two controls that entry owes.
    """

    name: str
    pattern: re.Pattern[str]
    certainly: tuple[str, ...]
    certainly_not: tuple[str, ...]


REFUSED = (
    RefusedShape(
        name="a constructed clock",
        pattern=re.compile(r"\bnew Date\b"),
        certainly=(
            "  const today = new Date();",
            "const startOfTerm = new Date(2026, 7, 17);",
        ),
        certainly_not=(
            " * file, and no `Date` is constructed or read anywhere in it — which",
            "const when = new Intl.DateTimeFormat(undefined, options);",
            "function courseWeekOf(point: TrendPoint): number {",
        ),
    ),
    RefusedShape(
        name="the clock read statically",
        pattern=re.compile(r"\bDate\."),
        certainly=(
            "  const now = Date.now();",
            "const parsed = Date.parse(instant);",
        ),
        certainly_not=(
            "  }).formatToParts(when);",
            "const formatter = new Intl.DateTimeFormat('en-US', { timeZone });",
            "  readonly closesAt?: string;",
        ),
    ),
    RefusedShape(
        name="the clock called without new",
        pattern=re.compile(r"\bDate\s*\("),
        certainly=(
            "  const stamp = Date(0);",
            "  const today = new Date();",
        ),
        certainly_not=(
            "  weekday: 'short',",
            "type DateLike = string;",
            "const shown = Intl.DateTimeFormat().format(when);",
        ),
    ),
)


def hits_for(shape: RefusedShape, text: str, where: str) -> list[str]:
    """Every line of `text` that trips one shape, named by line and by what matched."""
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = shape.pattern.search(line)
        if match is not None:
            found.append(f"{where}:{number}: {shape.name} — matched {match.group(0)!r}")
    return found


def reaches_in(text: str, where: str) -> list[str]:
    """Every refused shape this text trips, over all three.

    One function for the tree walk and for the negative controls, so a green over
    the tree comes from the same matcher the controls exercised
    (`docs/MISTAKES.md` entry 35).
    """
    return [line for shape in REFUSED for line in hits_for(shape, text, where)]


def frontend_sources() -> list[Path]:
    """Every TypeScript source under `frontend/src/`, tests and fixtures included.

    Included rather than excluded: a fixture module or a component test is still
    a place a clock read can be written down, and the day one lands there is the
    day the next component reads it. Two of the four allowances below are test
    files for exactly that reason — they are named, not exempted by being tests.
    """
    return sorted(
        path
        for path in FRONTEND_SOURCE.rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    )


def test_no_frontend_source_reaches_the_clock_outside_the_named_files() -> None:
    """SPEC §2.2's week axes are the server's, so nothing in the client asks what day it is.

    **The mutations this kills**, each of which renders a plausible report and
    passes every other test in this ticket: a term-week sub-label computed from
    today's date and a start offset; a "current week" derived from the clock
    instead of taken from `week.course_week`; a published-week list filled in
    from a calendar rather than taken from the API; and a timestamp rendered
    beside a comment, which SPEC §4 forbids outright and which needs a clock to
    format.

    **The near misses it must survive**, all of them controls beside this test:
    an instant the server sent, formatted for a reader through `Intl`; the
    sentence "no `Date` is constructed" written in a file's own documentation;
    and a `closesAt` prop, which names an instant without reading one.

    **The canary, first.** The walk has to have read the two files E4-11 names by
    name. A sweep over an empty file list is silent about everything, and its
    silence is what this test would otherwise report as compliance.
    """
    read = frontend_sources()
    relative = {str(path.relative_to(REPO_ROOT)) for path in read}
    missing = sorted(name for name in FILES_THE_WALK_MUST_FIND if name not in relative)
    assert not missing, (
        f"The walk over {FRONTEND_SOURCE} did not read {missing}; it read {len(read)} files. Both "
        "are named in E4-11's own text as files this ticket touches, so their absence means this "
        "sweep is reading somewhere else — and a judgement made over nothing is silent about "
        "everything."
    )

    allowed = {entry.path for entry in MAY_READ_THE_CLOCK}
    findings: list[str] = []
    for path in read:
        where = str(path.relative_to(REPO_ROOT))
        if where in allowed:
            continue
        findings.extend(reaches_in(path.read_text(encoding="utf-8"), where))

    assert not findings, (
        "These lines under `frontend/src/` reach the machine's clock:\n\n"
        + "\n".join(findings)
        + "\n\nSPEC §2.2 puts both week axes on the report payload precisely so that no client "
        "computes one, and every such computation needs today's date. A file that genuinely has "
        "to turn an instant the server sent into words a reader reads belongs in "
        "`MAY_READ_THE_CLOCK` in this module, with the sentence saying which instant and why — "
        "and adding it there is a decision made out loud, which is the point. Loosening a "
        "pattern to make a red go away gives back the guarantee.\n\n"
        "The files that may, today:\n"
        + "\n".join(f"- {entry.path}: {entry.why}" for entry in MAY_READ_THE_CLOCK)
    )


def test_every_file_allowed_to_read_the_clock_still_does() -> None:
    """The allowance is exact, so it cannot quietly become a hole.

    An entry for a file that no longer reaches the clock is an entry that would
    cover the day it starts again, and the sweep above would say nothing. This is
    the other half of `docs/MISTAKES.md` entry 35's rule applied to the allowance
    rather than to the patterns: an exemption that exempts nothing is an
    exemption nobody is checking.

    It also fails when an allowed file is deleted or renamed, which is the moment
    to decide whether the allowance travelled with it.

    Asserts nothing about what ships, so it carries no `invariant` marker.
    """
    idle: dict[str, str] = {}
    for entry in MAY_READ_THE_CLOCK:
        path = REPO_ROOT / entry.path
        if not path.is_file():
            idle[entry.path] = "the file is not there"
            continue
        if not reaches_in(path.read_text(encoding="utf-8"), entry.path):
            idle[entry.path] = "the file reaches the clock nowhere"

    assert not idle, (
        f"These entries of `MAY_READ_THE_CLOCK` are not covering anything: {idle}.\n\n"
        "An allowance for a file that does not reach the clock is a hole waiting for the day it "
        "does. If the reach was removed deliberately, remove the entry in the same change; if "
        "the file moved, move the entry with it."
    )


def test_each_refused_shape_finds_a_source_that_certainly_carries_it() -> None:
    """The instrument, both ways: every shape is proven visible before its silence counts.

    `docs/MISTAKES.md` entry 35: "When a guard enumerates mechanisms, require it
    to *find* each one on a subject that certainly has it, as a control. A guard
    that only ever reports absence cannot tell you which mechanisms it can see."

    **The mutations this kills.** A pattern that compiles and matches nothing —
    an escaped word boundary, a character class that swallowed its own subject.
    And the opposite: a pattern broad enough to fire on `Intl.DateTimeFormat`, on
    a `closesAt` prop, or on a file's own sentence about not constructing a
    `Date` — each of which makes the sweep above red against correct code and
    gets it loosened until it sees nothing.

    Asserts nothing about what ships, so it carries no `invariant` marker: a red
    here means this module is broken, not that the frontend reads a clock.
    """
    blind = {
        shape.name: [source for source in shape.certainly if not hits_for(shape, source, "control")]
        for shape in REFUSED
    }
    unseen = {name: sources for name, sources in blind.items() if sources}
    assert not unseen, (
        f"These refused shapes did not find sources that certainly carry them: {unseen}.\n\n"
        "Each of those lines reaches the clock, written out. A shape that cannot see its own "
        "control sees nothing in `frontend/src/` either, and the sweep beside this test would "
        "report a clean tree whatever the tree held."
    )

    firing = {
        source: reaches_in(source, "control")
        for shape in REFUSED
        for source in shape.certainly_not
        if reaches_in(source, "control")
    }
    assert not firing, (
        f"These sources reach no clock and were refused anyway: {firing}.\n\n"
        "Every one of them is something these surfaces legitimately do — format an instant the "
        "server sent, name one in a prop, or document that no `Date` is constructed. A sweep that "
        "refuses them is red against correct code, and the next person to meet it will widen it "
        "until it is silent, which is how the guarantee is lost."
    )
