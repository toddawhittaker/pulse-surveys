"""E5.1-03 criterion 2 — no sentence is left behind as a literal in `api/deps.py`.

The ticket moves every sentence the four entry pages serve, and the instructor
gate's refusal, into the copy registry, where SPEC §4.1 items 4 and 5 are swept
over them by
`tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`.
Moving the strings is half of the criterion. The other half is that nothing is
left behind, and that the next sentence somebody writes into
`backend/app/api/deps.py` is refused here rather than shipped past the
inventory. The frontend has had that guard since E4-12
(`tests/unit/test_the_component_and_route_trees_ship_no_ungoverned_string.py`);
this is its backend counterpart over the one module the ticket names.

**What counts as a sentence (ruling R3 of the work order).** A `str` constant —
including each literal part of an f-string — that is not a docstring and that
contains three or more letter-words in a row separated by single spaces. A
letter-word stands on its own: the `px` of `2px` and the `serif` of
`sans-serif` are not words here. A
docstring is the first statement of a module, a class or a function; prose
explaining code is not something a person is served, and a sweep that punished
it would be training the next reader to delete the explanation.

**One exemption, by shape.** The arguments of a `raise` whose exception is not
`HTTPException`. FastAPI answers such an exception with a generic 500, so its
words reach a log and never a person. The exemption is read off the syntax of
the `raise` statement itself: an `HTTPException` built in one statement and
raised in another is swept, which is the safe direction to be wrong in.

**Disclosed limits, stated rather than discovered** (`docs/MISTAKES.md` entry
14):

  - **a two-word string is not a sentence here.** The door template's font
    stacks (`'Schibsted Grotesk'`, `'Helvetica Neue'`) and its `<title>` are two
    words each, and the rule must leave them alone. A two-word heading written
    as a literal would pass this sweep; the inventory's canaries and the entry
    page test are what notice a page whose words are not in the registry;
  - **a sentence assembled at runtime** from fragments of fewer than three
    words each, or joined by something other than a single space — two spaces,
    a newline — is invisible to the pattern;
  - **modules other than `deps.py`.** The ticket names that module; `api/dev.py`
    serves a development-only page and the work order leaves the other `api/`
    modules out of this ticket deliberately.

**The controls come first, and every sample is written in this module.** None
is copied out of `deps.py` (`docs/MISTAKES.md` entry 19): a canary taken from
the file being swept goes blind with it. Each allowance is shown leaving a near
miss alone and each refusal is shown naming a planted offender, so a scanner
that has gone blind or gone wild says so before the real file is read
(`docs/MISTAKES.md` entry 3). **A red in a control means these tests are
broken, not the code.**

**Which failure a red is, before E5.1-03 lands.** The controls are green on
today's tree. The rule over `deps.py` is red on an assertion that lists the
sentences the module still holds — the entry pages' copy and the instructor
gate's refusal — by line.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The one module criterion 2 names.
DEPS_PATH = REPO_ROOT / "backend" / "app" / "api" / "deps.py"

# Three or more runs of ASCII letters, each separated from the next by exactly
# one space. Written from R3's words rather than from anything in `deps.py`.
#
# **Each run has to be a word on its own**, which is what the two lookarounds
# say: not the tail of `2px`, and not one half of `sans-serif`. Without them
# `outline: 2px solid var(...)` reads as the three words `px solid var`, and a
# focus rule is a finding. The stylesheet sample below carries exactly that
# declaration so the boundary is exercised rather than assumed.
SENTENCE = re.compile(r"(?<![\w-])[A-Za-z]+(?: [A-Za-z]+){2,}(?![\w-])")

# The one exception whose message *is* served: FastAPI turns its `detail` into
# the response body. Matched on the called name's last segment, so
# `HTTPException(...)` and `fastapi.HTTPException(...)` are the same thing here.
SERVED_EXCEPTION = "HTTPException"

# ---------------------------------------------------------------------------
# The samples. Every sentence below is written for this module and for nothing
# else; none is a sentence the product ships.
# ---------------------------------------------------------------------------

A_PLANTED_SENTENCE = "The planted sentence must be named by the sweep."

A_MODULE_CONSTANT = "\n".join(
    [
        '"""A sample module."""',
        "",
        f"NOTICE = {A_PLANTED_SENTENCE!r}",
        "",
    ]
)

# The same sentence in a served refusal, and the same sentence in a refusal
# FastAPI answers with a bare 500. The two differ in the exception's name and in
# nothing else, which is what makes them a pair.
A_SERVED_REFUSAL = "\n".join(
    [
        '"""A sample module."""',
        "",
        "from fastapi import HTTPException",
        "",
        "",
        "def refuse() -> None:",
        '    """Refuse the caller."""',
        f"    raise HTTPException(status_code=401, detail={A_PLANTED_SENTENCE!r})",
        "",
    ]
)

AN_UNSERVED_REFUSAL = "\n".join(
    [
        '"""A sample module."""',
        "",
        "",
        "def refuse() -> None:",
        '    """Refuse the caller."""',
        f"    raise RuntimeError({A_PLANTED_SENTENCE!r})",
        "",
    ]
)

# A docstring holding the sentence, and the same sentence as a bare expression
# that is *not* the first statement — which is not a docstring, so it is named.
A_DOCSTRING = "\n".join(
    [
        f'"""{A_PLANTED_SENTENCE}"""',
        "",
        "",
        "class Sample:",
        f'    """{A_PLANTED_SENTENCE}"""',
        "",
        "",
        "def sample() -> None:",
        f'    """{A_PLANTED_SENTENCE}"""',
        "",
    ]
)

A_STRING_THAT_IS_NOT_A_DOCSTRING = "\n".join(
    [
        "def sample() -> None:",
        "    value = 1",
        f"    {A_PLANTED_SENTENCE!r}",
        "",
    ]
)

# A page template's non-sentences: a stylesheet carrying both font stacks and a
# focus ring, a testid, a cookie name, a header value and a two-word title. None
# is a sentence and all of them must be left alone.
A_STYLESHEET_AND_ITS_NEIGHBOURS = "\n".join(
    [
        '"""A sample module."""',
        "",
        "STYLE = (",
        "    \":root { --font-body: 'Schibsted Grotesk', 'Helvetica Neue', sans-serif; }\"",
        '    " body { font-family: var(--font-body); margin: 0; }"',
        '    " a:focus-visible { outline: 2px solid var(--marigold-deep); }"',
        ")",
        'TESTID = "sample-entry-refused"',
        'COOKIE = "sample_login"',
        'CHALLENGE = "Bearer"',
        'TITLE = "<title>Pulse Surveys</title>"',
        "",
    ]
)

# The other side of the two-word boundary: the same title with a third word.
A_THREE_WORD_TITLE = "\n".join(
    [
        '"""A sample module."""',
        "",
        'TITLE = "<title>Pulse Surveys Online</title>"',
        "",
    ]
)

# A sentence in the literal part of an f-string, and an f-string whose literal
# parts carry no words at all.
AN_F_STRING_SENTENCE = "\n".join(
    [
        "def greet(name: str) -> str:",
        '    return f"Hello {name}, your session has ended."',
        "",
    ]
)

AN_F_STRING_ADDRESS = "\n".join(
    [
        "def origin(scheme: str, host: str) -> str:",
        '    return f"{scheme}://{host}"',
        "",
    ]
)


# ---------------------------------------------------------------------------
# The scanner.
# ---------------------------------------------------------------------------


class Finding(NamedTuple):
    """One sentence-shaped string: where it is, the whole string, and the run that matched."""

    line: int
    text: str
    sentence: str


class Scan(NamedTuple):
    """What one scan read: how many string constants it examined, and what it found."""

    examined: int
    findings: list[Finding]


def docstring_constants(tree: ast.AST) -> set[int]:
    """The identity of every string node that is a docstring rather than a value."""
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


def called_name(function: ast.expr) -> str | None:
    """The last segment of the name a call is made through, or `None` for anything else."""
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def unserved_raise_constants(tree: ast.AST) -> set[int]:
    """Every string constant inside the call a `raise` makes, unless it raises `HTTPException`.

    Read off the `raise` statement's own syntax: `raise RuntimeError("...")` is
    exempt and `raise HTTPException(detail="...")` is not. An exception built in
    one statement and raised in another is not exempt either way, which costs a
    false finding at worst and never a missed one.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if called_name(node.exc.func) == SERVED_EXCEPTION:
            continue
        for inner in ast.walk(node.exc):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                found.add(id(inner))
    return found


