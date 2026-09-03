"""E2-11 — every shipped user-facing string, read from its source of record.

SPEC §14.3's E2 exit clause: "the copy-inventory test exists and reads the survey
surface's shipped strings". The strings live in two places, and this module reads
both so that the rules in
`tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py` are
statements about what ships rather than about a list somebody kept.

**The backend half is read through E2-08's own reader.** `fixtures.submit.
copy_texts()` imports `app.copy`, calls the package's `copy_modules()`
enumeration and reads each module's `COPY` mapping; it already refuses a registry
that is missing, unenumerable or empty. A second reader here would be a second
answer to "where is the registry" for the two halves of one ticket to disagree
over (`docs/MISTAKES.md` entry 13), so there is one, and it is that one.

**The frontend half is parsed as text, in Python.** The alternative — evaluating
the module with Node — would put a JavaScript runtime inside the §4.1 invariant
pass, which runs serially in the Python job with no database and nothing else.
The cost is stated rather than hidden: a string assembled at runtime is invisible
to a text parse. See the honest-limits paragraph in the test module's docstring
for the whole list.

**The parser refuses what it cannot classify, and that is the design.** A parser
that skipped an unfamiliar line would report a clean surface over strings it never
read, which is `docs/MISTAKES.md` entries 3 and 9 in one move: every rule asserted
downstream would still be green, and its greenness would mean nothing. So every
line inside the exported object literal is classified — an entry, a comment, the
continuation of an entry whose value is on the next line, or the close — and
anything else raises `CopyParseError` naming the file, the line and the line's
text.

**Outside the literal, code is read for quotes rather than for shape, and the
rule is the same above it and below it.** A copy file carries helpers after its
mapping — E2-10's `studentSurvey.ts` closes its literal and then exports a `keyof
typeof` key type, a `copy()` lookup and a `fillCopy()` that substitutes
`{placeholder}` holes. Those are not strings and there is no reason to refuse
them. So outside the literal **a code line passes only if it carries no quote
character at all** — no `'`, no `"`, no backtick. A sentence written into a
helper (`return 'Nothing is open this week.'`) is a shipped string the inventory
cannot govern, and it is refused loudly rather than passed over, which is why
"allow everything after the close" was not the answer.

**One rule and not two**, because the first version of this parser had a
prefix-matched allowance above the literal (`import`, `type`, `interface`) that
skipped such a line whole — so `type Mood = 'Great week' | 'Rough week';` parsed
clean while the identical sentence below the literal was refused. A guard with
two rules for one question is a guard defeated at whichever end is weaker, and
the fail-closed end is the one to keep.

Three costs, stated rather than discovered. A line whose only quote sits in a
trailing `// it's fine` comment is refused; so is a helper that legitimately
needs a string for something other than copy; and so is an `import` with a
quoted module path, which is why this rule is affordable only because the shipped
copy files have no imports. Each refusal names the line, and the answer is to
move the string into the literal or to triage the exception here, in the change
that introduces it. Comments are unaffected: block and line comments are consumed
before this rule is reached, which is why the backticks inside `fillCopy`'s own
documentation are not a refusal.

**The frontend enumeration is recursive, over the whole TypeScript family, and
the coverage rule does not consult it.** A one-level `*.ts` glob missed a copy
file in a subdirectory and a copy file spelled `.tsx`, and the rule that was
supposed to catch that compared the glob's answer with the same glob's answer —
so it agreed with itself and two shipped surfaces were invisible. The walk now
descends and reads `.ts`, `.tsx`, `.mts` and `.cts`; and
`files_the_collector_did_not_read` walks **everything** under the copy
directory, at any depth and of any suffix, requiring each file to be one the
collector actually parsed. The copy directory holds copy, so a `.json`, a `.md`
or a suffix nobody thought of is a red rather than a silence. The two
enumerations answer different questions on purpose: one asks what to parse, the
other asks what was missed.

**The files are enumerated by globbing the directory, never by asking git.** A
violation planted to prove this suite can go red is an untracked file, and a
`git ls-files` enumeration would not see it — the run would come back green and
read as "the finding was wrong" (`docs/MISTAKES.md` entry 16's neighbour, and the
check-the-mutation-landed rule). The glob refuses an empty directory for the same
reason it refuses an unreadable line.

**Nothing here reads a database or builds an application.** The registry is a
package of constants and the frontend copy is a file; both are readable in the
invariant pass, and `app.copy` is import-safe by design.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from fixtures.submit import COPY_PACKAGE, copy_texts

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where the frontend keeps its externalized strings. E2-10 put `studentSurvey.ts`
# here and E2-11 reads the directory rather than that file: a second surface
# arrives as a second file, and an inventory that named one file would be an
# inventory the next ticket shrinks by accident.
FRONTEND_COPY_DIRECTORY = REPO_ROOT / "frontend" / "src" / "copy"

# The whole TypeScript family, because a copy file that changed suffix is a copy
# file. `.tsx` is the one that matters — a copy module beside a component would
# take it as a matter of course — and `.mts`/`.cts` are here because excluding
# them would be choosing which two of four spellings the guard can see. The
# walk is recursive: `frontend/src/copy/reports/aggregate.ts` is copy in the copy
# directory, and a one-level glob reported the tree clean over exactly that file.
COPY_FILE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")

# The characters a TypeScript string may be delimited by. Backticks are refused
# rather than read: a template literal can interpolate, so its text is not a
# string this parser is in a position to report.
STRAIGHT_QUOTES = "'\""
BACKTICK = chr(0x60)

# Every character a string may open with. Outside the literal — above it and
# below it alike — a code line carrying any of the three is refused. See the
# module docstring for the rule and what it costs.
QUOTE_CHARACTERS = STRAIGHT_QUOTES + BACKTICK

# The two halves of a UTF-16 surrogate pair. A padlock can be written as two
# four-digit escapes rather than one — the high half then the low half — and
# decoding each on its own produces two lone surrogates that no sweep for the
# lock character can match, while the browser renders the padlock exactly as it
# renders the literal one. So the pair is recombined here, and a half with no
# partner is refused: a lone surrogate is not text, and passing one through would
# be this parser reporting a character no reader will ever see.
HIGH_SURROGATES = range(0xD800, 0xDC00)
LOW_SURROGATES = range(0xDC00, 0xE000)
SURROGATE_BASE = 0x10000

# One exported object literal per copy file, discovered by shape rather than by
# name — `export const STUDENT_SURVEY_COPY = {`. The name is not pinned because
# the next surface's file will choose its own, and a constant here would be this
# suite naming something the ticket leaves to the author. What *is* pinned is
# that there is exactly one: a second literal in the same file is a second place
# for strings to live, and the parser reads one.
OPENING = re.compile(
    r"^export\s+const\s+[A-Za-z_$][A-Za-z0-9_$]*\s*(?::[^=]+)?=\s*\{\s*$",
)

# `}`, `};`, `} as const;`, `} as const satisfies Record<string, string>;`.
CLOSING = re.compile(r"^\}(?:\s+as\s+const)?(?:\s+satisfies\s+[^;]+?)?\s*;?\s*$")

# The escapes a JavaScript string may spell a character with, other than the
# numeric ones handled beside them. `\u{1F512}` matters more than it looks:
# without it, a lock emoji written as an escape would reach the iconography sweep
# in §4.1 item 5 as the ordinary characters of an escape sequence, and the sweep
# would report the surface clean. A parser that mis-decodes is a collector gone
# blind.
SIMPLE_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
}

HEX_DIGITS = "0123456789abcdefABCDEF"


class CopyInventoryError(Exception):
    """The inventory cannot be collected, so nothing asserted over it would mean anything."""


class CopyParseError(CopyInventoryError):
    """A line inside a copy file that the parser cannot classify."""


class CopyString(NamedTuple):
    """One shipped string: its dotted key, its text, and where it was read from."""

    key: str
    text: str
    source: str


def display(path: Path) -> str:
    """A path as this repository names it, or in full when it is outside the checkout."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def refusal(where: str, line: str, why: str) -> str:
    """The message every parse refusal carries: the place, the line, and what to do."""
    return "\n".join(
        [
            f"{where} {why}:",
            f"  {line.rstrip()!r}",
            "",
            "This parser refuses a line it cannot classify rather than skipping it. A collector "
            "that skips what it cannot read reports a clean surface over strings it never saw, "
            "and every rule E2-11 asserts would still be green (`docs/MISTAKES.md` entries 3 and "
            "9).",
            "",
            "The shipped convention is one exported object literal per file, holding quoted "
            "`'dotted.key': 'text'` pairs, closed with `} as const satisfies Record<string, "
            "string>;`. If the shape above is legitimate, it is taught in "
            "`tests/fixtures/copy_inventory.py` — in the same change that introduces it, so that "
            "the parser and the convention move together.",
        ]
    )


