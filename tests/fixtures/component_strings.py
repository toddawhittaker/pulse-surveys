"""E4-12 — every string the component and route trees ship, read from the source.

The carried done-when this exists for is `docs/tickets/e3/carried-from-e2.md`,
"The rendered student surface's strings rest on a convention nothing sweeps":

> **Done when:** a parse of the component and route trees refuses a user-visible
> string literal outside the copy modules, reusing the inventory's parser, with a
> planted offender and a near miss (a test id, a class name, a key literal) both
> proven.

`tests/fixtures/copy_inventory.py` collects what the copy modules publish, and
SPEC §4.1 items 4 and 5 are asserted over that. A sentence written straight into a
component renders identically and is in no inventory, so both items pass over it
in green — the convention held by review alone until this module, and the E2
boundary recorded that as a gap rather than as a finding because nothing was
violating it yet. Something was by E4: `UnknownAddress.tsx` renders two sentences
as JSX text.

**The escape and surrogate readers are the inventory's own.** `read_escape`,
`is_surrogate` and `read_surrogate_pair` are imported rather than rewritten, so a
padlock spelled as a surrogate pair decodes to the same character here as it does
there. Two readers for one question is `docs/MISTAKES.md` entry 13, and the
inventory already paid for that lesson once.

**What this reads, and what it refuses.** A scanner walks each file and hands back
every piece of text a reader could ever see: string literals with the position
they were written in, template-literal fragments, and JSX text runs. Every piece
is then classified — allowed, or a finding naming the file, the line and the text.
A piece that fits no rule is a finding too, in the inventory parser's own
fail-closed style: a sweep that passed over what it could not classify would
report a clean tree over the strings it never understood, which is
`docs/MISTAKES.md` entries 3 and 9 in one move.

**A file the scanner cannot read is a finding, not an exception that stops the
sweep.** `scan_source` raises `ComponentParseError` when it meets a shape it
cannot resolve — an unterminated string, a block comment nobody closed, JSX that
never balances — and `findings_in_tree` turns that refusal into a finding against
that one file so the rest of the tree is still reported. The refusal is loud
either way; what this buys is that one unreadable file does not hide fifty real
ones behind it.

**`<` is JSX only in a `.tsx` file.** In `.ts`, `.mts` and `.cts` it is a
comparison or a type argument and never an element, so the scanner does not look
for JSX there at all. That removes the whole class of false readings that
`Record<string, string>` and `useState<Foo>(null)` would otherwise produce, and it
costs nothing: JSX cannot be written in those files.

**In a `.tsx` file the ambiguity is real, and it is settled by what comes before
the `<`.** An element may only begin where an expression may begin — after `(`,
`,`, `{`, `=`, `=>`, `&&`, `?`, `:`, `return` and their kin — while `a < b` and
`Map<K, V>` follow an identifier or a closing bracket. The near miss that decides
the shape of the rule is `frontend/src/components/WeekNav.tsx`'s
`(week) => week < currentWeek`, which a naive scan for text between `>` and `<`
reads as the JSX text ` week `.

**The disclosed limits, stated here rather than discovered later.** Each is a way
a user-visible string reaches a screen without this module seeing it:

  - a string assembled at runtime, or reached through a variable. A sentence
    split across template fragments — `` `Week ${n} of ${total}` `` — is three
    fragments none of which is sentence-shaped, and it is out of scope by the same
    rule that lets `` `pulse-bar ${state}` `` through;
  - a single word. The rule reads a sentence as whitespace plus letters, so a
    one-word literal in an expression position is allowed. Widening it to any
    letter-carrying literal would refuse every `'button'`, `'polite'` and
    `'en-US'` in the tree;
  - files outside the two trees. `frontend/src/lib/landings.ts` holds shipped
    sentences and is not swept here; `main.tsx` and `router.tsx` are not either.
    Both are recorded in `docs/tickets/e4/deferred.md` rather than left to be
    found;
  - CSS `content:` properties, which put text on a screen from a stylesheet;
  - imports are read by a regular expression rather than by the scanner, so the
    only import shapes recognised are `from '...'`, `import '...'`,
    `import('...')` and `require('...')`;
  - **a regular-expression literal is not recognised as one.** Its characters are
    read as ordinary code, which is harmless while its braces balance — the
    `/\\{(\\w+)\\}/g` in the copy modules' own `fillCopy` does — and which
    miscounts the nesting when they do not. The failure that produces is loud
    rather than silent: the scanner loses the frame it is in and refuses the file
    at the end, naming it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from fixtures.copy_inventory import (
    BACKTICK,
    HIGH_SURROGATES,
    LOW_SURROGATES,
    REPO_ROOT,
    STRAIGHT_QUOTES,
    CopyInventoryError,
    display,
    is_surrogate,
    read_escape,
    read_surrogate_pair,
)

FRONTEND_SOURCE_ROOT = REPO_ROOT / "frontend" / "src"

# The two trees the carried done-when names. Not `frontend/src` whole: the copy
# modules are the place strings are *supposed* to live, and `lib/` holds the
# landing sentences that are somebody else's deferral.
COMPONENT_DIRECTORY = FRONTEND_SOURCE_ROOT / "components"
ROUTE_DIRECTORY = FRONTEND_SOURCE_ROOT / "routes"
SWEPT_DIRECTORIES = (COMPONENT_DIRECTORY, ROUTE_DIRECTORY)

# The same family the copy collector reads, for the same reason: a module that
# changed suffix is the same module.
SOURCE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")

# JSX is only possible in `.tsx`. See the module docstring.
JSX_SUFFIX = ".tsx"

# Test modules are excluded because a test's strings are not shipped. The
# spelling is `.test.` anywhere in the filename, which is this repository's
# convention (`WeekNav.test.tsx`).
TEST_INFIX = ".test."

# The three test-support modules that live inside the swept trees and ship to
# nobody. Named one by one rather than matched by a pattern, because a pattern
# that excused `*Fixtures.ts` would excuse a component somebody named that way,
# and because each of these is a claim to be checked: the rule module requires
# every one of them to exist and to be imported only from excluded files. A
# shipped import of one of them is a finding — that is the moment the exclusion
# stops being true.
EXCLUDED_SUPPORT_MODULES = (
    Path("components") / "instructorReportCommentFixtures.ts",
    Path("components") / "instructorReportStats.fixtures.ts",
    Path("routes") / "instructor" / "instructorReportFixtures.ts",
)

# ---------------------------------------------------------------------------
# What a piece of text is, and where it was written.
# ---------------------------------------------------------------------------

STRING = "a string literal"
TEMPLATE = "a template literal fragment"
JSX_TEXT = "JSX text"

IMPORT = "a module specifier"
ATTRIBUTE = "a JSX attribute value"
EXPRESSION = "an expression"
CHILDREN = "the children of an element"


class Piece(NamedTuple):
    """One run of text a reader could see, with everything needed to judge it."""

    kind: str
    value: str
    line: int
    position: str
    attribute: str | None


class Finding(NamedTuple):
    """One string the sweep refuses, named the way a reader can act on."""

    source: str
    line: int
    text: str
    why: str

    def __str__(self) -> str:
        return f"{self.source}:{self.line}: {self.why}: {self.text!r}"


class ComponentStringError(CopyInventoryError):
    """The sweep cannot read a file, so nothing asserted over it would mean anything."""


class ComponentParseError(ComponentStringError):
    """A construct in a component the scanner cannot resolve."""


# ---------------------------------------------------------------------------
# The vocabulary of the classification.
# ---------------------------------------------------------------------------

# SPEC §4.1 item 1 names aria labels explicitly, and item 4's vocabulary reaches
# "tooltips, exports, or aria labels" in as many words. These are the attributes
# whose value a person reads or hears, so a literal in one of them is copy however
# short it is.
VISIBLE_ATTRIBUTES = (
    "aria-label",
    "aria-roledescription",
    "aria-valuetext",
    "alt",
    "placeholder",
    "title",
)

# Attributes whose value is legitimately several words. Everything else is allowed
# by the shape of its value rather than by its name — a single token with no
# internal whitespace is code wherever it sits — so this list stays short by
# construction instead of growing one attribute per review
# (`docs/mistakes/` — a closed-set guard is defeated one level out).
#
# `className` carries several classes; `aria-labelledby` and `aria-describedby`
# carry lists of ids, which is why item 4's own reach does not make them visible
# text; and the SVG geometry attributes carry path data whose commands are
# letters.
ATTRIBUTES_ALLOWED_TO_CARRY_SEVERAL_WORDS = (
    "aria-describedby",
    "aria-labelledby",
    "class",
    "classname",
    "d",
    "headers",
    "points",
    "preserveaspectratio",
    "srcset",
    "sizes",
    "style",
    "transform",
    "viewbox",
)

# `data-testid`, `data-week`, anything the tests hang on. Matched as a prefix
# because the set is open by design; the value is a token either way, so this
# only matters for the rare multi-word one.
DATA_ATTRIBUTE_PREFIX = "data-"

# A dotted copy key, as the inventory spells them: lowercase segments, each
# beginning with a letter. The leading-letter rule is what keeps `v1.0` and
# `2.5` out — a version or a number is not a key — and the underscore is in
# because `small_n.body` is one.
DOTTED_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")

# Where a string literal is a module specifier. Read off the code before it on
# its own line: `from` covers the ordinary form, the `export ... from` form and
# the multi-line one whose specifier sits after a `} from`; a line that is only
# the word `import` covers the side-effect import; and the two call forms cover
# the dynamic ones.
#
# **Not `^\\s*(?:import|export)\\s`**, which was the first spelling and was wrong
# in the direction that matters: it reads `export const EMPTY = 'Nothing is open
# this week.'` as an import and lets the sentence through. A rule that excuses a
# whole statement because of the word it starts with is the prefix-matched
# allowance the copy parser had to remove for the same reason.
IMPORT_POSITION = re.compile(r"\bfrom\s*$|^\s*import\s+$|(?:^|[\s(,=])(?:import|require)\s*\(\s*$")

# Every import specifier in a file, for the excluded-module rule. A regular
# expression rather than the scanner, because this question is also asked of the
# `*.test.tsx` files, and running the whole classifier over a tree it does not
# govern would turn a test file's own strings into refusals.
IMPORT_SPECIFIERS = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)(['"])([^'"\n]*)\1""",
    re.MULTILINE,
)

