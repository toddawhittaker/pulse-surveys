"""No frontend test is disabled in place — the boundary review's finding about silent retirement.

E4-16 gave this repository a component-test runner and made a red mean stop, and
E4-08 through E4-12 put a growing share of the report's behaviour behind it. Some
of that behaviour is §4.1's: what a small-N week renders, what a released comment
may show, which words a surface may use. A Python suite cannot assert any of it —
it is React rendering — so the component tests *are* the assertion, and an
assertion that can be switched off in place is one nobody is holding.

`vitest` offers three ways to leave a test in the file and stop running it:
`.skip`, `.todo` and the `x`-prefixed forms (`xit`, `xdescribe`). Every one of
them is invisible in a green run — the runner reports the file, reports a count,
and says nothing an eye scanning CI would catch. This sweep is what says it.

**Fail closed, naming the file and the line.** A marker found is a failure whose
message is the offending line, so the repair is a decision somebody makes on the
record rather than a line that slid past review.

**What this does NOT guarantee, and the gap is real.** It catches a test that is
*disabled*. It does not catch a test that is **deleted**, **renamed into
irrelevance**, or **emptied of its assertions** — each of which retires the same
behaviour with no marker to find, and each of which leaves a green suite that
asserts less than it did. There is no count floor here and no inventory of which
component tests are confidentiality-bearing, so nothing in this file would notice
`PulseTrendChart.test.tsx` losing its small-N case tomorrow. That class of silent
retirement is **carried** rather than closed, and it is the same shape as the
carried denial-module entry on the §4.1 pass having no collection floor. This
module closes the half that is mechanically checkable and states the half that is
not, rather than reading as though it closed both.

It also does not judge `.only`, deliberately. A committed `.only` silently retires
every *other* test in its file, which is the same hazard one level out — but
refusing it is a rule about a local development habit rather than about a
confidentiality assertion, and adding it here would mean this sweep failing for a
reason unrelated to what it is named for. It is named here so the next reader knows
it was considered.

**E5-14 extends it to `tests/e2e/**/*.spec.ts`** and adds Playwright's
`test.fixme(` and `test.fail(` beside the forms above (`test.skip(` was already
matched): the end-to-end student-seat proof of §4.1 item 1,
`student-benchmark-exclusion.spec.ts`, could be switched off in place exactly as
a component test could, and nothing said so.

**Marked `invariant`**, which puts this module in CI's isolated §4.1 pass, where a
skip or an empty collection is itself a failure — which is the same property this
sweep asserts of the frontend suite, applied to the sweep. §4.1 items 1, 3 and 5
are the ones with rendering-side assertions today.

**The sweep is controlled in both directions** (`docs/MISTAKES.md` entries 3 and
35). A pattern searched against a tree has to be run against the text it claims to
catch *and* against the text it claims to allow, and it needs a canary saying it
read anything at all — the two control tests below are that, and the tree sweep
asserts it found test files before it reports none of them offending.
"""

import re
from pathlib import Path

import pytest
from fixtures.component_strings import (
    FRONTEND_SOURCE_ROOT,
    every_source_file,
    is_test_module,
)

pytestmark = pytest.mark.invariant

# The disabling forms `vitest` accepts, as they are written in a test file.
#
# **Anchored on the call rather than searched for as words.** A bare search for
# `.skip` matches a sentence in a comment, a property on an object and a string in
# a fixture, and a sweep that fails on prose gets widened or deleted rather than
# obeyed (`docs/MISTAKES.md` entry 43 is this repository's record of exactly that).
# Each pattern here requires a runner name, the disabling form, and the opening
# parenthesis of a call.
DISABLED_FORMS = (
    # `it.skip(`, `test.todo(`, `describe.skip(`, and the same three with `.failing`
    # — plus Playwright's `test.fixme(` and `test.fail(` (E5-14), which leave a test
    # in a spec file and stop it asserting anything. `test.skip(` and
    # `test.describe.skip(` / `.fixme(` are covered by the same alternation, because
    # `describe` is matched wherever it stands before the dot.
    re.compile(r"\b(?:it|test|describe|suite)\s*\.\s*(?:skip|todo|failing|fixme|fail)\s*\("),
    # `xit(`, `xtest(`, `xdescribe(`
    re.compile(r"\bx(?:it|test|describe)\s*\("),
)

