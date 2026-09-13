"""E4-12 — SPEC §4.1 items 4 and 5 reach the strings a component writes for itself.

The carried entry this closes is `docs/tickets/e3/carried-from-e2.md`, "The
rendered student surface's strings rest on a convention nothing sweeps", recorded
at the E2 boundary and owned by E4:

> Today every user-visible string in the survey components resolves through the
> copy registry, so nothing is wrong — the convention is simply unguarded, and one
> ungoverned sentence in a component would ship past items 4 and 5 with the
> inventory green.
>
> **Done when:** a parse of the component and route trees refuses a user-visible
> string literal outside the copy modules, reusing the inventory's parser, with a
> planted offender and a near miss (a test id, a class name, a key literal) both
> proven.

`tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
asserts both items over the strings the copy modules publish. That is the whole of
their reach, and a sentence written into a component is outside it: the screen
reads correctly, the vocabulary sweep passes, and the confidentiality count never
sees the sentence. The machinery here is `tests/fixtures/component_strings.py`,
which reuses the inventory parser's escape and surrogate readers so that a padlock
spelled as an escape decodes the same way on both sides.

**Which tests carry the marker.** The two rules over the shipped trees are marked
`invariant` and their docstrings name the items they extend. The instruments — the
scanner's controls, the offender and near-miss samples, the walk's controls — are
not: they assert nothing about what ships, and CI's isolated §4.1 pass should fail
on a rule rather than on the thing that measures it. **A red in an unmarked test
here means this module is broken, not that the components are.** The marker is
per test, as the inventory module holds it; this module's name carries none of the
denial-name shapes
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
sweeps for, so no module-level marker is demanded of it, and
`scripts/ci/check_invariant_assertions.py` is satisfied because every marked test
below asserts in its own body.

**Every rule is run in both directions before the tree is read**
(`docs/MISTAKES.md` entry 3). A sweep for strings that are not there is satisfied
perfectly by a sweep that has gone blind, so each red is given a planted offender
it must name and each allowance is given a near miss it must leave alone. None of
the samples is copied out of a shipped file: a canary taken from the thing being
swept goes blind with it, and a test holding a shipped sentence reddens when
somebody rewords it (`docs/MISTAKES.md` entry 19).

**The near miss that decides the shape of the JSX rule** is
`frontend/src/components/WeekNav.tsx`'s arrow function, carried here verbatim
because it is the case a naive scan for text between `>` and `<` reads as the
sentence ` week `. It is in the near-miss table below, spelled exactly as it
ships.

**The disclosed limits, stated rather than discovered.** Each is a way a string
reaches a reader without this module seeing it, and none of them is closed here:

  - **a string assembled at runtime**, or reached through a variable. A sentence
    split across template fragments is out of scope by the same rule that lets a
    class list through;
  - **a single word.** The rule reads a sentence as whitespace plus letters after
    trimming, so a one-word literal in an expression position is allowed.
    Widening it would refuse every `'button'` and `'polite'` in the tree;
  - **files outside the two trees.** `frontend/src/lib/landings.ts` holds shipped
    sentences, and `main.tsx` and `router.tsx` are not swept either. That gap is
    recorded in `docs/tickets/e4/deferred.md` with an owner rather than left to be
    found;
  - **CSS `content:` properties**, which put text on a screen from a stylesheet;
  - **an SVG drawn as a lock or a shield**, which is item 5's iconography clause
    in a form no text sweep reaches. The inventory module discloses the same;
  - **a regular-expression literal**, whose characters the scanner reads as
    ordinary code. Where its braces do not balance the scanner loses track of the
    nesting and refuses the file by name, which is a loud failure rather than a
    quiet one, and the repair is to teach the scanner rather than to excuse the
    file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.component_strings import (
    EXCLUDED_SUPPORT_MODULES,
    SWEPT_DIRECTORIES,
    ComponentParseError,
    ComponentStringError,
    findings_in_source,
    findings_in_tree,
    import_specifiers,
    shipped_importers_of_support_modules,
    support_modules_that_do_not_exist,
    swept_files,
)
from fixtures.copy_inventory import collect_shipped_copy, display

# The keys the samples below look up. Written here rather than read from the
# inventory, so that the classifier's own controls do not move when the report's
# copy does — and so that the "a dotted literal the inventory does not hold is
# red" direction can be planted without touching anything real.
SAMPLE_KEYS = frozenset(
    {
        "instructor_report_page.heading",
        "instructor_report_page.comments_note",
        "instructor_report_page.participation_credit_note",
        "instructor_report_page.previous",
    }
)

A_SAMPLE_FILE = "a sample component"

# `frontend/src/components/WeekNav.tsx`, carried verbatim. The line is here
# because of what it looks like rather than because of what it does: between its
# `>` and its `<` sits the text ` week `, and a sweep reading JSX text as
# "whatever lies between a close angle and an open angle" reports this component
# as shipping a sentence. Copied whole, the line it starts on included, per
# `docs/MISTAKES.md` entry 3's rule about building canaries.
THE_WEEK_NAV_ARROW = "const previous = weeks.filter((week) => week < currentWeek).at(-1) ?? null;"


def a_component_rendering(markup: str) -> str:
    """A minimal component whose body is one element, for the JSX samples."""
    return "\n".join(
        [
            "import { copy } from '../copy/instructorReportPageCopy';",
            "",
            "export function Sample(): JSX.Element {",
            "  return (",
            f"    {markup}",
            "  );",
            "}",
            "",
        ]
    )


def a_component_declaring(statement: str) -> str:
    """A minimal component with one statement beside it, for the non-JSX samples."""
    return "\n".join(
        [
            "import { copy } from '../copy/instructorReportPageCopy';",
            "",
            statement,
            "",
            "export function Sample(): JSX.Element {",
            "  return <p>{copy('instructor_report_page.heading')}</p>;",
            "}",
            "",
        ]
    )


# ---------------------------------------------------------------------------
# A component written the way the shipped ones are: everything the convention
# permits, in one file, so that the accepted direction is exercised on the
# shapes that actually occur rather than on the two the rules mention.
# ---------------------------------------------------------------------------

A_CONVENTIONAL_COMPONENT = "\n".join(
    [
        "import { copy, fillCopy } from '../copy/instructorReportPageCopy';",
        "import './report.css';",
        "",
        "type Props = Readonly<{ week: number; total: number }>;",
        "",
        "const CLASSES: Record<string, string> = { note: 'pulse-report-note' };",
        "",
        "export function ReportNote({ week, total }: Props): JSX.Element {",
        f"  {THE_WEEK_NAV_ARROW}",
        "  const label = `pulse-week ${week > total ? 'over' : 'under'}`;",
        "  return (",
        '    <section className="pulse-report pulse-report-note" data-testid="report.trend">',
        "      {/* the note this page always renders */}",
        "      <h2 className={label}>{copy('instructor_report_page.heading')}</h2>",
        "      <p aria-label={copy('instructor_report_page.comments_note')}>",
        "        {fillCopy('instructor_report_page.participation_credit_note', {",
        "          week: String(week),",
        "        })}",
        "      </p>",
        '      <svg viewBox="0 0 24 24" aria-hidden="true" role="img">',
        '        <path d="M4 4 L20 20" fill="none" />',
        "      </svg>",
        "      <span>&middot;</span>",
        "      {previous === null ? null : (",
        "        <a href=\"#previous\">{copy('instructor_report_page.previous')}</a>",
        "      )}",
        "      {CLASSES.note === label ? null : <span>{' '}</span>}",
        "    </section>",
        "  );",
        "}",
        "",
    ]
)

# ---------------------------------------------------------------------------
# The offenders. Each is one way a user-visible string ships without a copy
# module, and each is written here rather than copied out of the tree.
# ---------------------------------------------------------------------------

OFFENDERS = {
    "a sentence rendered as JSX text": (
        a_component_rendering("<h1>Nothing is open at this address today.</h1>"),
        "Nothing is open at this address today.",
    ),
    "a sentence in an aria label": (
        a_component_rendering('<button aria-label="Close the weekly trend panel" />'),
        "Close the weekly trend panel",
    ),
    "a word in an alt attribute reached through braces": (
        a_component_rendering("<img alt={'Chart'} />"),
        "Chart",
    ),
    "a sentence in an exported constant": (
        a_component_declaring("export const EMPTY_STATE = 'Nothing is open this week.';"),
        "Nothing is open this week.",
    ),
    "a sentence returned by a helper": (
        a_component_declaring(
            "\n".join(
                [
                    "function fallback(): string {",
                    "  return 'Nothing is open this week.';",
                    "}",
                ]
            )
        ),
        "Nothing is open this week.",
    ),
    "a sentence spelled as a template literal": (
        a_component_declaring("const note = `Nothing to show for this week.`;"),
        "Nothing to show for this week.",
    ),
    "a copy key the inventory does not hold": (
        a_component_rendering("<p>{copy('instructor_report_page.headnig')}</p>"),
        "instructor_report_page.headnig",
    ),
    "a sentence in a title attribute": (
        a_component_rendering('<abbr title="Weeks counted from the start of the term" />'),
        "Weeks counted from the start of the term",
    ),
    "several words in an attribute this sweep cannot classify": (
        a_component_rendering('<div summary="Rows of weekly ratings" />'),
        "Rows of weekly ratings",
    ),
}

# ---------------------------------------------------------------------------
# The near misses. Each is legitimate and each is one a rule written slightly
# wider would refuse, so the sweep is unusable if any of them goes red.
# ---------------------------------------------------------------------------

NEAR_MISSES = {
    "a test id shaped like a copy key": a_component_rendering(
        '<section data-testid="report.trend" />'
    ),
    "several class names in one attribute": a_component_rendering(
        '<section className="pulse-report pulse-report-note" />'
    ),
    "a copy key the inventory holds": a_component_rendering(
        "<p>{copy('instructor_report_page.heading')}</p>"
    ),
    "the week navigation's arrow function": a_component_declaring(THE_WEEK_NAV_ARROW),
    "a type argument that looks like an element": a_component_declaring(
        "const rows: Record<string, string> = {};"
    ),
    "a generic call that looks like an element": a_component_declaring(
        "const width = measure<number>(320);"
    ),
    "an SVG view box and its path data": a_component_rendering(
        '<svg viewBox="0 0 24 24"><path d="M4 4 L20 20" /></svg>'
    ),
    "a spacing expression between elements": a_component_rendering("<span>{' '}</span>"),
    "an HTML entity standing in for punctuation": a_component_rendering("<span>&middot;</span>"),
    "a single code token in an expression": a_component_declaring("const politeness = 'polite';"),
    "a separator with no letters in it": a_component_declaring("const joined = ['a'].join(', ');"),
    "a conditional class list reached through braces": a_component_rendering(
        "<section className={ready ? 'pulse-a pulse-b' : 'pulse-c'} />"
    ),
    "an aria label reached through the copy module": a_component_rendering(
        "<p aria-label={copy('instructor_report_page.comments_note')} />"
    ),
}

# ---------------------------------------------------------------------------
# What the scanner must refuse outright rather than read past.
# ---------------------------------------------------------------------------

REFUSED = {
    "a string the line never closes": a_component_declaring("const broken = 'Nothing is open;"),
    "a block comment nobody closed": "\n".join(
        ["/* a header nobody closed", "export const A = 1;", ""]
    ),
    "an element whose children never end": "\n".join(
        ["export function Sample(): JSX.Element {", "  return (", "    <div>", ""]
    ),
    "a tag that never closes": "\n".join(
        ["export function Sample(): JSX.Element {", "  return <div className=", ""]
    ),
    "the low half of a surrogate pair on its own": a_component_declaring("const half = '\\uDD12';"),
}

A_SAMPLE_IMPORTING_EVERY_WAY = "\n".join(
    [
        "import { alpha } from './alpha';",
        "import './styles.css';",
        "import type { Beta } from '../beta';",
        "export { gamma } from './gamma';",
        "const delta = await import('./delta');",
        "const epsilon = require('./epsilon');",
        "const label = 'not a specifier at all';",
        "",
    ]
)


# ---------------------------------------------------------------------------
# The instrument: the classifier, both directions.
# ---------------------------------------------------------------------------


def test_the_sweep_leaves_a_component_written_the_way_the_shipped_ones_are() -> None:
    """The accepted direction, before any component is judged by this sweep.

    A sweep that refused the convention would be red over a correct tree and
    would be deleted rather than fixed, so the sample carries everything the
    convention permits at once: imports of a copy module and a stylesheet, a type
    alias, a class-name constant, a template literal built from a class and an
    expression, a copy lookup in JSX, a copy lookup inside an `aria-label`, a
    substitution call with an object argument, an SVG with its view box and path
    data, a `data-testid` shaped like a dotted key, an HTML entity, a spacing
    expression, a comment inside JSX, a conditional element, and the week
    navigation's arrow function.

    **The mutation it kills:** any rule widened until it refuses one of these —
    a JSX-text rule that reads `Record<string, string>` as markup, a dotted-key
    rule that runs over test ids, an attribute rule that refuses a class list.
    Each of those makes the rules below unsatisfiable rather than strict.
    **A red here means this module is broken, not that the components are.**
    """
    found = findings_in_source(
        A_CONVENTIONAL_COMPONENT, A_SAMPLE_FILE, jsx=True, known_keys=SAMPLE_KEYS
    )
    assert found == [], (
        "The sweep refused a component written the way the shipped ones are:\n"
        + "\n".join(f"  {finding}" for finding in found)
        + "\n\nEvery rule below is a statement about what this classifier returned, so a "
        "classifier that refuses the convention makes them a statement about nothing anybody "
        "could satisfy."
    )


@pytest.mark.parametrize("offender", sorted(OFFENDERS))
def test_the_sweep_names_each_planted_offender(offender: str) -> None:
    """The refused direction: every way a user-visible string ships ungoverned is loud.

    Each sample is a real way one would arrive: a sentence rendered as JSX text,
    which is what `UnknownAddress.tsx` was doing when this ticket was written; a
    sentence in an `aria-label` and in a `title`, which SPEC §4.1 item 1 names
    explicitly and no inventory can see; a word in an `alt` reached through
    braces, which is the same defect wearing the syntax that looks like the
    convention; a sentence in an exported constant and one returned from a
    helper, which is where a component's own strings collect; a sentence spelled
    as a template literal, which is how the first one comes back after the string
    rule lands; several words in an attribute this sweep has no rule for, which is
    the fail-closed direction; and a mistyped copy key, which renders nothing and
    passes every other rule here.

    Each assertion names the text the sweep must report, so a sweep that returned
    findings for a different reason — a refusal, another line — fails rather than
    passing on the count.

    **The mutations it kills:** any of the four red rules deleted or narrowed past
    its case. **A red here means this module is broken, not that the components
    are.**
    """
    source, expected = OFFENDERS[offender]
    found = findings_in_source(source, A_SAMPLE_FILE, jsx=True, known_keys=SAMPLE_KEYS)
    assert [finding.text.strip() for finding in found] == [expected], (
        f"Over a component holding {offender}, the sweep reported "
        f"{[finding.text for finding in found]} rather than the one finding {expected!r}.\n"
        "\n" + "\n".join(f"  {finding}" for finding in found)
    )


@pytest.mark.parametrize("near_miss", sorted(NEAR_MISSES))
def test_the_sweep_leaves_each_near_miss_alone(near_miss: str) -> None:
    """The other half of the pair, one sample at a time so a failure names which.

    The carried done-when asks for three of these by name — a test id, a class
    name, a key literal — and the rest are here because each is a shape a rule
    written slightly wider takes with it. The week navigation's arrow function is
    the one that decides how JSX text is read at all: between its `>` and its `<`
    lies ` week `, and every sweep that looks for text between angle brackets
    reports it as a shipped sentence.

    **The mutations it kills:** the JSX rule written as a search for `>text<`;
    the dotted-key rule run over attribute values; the attribute rule run over
    every attribute rather than over the ones a reader reads; a sentence rule
    that counts any letter rather than whitespace plus letters. **A red here
    means this module is broken, not that the components are.**
    """
    found = findings_in_source(
        NEAR_MISSES[near_miss], A_SAMPLE_FILE, jsx=True, known_keys=SAMPLE_KEYS
    )
    assert found == [], (
        f"The sweep refused {near_miss}, which is how this repository is meant to be written:\n"
        + "\n".join(f"  {finding}" for finding in found)
    )


@pytest.mark.parametrize("shape", sorted(REFUSED))
def test_the_scanner_refuses_a_file_it_cannot_read(shape: str) -> None:
    """Fail closed: a construct the scanner cannot resolve stops it, loudly.

    A scanner that skipped what it could not classify would report a clean tree
    over the strings it never understood, and every rule below would still be
    green (`docs/MISTAKES.md` entries 3 and 9). Each sample is a state that leaves
    the scanner unable to say what it is reading — a string running off its line,
    a comment nobody closed, JSX that never balances — and each of those makes
    every string after it read in the wrong state.

    **The mutation it kills:** a `continue` added for an unrecognised construct,
    or a string reader allowed to run past a newline to the next quote in the
    file. **A red here means this module is broken, not that the components
    are.**
    """
    with pytest.raises(ComponentParseError):
        findings_in_source(REFUSED[shape], A_SAMPLE_FILE, jsx=True, known_keys=SAMPLE_KEYS)


def test_a_file_the_scanner_cannot_read_is_a_finding_and_not_the_end_of_the_sweep(
    tmp_path: Path,
) -> None:
    """One unreadable file must not hide the rest of the tree behind it.

    The refusal above is the machinery's contract; over a whole tree it is turned
    into a finding against the one file, so that a run reports every offender it
    found as well as the file it could not read. A sweep that stopped at the first
    refusal would report one problem at a time, and the first one would be the
    only one anybody ever saw.

    **The mutation it kills:** the per-file `try` removed, so a single
    unterminated string turns the rule below into a single-file error message.
    **A red here means this module is broken, not that the components are.**
    """
    (tmp_path / "Unreadable.tsx").write_text(
        a_component_declaring("const broken = 'Nothing is open;"), encoding="utf-8"
    )
    (tmp_path / "Offending.tsx").write_text(
        a_component_rendering("<h1>Nothing is open at this address today.</h1>"), encoding="utf-8"
    )

    found = findings_in_tree(SAMPLE_KEYS, (tmp_path,), ())
    named = sorted(Path(finding.source).name for finding in found)
    assert named == ["Offending.tsx", "Unreadable.tsx"], (
        f"Over a tree holding one unreadable file and one offender, the sweep reported {named}. "
        "Both are findings: one is a sentence nothing governs, and the other is a file whose "
        "strings nobody has read."
    )


def test_the_walk_reaches_every_depth_and_leaves_the_test_modules_out(tmp_path: Path) -> None:
    """The accepted and refused directions of what gets judged at all.

    A walk that missed a subdirectory would report a clean tree over whatever is
    in it, which is the defect the copy collector shipped twice. A walk that
    judged test modules would refuse the sentences a test writes on purpose, and
    the rules would be deleted rather than fixed.

    **The mutation it kills:** a one-level glob, a single suffix, or a test
    exclusion that matches nothing. **A red here means this module is broken, not
    that the components are.**
    """
    (tmp_path / "WeekNav.tsx").write_text("export const A = 1;\n", encoding="utf-8")
    (tmp_path / "WeekNav.test.tsx").write_text("export const B = 2;\n", encoding="utf-8")
    (tmp_path / "instructor").mkdir()
    (tmp_path / "instructor" / "report.ts").write_text("export const C = 3;\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("not a source file", encoding="utf-8")

    judged = sorted(path.name for path in swept_files((tmp_path,), ()))
    assert judged == ["WeekNav.tsx", "report.ts"], (
        f"The walk judged {judged} over a tree holding a component, a nested route, a test module "
        "and a note."
    )


def test_the_walk_refuses_a_tree_with_no_source_file(tmp_path: Path) -> None:
    """An empty walk is a failure, never a pass.

    Every rule below is of the form "no swept file does X", and a walk that
    judged nothing satisfies all of them perfectly.

    **The mutation it kills:** returning an empty list instead of refusing, which
    turns both rules green over a tree with no components at all. **A red here
    means this module is broken, not that the components are.**
    """
    empty = tmp_path / "components"
    empty.mkdir()
    with pytest.raises(ComponentStringError):
        swept_files((empty,), ())


def test_the_import_reader_finds_every_shape_and_leaves_an_ordinary_string() -> None:
    """The instrument behind the support-module rule, both directions.

    The rule below says three modules are imported only by tests. A reader that
    found no imports at all would say exactly the same thing, in green, over a
    tree that imported them everywhere.

    **The mutation it kills:** a reader that knows only `from '...'`, which misses
    the side-effect import and both call forms. **A red here means this module is
    broken, not that the components are.**
    """
    found = import_specifiers(A_SAMPLE_IMPORTING_EVERY_WAY)
    assert found == [
        "./alpha",
        "./styles.css",
        "../beta",
        "./gamma",
        "./delta",
        "./epsilon",
    ], f"The reader found {found} over a file importing in every shape this repository uses."


def test_the_support_module_rule_names_a_shipped_importer_and_spares_a_test(
    tmp_path: Path,
) -> None:
    """The instrument behind the exclusion, planted in both directions.

    A test-support module is excused from the sweep on the strength of a claim:
    that nothing shipped imports it. The claim is checkable and this is the check,
    so it is run against a planted tree where a shipped file does import one — the
    state in which the exclusion is quietly wrong — and against one where only a
    test does.

    **The mutation it kills:** an importer reader that skips relative specifiers,
    or one that counts a test module as a shipped importer and so reports every
    excluded module as a violation. **A red here means this module is broken, not
    that the components are.**
    """
    support = tmp_path / "reportFixtures.ts"
    support.write_text("export const ROWS = [];\n", encoding="utf-8")
    (tmp_path / "Report.test.tsx").write_text(
        "import { ROWS } from './reportFixtures';\n", encoding="utf-8"
    )

    spared = shipped_importers_of_support_modules((tmp_path,), (support,))
    assert spared == {}, (
        f"With only a test module importing it, the reader reported {spared}. A support module "
        "imported by tests alone is the state the exclusion claims, and a reader that flags it "
        "makes the rule below unsatisfiable."
    )

    (tmp_path / "Report.tsx").write_text(
        "import { ROWS } from './reportFixtures';\n", encoding="utf-8"
    )
    caught = shipped_importers_of_support_modules((tmp_path,), (support,))
    assert caught == {display(support): [display(tmp_path / "Report.tsx")]}, (
        f"With a shipped component importing it, the reader reported {caught}. That is the moment "
        "the exclusion stops being true: the module's strings reach a screen and this sweep is "
        "excusing them."
    )


# ---------------------------------------------------------------------------
# The rules. Both are marked, and both docstrings name the items they extend.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_no_shipped_component_or_route_writes_a_user_visible_string_of_its_own() -> None:
    """SPEC §4.1 items 4 and 5, over the strings the inventory cannot see.

    > 4. Aggregate language counts sections, never instructors; "needs attention,"
    >    never "underperforming"; no ranking, no composite scores, and no
    >    score-sorting anywhere.
    > 5. Confidentiality copy appears exactly once per surface [...] in plain
    >    words, no shield or lock iconography.

    Both items are asserted over the copy inventory, and both stop at its edge. A
    sentence written into a component is swept by neither: item 4's vocabulary
    never reads it, and item 5 cannot count a confidentiality line it has never
    collected — a second promise rendered beside the first would leave the count
    at one. So the rule is that the component and route trees write no
    user-visible string of their own, and every string they do write resolves
    through a copy module the inventory reads.

    The keys are taken from the inventory itself, so the "a dotted literal the
    inventory does not hold is red" half is a statement about the collected
    inventory rather than about a list kept here.

    **The mutations it kills:** a sentence rendered as JSX text; a literal in an
    `aria-label`, `title`, `alt` or `placeholder`; a sentence in a constant or
    returned from a helper; and a copy key that resolves to nothing. **What makes
    it non-vacuous:** every planted offender in `OFFENDERS`, every near miss in
    `NEAR_MISSES`, the walk's refusal of an empty tree, and the assertion below
    that the sweep judged something and that the inventory handed it keys.
    """
    judged = swept_files()
    assert judged, (
        f"No file under {[display(directory) for directory in SWEPT_DIRECTORIES]} is judged by "
        "this sweep, so the rule passed over nothing."
    )

    known_keys = frozenset(string.key for string in collect_shipped_copy())
    assert known_keys, (
        "The copy inventory collected no keys, so every dotted literal in the trees would be "
        "reported as unknown and this rule would be red for the wrong reason."
    )

    found = findings_in_tree(known_keys)
    assert not found, "\n".join(
        [
            f"These strings ship from the component and route trees with no copy module "
            f"governing them ({len(found)} in {len({finding.source for finding in found})} "
            "files):",
            *(f"  {finding}" for finding in found),
            "",
            "SPEC §4.1 items 4 and 5 are asserted over the copy inventory, and a string written "
            "into a component is outside it: the vocabulary sweep never reads it, and item 5's "
            "count cannot see a second confidentiality sentence it never collected.",
            "",
            "The repair is to move the string into a copy module under `frontend/src/copy/` and "
            "render it through `copy()`, in the change that introduces it. Teaching this sweep to "
            "excuse the shape is not one of the answers; if a shape is genuinely not a "
            "user-visible string, it is classified in `tests/fixtures/component_strings.py` with "
            "a control in both directions.",
        ]
    )


@pytest.mark.invariant
def test_every_excluded_support_module_exists_and_ships_to_nobody() -> None:
    """The exclusions this sweep rests on are claims, and this is where they are checked.

    Three test-support modules live inside the swept trees and are excused from
    the rule above. Both halves of that excuse can rot without anything noticing.
    An exclusion naming a file that has been renamed excuses nothing and goes on
    reading like coverage (`docs/MISTAKES.md` entry 14 — an enumeration reported
    as an impossibility). And a support module a shipped component imports is not
    support at all: its strings reach a screen while this sweep steps over them.

    **The mutations it kills:** a support module renamed with the exclusion left
    pointing at the old name; and a component importing its own fixtures, which
    is how test data reaches production and how an excused module starts
    shipping. **What makes it non-vacuous:** the planted control above, which
    requires the reader to name a shipped importer and to spare a test one, and
    the existence assertion here, which requires the excluded set to be real
    files rather than three strings nobody has checked.
    """
    absent = support_modules_that_do_not_exist()
    assert not absent, (
        f"These modules are excluded from the sweep and do not exist: {absent}.\n"
        "\n"
        f"The excluded set is {[str(path) for path in EXCLUDED_SUPPORT_MODULES]}, relative to "
        "`frontend/src`. An exclusion for a file that is not there excuses nothing, and it reads "
        "exactly like an exclusion that is doing its job. If the module has been renamed, rename "
        "it here in the same change; if it has been deleted, delete the exclusion."
    )

    importers = shipped_importers_of_support_modules()
    assert not importers, (
        f"These test-support modules are imported by files that ship: {importers}.\n"
        "\n"
        "They are excused from the string sweep because nothing shipped imports them. A component "
        "that does import one puts its strings on a screen with SPEC §4.1 items 4 and 5 asserted "
        "over none of them, and this sweep steps over the module by name."
    )