def read_escape(fragment: str, index: int, where: str, line: str) -> tuple[str, int]:
    """The character a backslash escape at `index` stands for, and the index after it."""
    if index + 1 >= len(fragment):
        raise CopyParseError(refusal(where, line, "ends in a dangling backslash"))
    marker = fragment[index + 1]

    if marker == "u" and fragment[index + 2 : index + 3] == "{":
        end = fragment.find("}", index + 3)
        digits = fragment[index + 3 : end]
        if end == -1 or not digits or any(digit not in HEX_DIGITS for digit in digits):
            raise CopyParseError(
                refusal(where, line, "carries a `\\u{...}` escape this cannot read")
            )
        return chr(int(digits, 16)), end + 1

    if marker in ("u", "x"):
        width = 4 if marker == "u" else 2
        digits = fragment[index + 2 : index + 2 + width]
        if len(digits) != width or any(digit not in HEX_DIGITS for digit in digits):
            raise CopyParseError(
                refusal(where, line, f"carries a `\\{marker}` escape this cannot read")
            )
        return chr(int(digits, 16)), index + 2 + width

    return SIMPLE_ESCAPES.get(marker, marker), index + 2


def is_surrogate(character: str, half: range) -> bool:
    """Whether `character` is one code unit and falls in one half of the surrogate range."""
    return len(character) == 1 and ord(character) in half