# Text the sweep must catch, one line per pattern, written the way a real file
# writes them. The control that runs this is what proves the patterns are not
# blind.
CERTAINLY_DISABLED = (
    "  it.skip('hides raw comments below the threshold', () => {",
    "  test.todo('the release carries no week');",
    "  describe.skip('small-N', () => {",
    "  xit('renders the suppression notice', () => {",
    "  xdescribe('the trend pair', () => {",
    "  suite.failing('workload', () => {",
    # Playwright's forms, as `tests/e2e/*.spec.ts` would write them (E5-14).
    "test.fixme('a student seat serves no benchmark key', async ({ page }) => {",
    "  test.skip(browserName === 'webkit', 'no comparison DOM on webkit');",
    "test.describe.fixme('the student seat, two consecutive weeks', () => {",
    "test.describe.skip('the exit drive', () => {",
    "  test.fail();",
)

# Text the sweep must allow. Every line here contains a word one of the patterns
# is built around, in a place where it means something else — which is what tells
# a precise pattern from one that matches its own subject wherever it appears.
CERTAINLY_ALLOWED = (
    "  // We do not skip this case: a suppressed week still renders its summary.",
    "  const skip = comments.length === 0;",
    "  it('skips nothing', () => {",
    "  expect(rows.map((row) => row.skip)).toEqual([false, false]);",
    "  describe('the todo list component', () => {",
    "  test('xit is a word that appears in this sentence', () => {",
    # Near misses from the Playwright side (E5-14): the words in a title, a
    # locator, a variable and an ordinary `test.describe(` / `test.step(`.
    "test('fixme is only a word in this title', async ({ page }) => {",
    "  await page.getByRole('button', { name: 'Skip' }).click();",
    "  const fixme = false;",
    "test.describe('failing weeks are suppressed, not dropped', () => {",
    "  await test.step('the student reads a week that failed to close', async () => {",
)


def offenders_in(text: str) -> list[tuple[int, str]]:
    """Every disabled-test line in one file's text, as `(line number, the line)`.

    Line numbers are 1-based, so a failure message names a place an editor opens.
    """
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if any(pattern.search(line) for pattern in DISABLED_FORMS):
            found.append((number, line.strip()))
    return found


def frontend_test_modules() -> list[Path]:
    """Every test module under `frontend/src`, at any depth.

    `every_source_file` is the copy inventory's own walk and it descends symlinked
    directories, for the reason that module records: a walk that stops at a link
    reports a clean tree over whatever is behind it. The whole of `frontend/src` is
    swept rather than the component and route directories alone, because the
    enclosure of a closed set is where the set gets defeated
    (`docs/MISTAKES.md` entry 53) — a confidentiality-bearing test moved into a new
    directory tomorrow is still a test.
    """
    return [path for path in every_source_file((FRONTEND_SOURCE_ROOT,)) if is_test_module(path)]


def test_no_frontend_test_module_disables_a_test_in_place() -> None:
    """The sweep itself: no `.skip`, `.todo`, `xit` or `xdescribe` in a committed test.

    **The canary first** (`docs/MISTAKES.md` entry 3). An empty offender list from a
    walk that found no test modules is a green that means nothing at all, so the
    number of files read is asserted before the finding is reported. E4-16 shipped a
    proof test and E4-08 through E4-10 shipped six more, so a tree with none of them
    is a tree this sweep is not looking at.

    **The mutation this kills:** a confidentiality-bearing component test disabled
    in place rather than removed — `it.skip` added to the small-N case while the
    file, its name and its count of describes all stay put, and CI stays green.

    **The near miss it must survive:** the same test *deleted*. This sweep does not
    catch that and does not claim to; the module docstring says so, and the class is
    carried rather than closed.
    """
    modules = frontend_test_modules()
    assert modules, (
        f"No test module exists under {FRONTEND_SOURCE_ROOT}, so this sweep read nothing and its "
        "clean result is a statement about an empty set. E4-16 shipped the component-test runner "
        "and a proof test, and E4-08 through E4-10 shipped one beside each component they added — "
        "if none of them is here, either the tree has moved or this walk is looking in the wrong "
        "place."
    )

    findings: list[str] = []
    for path in modules:
        for number, line in offenders_in(path.read_text(encoding="utf8")):
            findings.append(f"{path.relative_to(FRONTEND_SOURCE_ROOT.parents[1])}:{number}: {line}")

    assert not findings, (
        "These frontend tests are in the tree and are not run:\n\n" + "\n".join(findings) + "\n\n"
        "`vitest` leaves a skipped or todo test in the file, reports it in the run, and exits zero, "
        "so a disabled assertion is invisible to everything that reads a green. Some of what these "
        "tests assert is SPEC §4.1's — what a small-N week renders, what a released comment may "
        "show, which words a surface may use — and no Python suite can assert any of it, because it "
        "is React rendering.\n\n"
        "A test that should not run should be **deleted**, in a change that says what behaviour "
        "stopped being asserted and why. Disabling it in place keeps the appearance of the "
        "assertion and none of it."
    )