# An HTML entity, removed before JSX text is read for letters. `&nbsp;` and
# `&middot;` are punctuation a reader sees as a space and a dot; counting their
# letters would make every non-breaking space a shipped sentence.
HTML_ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")

LETTER = re.compile(r"[A-Za-z]")
INTERNAL_WHITESPACE = re.compile(r"\s")

# The name of a JSX element or attribute. Dots for `<Foo.Bar>`, colons for
# `xlink:href`, dashes for `data-testid` and `aria-label`.
JSX_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$.:-]*")

# The word before a `<` that says an expression may begin there. Without these a
# `return <div>` reads as a comparison, and every component's own markup would be
# invisible.
JSX_EXPRESSION_KEYWORDS = frozenset(
    {
        "return",
        "case",
        "default",
        "typeof",
        "instanceof",
        "in",
        "of",
        "await",
        "yield",
        "else",
        "do",
        "void",
        "delete",
        "new",
    }
)

# The characters after which an expression may begin. `>` is here for `=>`, which
# is how every element inside a `.map()` is reached.
EXPRESSION_OPENERS = "([{,;=+-*/%!&|?:<>~^"

# What may follow the `<` of an element: a name, a fragment, or a closing tag.
JSX_OPENERS = "_$>/"

IDENTIFIER_CHARACTERS = "_$"