def joined_surrogates(high: str, low: str) -> str:
    """The one character a high and a low surrogate stand for together."""
    high_part = (ord(high) - HIGH_SURROGATES.start) << 10
    low_part = ord(low) - LOW_SURROGATES.start
    return chr(SURROGATE_BASE + high_part + low_part)


def read_surrogate_pair(
    high: str, fragment: str, index: int, where: str, line: str
) -> tuple[str, int]:
    """The character a high surrogate and the escape after it stand for.

    A high surrogate with no low surrogate following is refused. Decoding it on
    its own would put a lone surrogate in the collected text: not a character any
    reader sees, and — for the padlock spelled this way — not one the iconography
    sweep in §4.1 item 5 can match either, while the browser renders the icon.
    """
    partner = ""
    if index < len(fragment) and fragment[index] == "\\":
        partner, index = read_escape(fragment, index, where, line)
    if not is_surrogate(partner, LOW_SURROGATES):
        raise CopyParseError(
            refusal(
                where,
                line,
                "carries the high half of a surrogate pair with no low half after it, which is "
                "not a character anything can render or sweep",
            )
        )
    return joined_surrogates(high, partner), index


def read_string_literal(fragment: str, where: str, line: str) -> tuple[str, str]:
    """The string literal `fragment` begins with, decoded, and whatever follows it.

    Decoded rather than returned raw, because the rules downstream are about the
    characters a student reads: `\\u{1F512}` is a lock on the screen and would be
    the ordinary characters of an escape sequence to a sweep reading the source.

    **Surrogate pairs are joined here**, so that the same padlock written as two
    four-digit escapes decodes to the same one character as the brace form and the
    literal. A half with no partner is refused rather than passed through.
    """
    if not fragment:
        raise CopyParseError(refusal(where, line, "expects a quoted string and holds nothing"))
    quote = fragment[0]
    if quote == BACKTICK:
        raise CopyParseError(
            refusal(
                where,
                line,
                "spells a string as a template literal, which may interpolate and is therefore "
                "not text this parser can report",
            )
        )
    if quote not in STRAIGHT_QUOTES:
        raise CopyParseError(refusal(where, line, "does not begin with a quoted string"))

    read: list[str] = []
    index = 1
    while index < len(fragment):
        char = fragment[index]
        if char == "\\":
            decoded, index = read_escape(fragment, index, where, line)
            if is_surrogate(decoded, HIGH_SURROGATES):
                decoded, index = read_surrogate_pair(decoded, fragment, index, where, line)
            elif is_surrogate(decoded, LOW_SURROGATES):
                raise CopyParseError(
                    refusal(
                        where,
                        line,
                        "carries the low half of a surrogate pair with no high half before it, "
                        "which is not a character anything can render or sweep",
                    )
                )
            read.append(decoded)
            continue
        if char == quote:
            return "".join(read), fragment[index + 1 :].strip()
        read.append(char)
        index += 1
    raise CopyParseError(refusal(where, line, "opens a string that the line never closes"))