# The end-to-end specs, and the one this sweep is required to find (E5-14, the
# boundary review's invariant-coverage LOW). `student-benchmark-exclusion.spec.ts`
# is SPEC §4.1 item 1's rendering-side proof — a student seat carries no benchmark
# key and draws no comparison DOM — and a `test.fixme(` added to it would leave
# the file, its name and CI's green all in place with the assertion gone.
REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_ROOT = REPO_ROOT / "tests" / "e2e"
E2E_SPEC_GLOB = "*.spec.ts"
A_CONFIDENTIALITY_SPEC = "student-benchmark-exclusion.spec.ts"


def e2e_spec_modules() -> list[Path]:
    """Every Playwright spec under `tests/e2e`, at any depth."""
    return sorted(E2E_ROOT.rglob(E2E_SPEC_GLOB))


def test_no_end_to_end_spec_disables_a_test_in_place() -> None:
    """The same sweep over `tests/e2e/**/*.spec.ts`, with Playwright's own disabling forms.

    Playwright leaves a `test.fixme(`, `test.skip(` or `test.fail(` test in the
    file, lists it in the report and exits zero — the same invisibility `vitest`
    has, on the suite that proves the student seat's half of §4.1 item 1 end to
    end.

    **The canary first** (`docs/MISTAKES.md` entry 3): the walk must find the
    student benchmark-exclusion spec by name, so an empty result from a walk
    pointed at the wrong directory is a red rather than a clean tree.

    **The mutation this kills:** `test.fixme(` or `test.skip(` added to a spec —
    in particular to `student-benchmark-exclusion.spec.ts` — while the file stays
    put. **The near miss it must survive:** the words themselves in a title, a
    locator or a variable, which the negative control below runs.
    """
    specs = e2e_spec_modules()
    names = {path.name for path in specs}
    assert A_CONFIDENTIALITY_SPEC in names, (
        f"The walk over {E2E_ROOT} found {sorted(names)} and not `{A_CONFIDENTIALITY_SPEC}`, the "
        "student seat's end-to-end proof that no benchmark reaches it. Either the walk is looking "
        "in the wrong place — and its clean result below means nothing — or that spec has moved, "
        "and `A_CONFIDENTIALITY_SPEC` is the line that follows it."
    )

    findings = [
        f"{path.relative_to(REPO_ROOT)}:{number}: {line}"
        for path in specs
        for number, line in offenders_in(path.read_text(encoding="utf8"))
    ]
    listed = "\n".join(findings)
    assert not findings, (
        f"These end-to-end tests are in the tree and are not run:\n\n{listed}\n\n"
        "Playwright reports a fixme'd or skipped test and exits zero, so a disabled assertion is "
        "invisible to everything that reads a green. A test that should not run is **deleted**, "
        "in a change that says what stopped being asserted and why."
    )


def test_the_sweep_catches_every_disabling_form_it_names() -> None:
    """The positive control. **A red here means this module is broken, not the frontend.**

    Every pattern is run against a line written the way a real test file writes it,
    one line per form, and each must be found. A pattern that had gone blind — a
    `vitest` spelling that changed, a regex edited until it matched nothing — would
    make the sweep above report a clean tree over any number of disabled tests, and
    nothing in that green would say so.

    Asserted per line rather than in aggregate, so a single form that stops matching
    names itself instead of hiding behind the five that still work.
    """
    for line in CERTAINLY_DISABLED:
        assert offenders_in(line), (
            f"The sweep does not recognise {line.strip()!r} as a disabled test. Every pattern in "
            "`DISABLED_FORMS` exists to catch one of these spellings, so a line here that is not "
            "caught is a hole in the sweep rather than an unusual way of writing a test."
        )


def test_the_sweep_allows_the_lines_that_only_look_like_disabled_tests() -> None:
    """The negative control. **A red here means this module is broken, not the frontend.**

    Each line carries a word one of the patterns is built around — `skip`, `todo`,
    `xit` — where it means something else: in a comment, as a variable, inside a
    test's own name. A sweep that failed on these would be failing on prose, and a
    sweep that fails on prose gets widened or deleted rather than obeyed, which is
    `docs/MISTAKES.md` entry 43's whole record.

    Together with the control above this is the pair entry 35 asks for: a guard has
    to be shown refusing as well as finding, or nothing says which of the two it can
    do.
    """
    for line in CERTAINLY_ALLOWED:
        assert not offenders_in(line), (
            f"The sweep reports {line.strip()!r} as a disabled test. It is not one — the word it "
            "matched on is in a comment, a variable name or a test's own title — and a sweep that "
            "fails on ordinary prose is one somebody widens or deletes instead of obeying."
        )