def scan(source: str, filename: str) -> Scan:
    """Every sentence-shaped string constant in `source` that is not a docstring or exempt.

    The literal parts of an f-string are `ast.Constant` nodes inside the
    `JoinedStr`, so `ast.walk` reaches each of them on its own — which is how a
    sentence in an f-string is found without any special case.
    """
    tree = ast.parse(source, filename=filename)
    skipped = docstring_constants(tree) | unserved_raise_constants(tree)
    examined = 0
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        examined += 1
        if id(node) in skipped:
            continue
        match = SENTENCE.search(node.value)
        if match is not None:
            findings.append(Finding(getattr(node, "lineno", 0), node.value, match.group(0)))
    return Scan(examined, sorted(findings))


def sentences_in(source: str) -> list[str]:
    """The matched runs a scan of `source` reports, for a control's message."""
    return [finding.sentence for finding in scan(source, "a sample module").findings]


def require_the_deps_module() -> str:
    """`backend/app/api/deps.py`'s source, or a failure naming where it was looked for."""
    if not DEPS_PATH.is_file():
        pytest.fail(
            f"{DEPS_PATH.relative_to(REPO_ROOT)} does not exist, so this sweep would read nothing "
            "and report a clean module. E1-13 put the role gates and the door pages there, and "
            "E5.1-03's criterion 2 is a statement about that file."
        )
    return DEPS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Controls. Green on today's tree; a red here means this module is broken.