def has_letters(text: str) -> bool:
    """Whether `text` carries a letter a reader would read as a word."""
    return bool(LETTER.search(text))


def is_sentence_shaped(text: str) -> bool:
    """Whether `text` is prose rather than a code token: whitespace plus letters, trimmed.

    The trim matters. `' '` and `'\\n'` are separators a component writes between
    elements; `'pulse-report-note'` is a class name; `'0 0 24 24'` is a view box.
    None of them is a sentence, and none of them carries both a letter and an
    internal space.
    """
    trimmed = text.strip()
    return bool(INTERNAL_WHITESPACE.search(trimmed)) and has_letters(trimmed)


def refusal(where: str, line: str, why: str) -> str:
    """The message every scanner refusal carries, in the inventory parser's shape."""
    return "\n".join(
        [
            f"{where} {why}:",
            f"  {line.rstrip()!r}",
            "",
            "This scanner refuses a construct it cannot resolve rather than skipping it. A sweep "
            "that skipped what it could not read would report a clean tree over the strings it "
            "never understood, and SPEC §4.1 items 4 and 5 would be asserted over less of the "
            "product than the run appears to say (`docs/MISTAKES.md` entries 3 and 9).",
            "",
            "If the shape above is legitimate, it is taught in "
            "`tests/fixtures/component_strings.py` in the same change that introduces it, with a "
            "control in both directions.",
        ]
    )