def require_entry_tail(remainder: str, where: str, line: str) -> None:
    """What may follow an entry's value: a comma, a trailing comment, or nothing."""
    tail = remainder.removeprefix(",").strip()
    if tail and not tail.startswith("//"):
        raise CopyParseError(
            refusal(where, line, f"carries {tail!r} after its value, which this parser cannot read")
        )


def parse_copy_module(text: str, source: str) -> dict[str, str]:
    """Every `key: text` pair of one TypeScript copy file, or a refusal naming the line.

    The states are: before the literal, inside it, after it, inside a block
    comment, and awaiting the value of an entry whose key ended its line. Every
    line lands in one of them or the parse stops.

    **Before and inside the literal**, only a declaration this parser knows
    (`import`, `type`, `interface`, `export type`) or a classified entry passes.
    **After it**, a code line passes when it carries no quote character —
    a copy file's helpers live there and hold no strings. The module docstring
    carries the rule and its two costs.
    """
    entries: dict[str, str] = {}
    inside = False
    opened = False
    in_block_comment = False
    pending_key: str | None = None

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        where = f"{source}:{number}"

        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
                if line.split("*/", 1)[1].strip():
                    raise CopyParseError(
                        refusal(where, raw, "closes a block comment with code after it")
                    )
            continue

        if not line or line.startswith("//"):
            continue

        if line.startswith("/*"):
            if "*/" not in line:
                in_block_comment = True
            elif line.split("*/", 1)[1].strip():
                raise CopyParseError(
                    refusal(where, raw, "closes a block comment with code after it")
                )
            continue

        if not inside:
            if OPENING.match(line):
                if opened:
                    raise CopyParseError(
                        refusal(
                            where,
                            raw,
                            "opens a second exported object literal; a copy file holds one, so "
                            "that the inventory reads all of it",
                        )
                    )
                inside = True
                opened = True
                continue
            # Outside the literal, above it or below it: the file's declarations
            # and its helpers. Read for quotes rather than for shape — see the
            # module docstring, and the paragraph there on why this is one rule
            # and not two. The `OPENING` check above runs first, so a second
            # literal is still refused as one rather than passing here for
            # holding no quote.
            carried = sorted({quote for quote in QUOTE_CHARACTERS if quote in line})
            if carried:
                raise CopyParseError(
                    refusal(
                        where,
                        raw,
                        f"is code {'below' if opened else 'above'} the copy literal carrying "
                        f"{carried}; a string written outside the literal is a string the "
                        "inventory cannot govern, and §4.1 items 4 and 5 would never be checked "
                        "over it",
                    )
                )
            continue

        if pending_key is not None:
            value, remainder = read_string_literal(line, where, raw)
            require_entry_tail(remainder, where, raw)
            record_entry(entries, pending_key, value, where, raw)
            pending_key = None
            continue

        if CLOSING.match(line):
            inside = False
            continue

        key, after_key = read_string_literal(line, where, raw)
        if not after_key.startswith(":"):
            raise CopyParseError(refusal(where, raw, "names a key with no `:` after it"))
        rest = after_key[1:].strip()
        if not rest:
            pending_key = key
            continue
        value, remainder = read_string_literal(rest, where, raw)
        require_entry_tail(remainder, where, raw)
        record_entry(entries, key, value, where, raw)

    if in_block_comment:
        raise CopyParseError(refusal(source, "", "ends inside an unclosed block comment"))
    if pending_key is not None:
        raise CopyParseError(refusal(source, "", f"ends before the value of {pending_key!r}"))
    if inside:
        raise CopyParseError(refusal(source, "", "opens a copy literal it never closes"))
    if not opened:
        raise CopyParseError(
            refusal(
                source,
                "",
                "exports no object literal of the shape `export const NAME = {`, so this file "
                "contributes nothing to the inventory while sitting in the copy directory",
            )
        )
    if not entries:
        raise CopyParseError(
            refusal(
                source,
                "",
                "exports an empty copy literal, and a surface with no strings passes every "
                "vocabulary rule there is",
            )
        )
    return entries