# ---------------------------------------------------------------------------


def test_a_sentence_in_a_module_level_constant_is_named() -> None:
    """The plainest offender: a sentence assigned to a constant.

    **The mutation it kills:** a scanner that reads only call arguments, which
    is green over the shape the entry pages' copy has today. **Its near miss**
    is the docstring control below, where the same words are prose. **A red
    here means this module is broken, not that the code is.**
    """
    found = sentences_in(A_MODULE_CONSTANT)
    assert found, (
        f"The scanner found nothing in a module whose one constant is {A_PLANTED_SENTENCE!r}. "
        "A scanner that cannot see that cannot see the sentences criterion 2 is about."
    )


def test_a_sentence_in_a_served_refusal_is_named() -> None:
    """`raise HTTPException(detail=...)` is served to a person, so its sentence is named.

    **The mutation it kills:** the exemption widened to every `raise`, which
    would excuse exactly the refusal the instructor gate answers with. **Its
    pair** is the next control: the same sentence, the same shape, a different
    exception, left alone. **A red here means this module is broken.**
    """
    found = sentences_in(A_SERVED_REFUSAL)
    assert found, (
        "The scanner left alone a sentence passed as an `HTTPException`'s `detail`. FastAPI "
        "serves that detail as the response body, so it is copy a person reads."
    )


def test_a_sentence_in_an_unserved_refusal_is_left_alone() -> None:
    """`raise RuntimeError("...")` reaches a log and never a person, so it is exempt.

    **The mutation it kills:** a scanner with no exemption, which would be red
    against a correct `deps.py` on the one `RuntimeError` the work order names
    and would be deleted rather than fixed. **Its pair** is the control above.
    **A red here means this module is broken.**
    """
    found = sentences_in(AN_UNSERVED_REFUSAL)
    assert found == [], (
        f"The scanner named {found} in a `raise RuntimeError(...)`. FastAPI answers an exception "
        "that is not an `HTTPException` with a generic 500, so these words are never served."
    )


def test_a_docstring_is_left_alone_and_the_same_words_elsewhere_are_named() -> None:
    """Docstrings at module, class and function level are prose; a later bare string is not.

    **The mutation it kills:** docstrings swept as copy, which would redden
    every module that explains itself; and, in the other direction, a
    "docstring" rule that skips every bare string expression, which excuses a
    sentence anywhere in a body. **A red here means this module is broken.**
    """
    in_docstrings = sentences_in(A_DOCSTRING)
    assert in_docstrings == [], (
        f"The scanner named {in_docstrings} in three docstrings. The first statement of a module, "
        "a class or a function is documentation, and the work order's rule leaves it alone."
    )
    elsewhere = sentences_in(A_STRING_THAT_IS_NOT_A_DOCSTRING)
    assert elsewhere, (
        "The scanner left alone a bare string that is the second statement of a function. That is "
        "not a docstring, and a rule that skipped it would skip a sentence anywhere in a body."
    )