# ---------------------------------------------------------------------------
# The scanner.
# ---------------------------------------------------------------------------

CODE_FRAME = "code"
TAG_FRAME = "jsx tag"
CHILDREN_FRAME = "jsx children"
TEMPLATE_FRAME = "template literal"


@dataclass
class Frame:
    """One nesting level of the scan: code, a JSX tag, its children, or a template."""

    kind: str
    depth: int = 0
    attribute: str | None = None
    position: str = EXPRESSION
    buffer: list[str] = field(default_factory=list)
    opened_on: int = 0


def line_of(lines: list[str], number: int) -> str:
    """The text of one line, for a refusal message."""
    return lines[number - 1] if 0 < number <= len(lines) else ""


def read_quoted(text: str, index: int, where: str, line: str) -> tuple[str, int]:
    """The string literal beginning at `index`, decoded, and the index after it.

    Decoded through the inventory's own escape and surrogate readers, so that a
    padlock written as `\\u{1F512}` or as a surrogate pair arrives as the
    character a browser draws rather than as the characters of an escape.

    A literal the line does not close is refused rather than run on to the next
    quote in the file: reading across a newline is how one unterminated string
    silently swallows the code after it.
    """
    quote = text[index]
    read: list[str] = []
    position = index + 1
    while position < len(text):
        char = text[position]
        if char == "\n":
            break
        if char == "\\":
            decoded, position = read_escape(text, position, where, line)
            if is_surrogate(decoded, HIGH_SURROGATES):
                decoded, position = read_surrogate_pair(decoded, text, position, where, line)
            elif is_surrogate(decoded, LOW_SURROGATES):
                raise ComponentParseError(
                    refusal(
                        where,
                        line,
                        "carries the low half of a surrogate pair with no high half before it",
                    )
                )
            read.append(decoded)
            continue
        if char == quote:
            return "".join(read), position + 1
        read.append(char)
        position += 1
    raise ComponentParseError(refusal(where, line, "opens a string that the line never closes"))


def previous_significant(text: str, index: int) -> int:
    """Where the last character of code before `index` is, skipping whitespace and comments.

    The position and not the character, because the caller needs to read the word
    ending there: searching the text for the character again finds the last one of
    its kind, which inside a skipped comment is a different character entirely —
    `return // note\\n<div>` would hand back the `n` of "note" and read the element
    as a comparison.

    The whole of the JSX-versus-comparison decision rests on this, so comments are
    skipped rather than read: `return (\\n  // why\\n  <div>` must reach the `(`.
    Returns `-1` when nothing precedes it.
    """
    position = index - 1
    while position >= 0:
        char = text[position]
        if char.isspace():
            position -= 1
            continue
        if char == "/" and position >= 1 and text[position - 1] == "*":
            opened = text.rfind("/*", 0, position)
            if opened == -1:
                return position
            position = opened - 1
            continue
        line_start = text.rfind("\n", 0, position) + 1
        comment = text.find("//", line_start)
        if comment != -1 and comment <= position:
            position = comment - 1
            continue
        return position
    return -1