def record_entry(entries: dict[str, str], key: str, value: str, where: str, line: str) -> None:
    """Add one entry, refusing a key the same file has already used."""
    if key in entries:
        raise CopyParseError(
            refusal(where, line, f"repeats the key {key!r}, so one of the two strings never ships")
        )
    entries[key] = value


def frontend_copy_files(directory: Path) -> list[Path]:
    """Every copy file under `directory`, at any depth, refusing a directory with none.

    On disk and not through `git ls-files`: a planted file used to prove this
    suite goes red is untracked, and an enumeration that asked git would not see
    it. Recursive and over the whole TypeScript family, because a one-level
    `*.ts` glob reported a clean tree over a copy file in a subdirectory and a
    copy file spelled `.tsx`.
    """
    if not directory.is_dir():
        raise CopyInventoryError(
            f"{display(directory)} is not a directory, so no frontend copy was read at all. "
            "E2-10 puts the survey surface's strings in `frontend/src/copy/studentSurvey.ts`; if "
            "the directory has moved, `FRONTEND_COPY_DIRECTORY` moves with it."
        )
    found = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in COPY_FILE_SUFFIXES
    )
    if not found:
        raise CopyInventoryError(
            f"{display(directory)} holds no {list(COPY_FILE_SUFFIXES)} file at any depth, so the "
            "frontend half of the inventory is empty. Every rule over it would then be a "
            "statement about nothing (`docs/MISTAKES.md` entry 3), which is why this is a refusal "
            "rather than an empty list."
        )
    return found


def every_file_under_the_copy_directory(directory: Path) -> list[Path]:
    """Everything under `directory`, at any depth, whatever its suffix.

    The second enumeration, and deliberately not the one above. The coverage rule
    that is supposed to catch a copy file the collector missed cannot be built out
    of the collector's own answer — that version agreed with itself, and a
    subdirectory and a `.tsx` shipped invisibly under it.
    """
    if not directory.is_dir():
        raise CopyInventoryError(
            f"{display(directory)} is not a directory, so this walk read nothing and every file "
            "it might have reported is a file it never saw."
        )
    found = sorted(path for path in directory.rglob("*") if path.is_file())
    if not found:
        raise CopyInventoryError(
            f"{display(directory)} holds no files at all, so the coverage rule over it is a "
            "statement about nothing."
        )
    return found


def files_the_collector_did_not_read(directory: Path) -> list[str]:
    """Every file under `directory` that the collector did not parse a string out of.

    The copy directory holds copy. A file of a suffix the collector does not
    read, or one nested where it does not look, is a shipped surface nothing
    governs — so it is named here rather than passed over. The comparison is
    between two independent walks: what the collector parsed, against everything
    that is there.
    """
    read_from = {string.source for string in collect_frontend_copy(directory)}
    return sorted(
        display(path)
        for path in every_file_under_the_copy_directory(directory)
        if display(path) not in read_from
    )


def collect_frontend_copy(directory: Path) -> list[CopyString]:
    """Every string every copy file in `directory` publishes."""
    collected: list[CopyString] = []
    for path in frontend_copy_files(directory):
        source = display(path)
        for key, text in parse_copy_module(path.read_text(encoding="utf-8"), source).items():
            collected.append(CopyString(key, text, source))
    return collected


def collect_backend_copy() -> list[CopyString]:
    """Every string the `app.copy` registry publishes, through E2-08's own reader."""
    return [CopyString(key, text, COPY_PACKAGE) for key, text in sorted(copy_texts().items())]


def collect_shipped_copy() -> tuple[CopyString, ...]:
    """Both halves of the inventory: the copy registry and the frontend copy files."""
    collected = (*collect_backend_copy(), *collect_frontend_copy(FRONTEND_COPY_DIRECTORY))
    if not collected:
        raise CopyInventoryError(
            "The inventory collected no strings from either source, so every rule over it would "
            "pass over nothing."
        )
    return collected


def prefix_of(key: str) -> str:
    """A dotted key's first segment, which is what names the surface it belongs to."""
    return key.split(".", 1)[0]