def test_a_stylesheet_a_testid_and_a_two_word_title_are_left_alone() -> None:
    """The door template's non-sentences pass: font stacks, a focus rule, a testid, a title.

    **The mutation it kills:** a sentence rule that counts two words, or that
    reads a CSS declaration as words, which is red against the door template on
    the day this lands. **A red here means this module is broken.**
    """
    found = sentences_in(A_STYLESHEET_AND_ITS_NEIGHBOURS)
    assert found == [], (
        f"The scanner named {found} in a stylesheet, a testid, a cookie name, a challenge and a "
        "two-word title. None of those is a sentence; the rule is three letter-words in a row."
    )


def test_a_three_word_title_is_named() -> None:
    """The other side of the two-word boundary: one more word, and it is a sentence.

    **The mutation it kills:** the threshold drifting to four words, which
    passes the control above and lets every three-word heading through. **A red
    here means this module is broken.**
    """
    found = sentences_in(A_THREE_WORD_TITLE)
    assert found, (
        "The scanner left alone a title of three letter-words. R3's rule is three or more, so the "
        "boundary is between this sample and the two-word title above."
    )


def test_a_sentence_in_an_f_string_part_is_named() -> None:
    """The canary: a sentence in an f-string's literal part, which a naive walk can miss.

    **The mutation it kills:** a scanner that reads only plain constants, or that
    skips a `JoinedStr`, which is blind to every interpolated refusal. **Its near
    miss** is an f-string whose literal parts carry no words — an address — and
    it must be left alone. **A red here means this module is broken.**
    """
    found = sentences_in(AN_F_STRING_SENTENCE)
    assert found, (
        'The scanner left alone `f"Hello {name}, your session has ended."`. The literal part '
        "after the placeholder is a sentence a person reads."
    )
    address = sentences_in(AN_F_STRING_ADDRESS)
    assert address == [], f"The scanner named {address} in an f-string that builds an address."


# ---------------------------------------------------------------------------
# The rule over the real module.
# ---------------------------------------------------------------------------


def test_api_deps_holds_no_sentence_outside_the_copy_registry() -> None:
    """Criterion 2: the ungoverned-sentence sweep covers `api/deps.py` and finds nothing.

    Every sentence the entry pages serve, and the instructor gate's 401, is a
    `CopyEntry` after E5.1-03, read by the items 4 and 5 sweep. A sentence still
    written as a literal here is one that sweep never reads: a forbidden word in
    it ships with the inventory green.

    **The mutation it kills:** any one sentence left in `deps.py` as a literal —
    a heading the move missed, `NOT_AN_INSTRUCTOR` kept beside its registry entry,
    a new refusal written inline later. **The near misses it spares** are the
    controls above: docstrings, the one `RuntimeError`, the template's styles and
    its two-word title.

    **The scan is required to have read something first** (`docs/MISTAKES.md`
    entry 3): a scan that examined no string constants reports a clean module
    whatever the module holds.
    """
    source = require_the_deps_module()
    result = scan(source, str(DEPS_PATH))

    assert result.examined > 0, (
        f"The scan of {DEPS_PATH.relative_to(REPO_ROOT)} examined no string constants at all, so "
        "its silence below would mean nothing. That module certainly holds strings — its cookie "
        "names, its testids, its template — so the scanner has gone blind."
    )
    assert not result.findings, (
        f"{DEPS_PATH.relative_to(REPO_ROOT)} still holds these sentences as literals:\n"
        + "\n".join(f"  line {f.line}: {f.text!r}" for f in result.findings)
        + "\n\nEach is served to a person and swept by nothing. Move it into a `CopyEntry` under a "
        "governed prefix — `app/copy/entry.py` for the entry pages, `app/copy/instructor_report.py` "
        "for the instructor gate — and serve its `.text`. A `raise` of anything but "
        "`HTTPException` is exempt, because FastAPI never serves its words."
    )