def word_ending_at(text: str, index: int) -> str:
    """The identifier ending at `index`, which is what tells `return` from a name."""
    end = index + 1
    start = end
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in IDENTIFIER_CHARACTERS):
        start -= 1
    return text[start:end]


def opens_an_element(text: str, index: int) -> bool:
    """Whether the `<` at `index` opens JSX rather than comparing or parameterising.

    Two questions, and both have to say yes. What follows the `<` must be a name,
    a fragment or a closing tag — which is what makes `a < b` a comparison, since
    a space follows. And what precedes it must be a place an expression may begin:
    an operator, an opening bracket, or one of the keywords an expression follows.
    `Record<string, string>` and `useState<Props>(null)` fail the second, because
    an identifier precedes them.
    """
    following = text[index + 1 : index + 2]
    if not following or not (following.isalpha() or following in JSX_OPENERS):
        return False
    position = previous_significant(text, index)
    if position < 0:
        return True
    previous = text[position]
    if previous in EXPRESSION_OPENERS or previous == "}":
        return True
    if previous.isalnum() or previous in IDENTIFIER_CHARACTERS:
        return word_ending_at(text, position) in JSX_EXPRESSION_KEYWORDS
    return False


def scan_source(text: str, source: str, *, jsx: bool) -> list[Piece]:
    """Every piece of readable text in one file, with the position it was written in.

    The states are code, a JSX tag, the children of an element, and a template
    literal; a `{` inside JSX and a `${` inside a template each open a nested code
    frame that closes on its own unmatched `}`. Anything that leaves the scanner
    unable to say which state it is in is refused.
    """
    lines = text.splitlines()
    pieces: list[Piece] = []
    frames = [Frame(CODE_FRAME)]
    index = 0
    line = 1
    length = len(text)

    while index < length:
        frame = frames[-1]
        where = f"{source}:{line}"
        raw = line_of(lines, line)

        if frame.kind == CHILDREN_FRAME:
            stop = index
            while stop < length and text[stop] not in "<{":
                stop += 1
            run = text[index:stop]
            if run.strip():
                pieces.append(Piece(JSX_TEXT, run, line, CHILDREN, None))
            line += run.count("\n")
            index = stop
            if index >= length:
                raise ComponentParseError(
                    refusal(source, raw, "ends inside the children of an element it never closed")
                )
            if text[index] == "{":
                frames.append(Frame(CODE_FRAME, attribute=frame.attribute))
                index += 1
                continue
            if text[index + 1 : index + 2] == "/":
                close = text.find(">", index)
                if close == -1:
                    raise ComponentParseError(
                        refusal(source, raw, "opens a closing tag that never ends")
                    )
                line += text.count("\n", index, close)
                index = close + 1
                frames.pop()
                continue
            frames.append(Frame(TAG_FRAME, opened_on=line))
            index += 1
            continue

        if frame.kind == TEMPLATE_FRAME:
            char = text[index]
            if char == "\\":
                frame.buffer.append(text[index + 1 : index + 2])
                index += 2
                continue
            if char == BACKTICK:
                fragment = "".join(frame.buffer)
                if fragment.strip():
                    pieces.append(
                        Piece(TEMPLATE, fragment, frame.opened_on, frame.position, frame.attribute)
                    )
                frames.pop()
                index += 1
                continue
            if char == "$" and text[index + 1 : index + 2] == "{":
                fragment = "".join(frame.buffer)
                if fragment.strip():
                    pieces.append(
                        Piece(TEMPLATE, fragment, frame.opened_on, frame.position, frame.attribute)
                    )
                frame.buffer.clear()
                frame.opened_on = line
                frames.append(Frame(CODE_FRAME, attribute=frame.attribute))
                index += 2
                continue
            if char == "\n":
                line += 1
            frame.buffer.append(char)
            index += 1
            continue

        char = text[index]

        if char == "\n":
            line += 1
            index += 1
            continue

        if text.startswith("//", index):
            end = text.find("\n", index)
            index = length if end == -1 else end
            continue

        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                raise ComponentParseError(
                    refusal(source, raw, "opens a block comment that is never closed")
                )
            line += text.count("\n", index, end)
            index = end + 2
            continue

        if char in STRAIGHT_QUOTES:
            if frame.kind == TAG_FRAME:
                position, attribute = ATTRIBUTE, frame.attribute
                frame.attribute = None
            else:
                line_start = text.rfind("\n", 0, index) + 1
                before = text[line_start:index]
                position = IMPORT if IMPORT_POSITION.search(before) else frame.position
                attribute = frame.attribute
            value, index = read_quoted(text, index, where, raw)
            pieces.append(Piece(STRING, value, line, position, attribute))
            continue

        if char == BACKTICK:
            position = EXPRESSION if frame.kind == TAG_FRAME else frame.position
            frames.append(
                Frame(
                    TEMPLATE_FRAME,
                    attribute=frame.attribute,
                    position=position,
                    opened_on=line,
                )
            )
            if frame.kind == TAG_FRAME:
                frame.attribute = None
            index += 1
            continue

        if frame.kind == TAG_FRAME:
            if text.startswith("/>", index):
                frames.pop()
                index += 2
                continue
            if char == ">":
                frame.kind = CHILDREN_FRAME
                frame.attribute = None
                index += 1
                continue
            if char == "{":
                frames.append(Frame(CODE_FRAME, attribute=frame.attribute))
                index += 1
                continue
            if char == "=" or char.isspace():
                index += 1
                continue
            name = JSX_NAME.match(text, index)
            if name is None:
                raise ComponentParseError(
                    refusal(
                        source,
                        raw,
                        f"holds {char!r} inside a JSX tag, where this scanner expects an attribute "
                        "name, a value, or the end of the tag",
                    )
                )
            frame.attribute = name.group(0)
            index = name.end()
            continue

        if char == "{":
            frame.depth += 1
            index += 1
            continue

        if char == "}":
            if frame.depth == 0 and len(frames) > 1:
                frames.pop()
            elif frame.depth > 0:
                frame.depth -= 1
            index += 1
            continue

        if jsx and char == "<" and opens_an_element(text, index):
            frames.append(Frame(TAG_FRAME, opened_on=line))
            index += 1
            continue

        index += 1

    if len(frames) != 1 or frames[0].kind != CODE_FRAME:
        raise ComponentParseError(
            refusal(
                source,
                "",
                "ends with "
                f"{[frame.kind for frame in frames[1:]]} still open, so the scanner lost track of "
                "where the code was and every string after that point was read in the wrong state",
            )
        )
    return pieces


# ---------------------------------------------------------------------------
# The classification.
# ---------------------------------------------------------------------------


def attribute_may_carry_several_words(name: str) -> bool:
    """Whether an attribute's value is legitimately more than one token."""
    lowered = name.lower()
    return lowered.startswith(DATA_ATTRIBUTE_PREFIX) or (
        lowered in ATTRIBUTES_ALLOWED_TO_CARRY_SEVERAL_WORDS
    )


def is_visible_attribute(name: str | None) -> bool:
    """Whether a reader reads or hears this attribute's value."""
    return name is not None and name.lower() in VISIBLE_ATTRIBUTES


def refuse(piece: Piece, source: str, why: str) -> Finding:
    """One finding, carrying the text as a reader would meet it."""
    return Finding(source, piece.line, piece.value, why)


def judge(piece: Piece, source: str, known_keys: frozenset[str]) -> Finding | None:
    """What one piece of text is: allowed, or a finding saying why not.

    The order is the order the rules can be read in. A copy key wins over
    everything, because `copy('instructor_report_page.heading')` inside an
    `aria-label` is the convention working rather than failing.
    """
    if piece.kind == JSX_TEXT:
        if has_letters(HTML_ENTITY.sub(" ", piece.value)):
            return refuse(
                piece,
                source,
                "renders text straight into JSX, where no copy module governs it",
            )
        return None

    if piece.position == IMPORT:
        return None

    value = piece.value

    # The key check runs where a key is written — an expression, and one that is
    # not the value of a named non-visible attribute. A `data-testid` reading
    # `report.trend` is a test id shaped like a key, and the attribute's name is
    # what says so; running the inventory cross-check over it would refuse every
    # dotted test id in the tree.
    key_position = piece.position != ATTRIBUTE and (
        piece.attribute is None or is_visible_attribute(piece.attribute)
    )
    if piece.kind == STRING and key_position and DOTTED_KEY.match(value):
        if value in known_keys:
            return None
        return refuse(
            piece,
            source,
            "is spelled like a copy key and the inventory holds no such key, so whatever it looks "
            "up is not a governed string",
        )

    if is_visible_attribute(piece.attribute) and has_letters(value):
        return refuse(
            piece,
            source,
            f"supplies {piece.attribute} — which a reader reads or hears — with a literal rather "
            "than with a copy entry",
        )

    if not is_sentence_shaped(value):
        return None

    # Judged by the attribute's name whether the value is written directly or
    # through braces: `className="a b"` and `className={'a b'}` are one class
    # list in two spellings, and a rule that read only the first would refuse
    # every conditional class in the tree.
    if piece.attribute is not None and attribute_may_carry_several_words(piece.attribute):
        return None

    if piece.position == ATTRIBUTE:
        return refuse(
            piece,
            source,
            f"supplies {piece.attribute} with several words, and this sweep cannot say whether a "
            "reader sees them",
        )

    return refuse(
        piece,
        source,
        "writes a sentence into the component tree, where SPEC §4.1 items 4 and 5 are asserted "
        "over nothing",
    )


def findings_in_source(
    text: str, source: str, *, jsx: bool, known_keys: frozenset[str]
) -> list[Finding]:
    """Every string in one file that no rule allows."""
    pieces = scan_source(text, source, jsx=jsx)
    judged = (judge(piece, source, known_keys) for piece in pieces)
    return [finding for finding in judged if finding is not None]


# ---------------------------------------------------------------------------
# The walk.
# ---------------------------------------------------------------------------


def is_test_module(path: Path) -> bool:
    """Whether a file is a test rather than something that ships."""
    return TEST_INFIX in path.name


def excluded_support_paths() -> list[Path]:
    """The three test-support modules, as absolute paths."""
    return [FRONTEND_SOURCE_ROOT / relative for relative in EXCLUDED_SUPPORT_MODULES]


def support_modules_that_do_not_exist() -> list[str]:
    """Every named test-support module that is not there.

    An exclusion for a file that has been renamed excuses nothing and says
    nothing, and it goes on reading like coverage. So the names are checked
    rather than assumed.
    """
    return sorted(display(path) for path in excluded_support_paths() if not path.is_file())


def every_source_file(directories: tuple[Path, ...] = SWEPT_DIRECTORIES) -> list[Path]:
    """Every TypeScript file under the swept trees, at any depth, tests included.

    Symlinked directories are descended, for the reason the copy collector gives:
    a walk that stops at a link reports a clean tree over whatever is behind it.
    """
    missing = [display(directory) for directory in directories if not directory.is_dir()]
    if missing:
        raise ComponentStringError(
            f"{missing} is not a directory, so this sweep read nothing there and every string in "
            "it is a string it never saw."
        )
    found = sorted(
        path
        for directory in directories
        for path in directory.rglob("*", recurse_symlinks=True)
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
    )
    if not found:
        raise ComponentStringError(
            f"No {list(SOURCE_SUFFIXES)} file exists under {[display(d) for d in directories]}, so "
            "every rule over the component and route trees is a statement about nothing "
            "(`docs/MISTAKES.md` entry 3)."
        )
    return found


def resolved_support_modules(support_modules: tuple[Path, ...] | None) -> set[Path]:
    """The support modules to excuse: the three real ones, or whatever a control plants.

    Every walk below takes them as an argument so that the controls can drive the
    exclusion over a planted tree. A rule that could only be exercised against the
    real files would be a rule whose refusing direction nobody has ever seen
    (`docs/MISTAKES.md` entry 3).
    """
    chosen = excluded_support_paths() if support_modules is None else list(support_modules)
    return {path.resolve() for path in chosen}


def swept_files(
    directories: tuple[Path, ...] = SWEPT_DIRECTORIES,
    support_modules: tuple[Path, ...] | None = None,
) -> list[Path]:
    """Every file this sweep judges: the shipped ones, tests and support modules aside."""
    excluded = resolved_support_modules(support_modules)
    return [
        path
        for path in every_source_file(directories)
        if not is_test_module(path) and path.resolve() not in excluded
    ]


def findings_in_tree(
    known_keys: frozenset[str],
    directories: tuple[Path, ...] = SWEPT_DIRECTORIES,
    support_modules: tuple[Path, ...] | None = None,
) -> list[Finding]:
    """Every ungoverned string in the component and route trees.

    A file the scanner refuses becomes a finding against that file rather than an
    exception that ends the sweep, so one unreadable module cannot hide the rest
    behind it. The refusal text is carried through whole, and the refusals the
    inventory's own escape readers raise are caught here for the same reason.
    """
    findings: list[Finding] = []
    for path in swept_files(directories, support_modules):
        source = display(path)
        try:
            findings.extend(
                findings_in_source(
                    path.read_text(encoding="utf-8"),
                    source,
                    jsx=path.suffix.lower() == JSX_SUFFIX,
                    known_keys=known_keys,
                )
            )
        except CopyInventoryError as refused:
            findings.append(Finding(source, 0, str(refused), "cannot be read by this scanner"))
    return findings


# ---------------------------------------------------------------------------
# The excluded modules, and who imports them.
# ---------------------------------------------------------------------------


def import_specifiers(text: str) -> list[str]:
    """Every module specifier a file names."""
    return [match.group(2) for match in IMPORT_SPECIFIERS.finditer(text)]


def names_of(path: Path) -> frozenset[str]:
    """The spellings a relative import of `path` can end in."""
    return frozenset({path.name, path.name.removesuffix(path.suffix)})


def shipped_importers_of_support_modules(
    directories: tuple[Path, ...] = SWEPT_DIRECTORIES,
    support_modules: tuple[Path, ...] | None = None,
) -> dict[str, list[str]]:
    """Every shipped file that imports one of the excluded test-support modules.

    The exclusion above is a claim that these modules reach nobody. This is what
    makes the claim checkable: a component importing its own fixtures ships them,
    and the sweep would then be excusing strings that do reach a screen.
    """
    chosen = excluded_support_paths() if support_modules is None else list(support_modules)
    excluded = {path.resolve() for path in chosen}
    wanted = {display(path): names_of(path) for path in chosen}
    importers: dict[str, list[str]] = {name: [] for name in wanted}

    for path in every_source_file(directories):
        if is_test_module(path) or path.resolve() in excluded:
            continue
        specifiers = import_specifiers(path.read_text(encoding="utf-8"))
        for name, spellings in wanted.items():
            if any(
                specifier.startswith(".") and specifier.rsplit("/", 1)[-1] in spellings
                for specifier in specifiers
            ):
                importers[name].append(display(path))

    return {name: sorted(found) for name, found in importers.items() if found}
