"""The frontend takes colour and type from tokens, never from a literal — ticket E1-04.

E1-04 acceptance criterion 3: "No component carries a raw hex value; tokens only."
SPEC §7.6 states the same rule as the prototype-to-codebase contract —
`design/tokens.css` is the single source for palette, type, spacing, radii, shadow
and the focus ring, and there is "no raw hex in components". `docs/DESIGN_BRIEF.md`
adds two hard rules of its own, and they are hard rules rather than preferences
because they are what stops the tool reading as part of its host: interactive
elements never use Canvas blue (`#0374B5`), and no Inter, Roboto, Arial or Lato
anywhere — Canvas chrome is Lato, and the type contrast is how Pulse reads as its
own considered thing inside the iframe.

**Three rules, three tests, two scopes.** The hex rule is asserted over
`frontend/src`, where components live; the Canvas-blue and font-face rules are
asserted over everything under `frontend/`, because a colour borrowed in
`index.html`'s `theme-color` or a face declared in a Tailwind theme file outside
`src/` is borrowed just as surely. The scopes differ because the questions differ:
a raw hex outside `src/` may be legitimate — an HTML `meta` tag cannot hold
`var(--chalk)` — while borrowing the host's blue never is.

**Where the token definitions live is a settled contract of this ticket and not a
choice this module makes.** The tokens are imported from `design/tokens.css`; they
are not copied into `frontend/src`. That is why the hex rule carries no exception
list: a file under `src/` whose job is to define `--chalk: #F6F8F4` would fail
here, and it should, because the moment there are two copies of the palette the
"single source" in §7.6 is a sentence rather than a fact. If the implementation
needs the definitions inside `src/` after all, that is a decision to take in the
ticket — `docs/disputes/E1-04-NN.md` — rather than an exception to add here.

**An empty sweep is the failure this module is most likely to have, so it fails
loudly rather than passing.** `frontend/src` does not exist at the time this was
written: the whole scaffold is what E1-04 lands. A sweep over nothing reports a
clean tree, which is `docs/MISTAKES.md` entry 3 and the shape of entry 36 one file
over — a control that answers "nothing wrong here" over a tree it never read. So
every test below requires the scan to have found source files before its verdict
counts, and says which directory it looked in when it has not.

**The files are enumerated from the git index**, the way
`tests/unit/test_no_unresolved_merge_conflicts.py` does, because `node_modules`
and `dist` are gitignored and both are full of hex and full of Inter. The reader
is a copy of that module's rather than an import from it: that sweep is over the
whole index with no suffix filter and this one is over one directory with one, and
the two would have to grow apart the first time either changed
(`docs/MISTAKES.md` entry 13 weighs the other way when the shared thing is one
subprocess call). The cost of reading the index is that a file written and not yet
`git add`ed is invisible — which the empty-scan guard turns into a red rather than
a quiet pass, and which is the reason that guard is not ceremony.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

FRONTEND = "frontend"
FRONTEND_SOURCE = "frontend/src"

# The suffixes the hex rule reads. The ticket's scope names TypeScript, CSS and
# HTML; `.js` and `.jsx` are included so that a file which changes suffix does not
# leave the sweep, and `.json` deliberately is not — a design token exported as
# JSON would be the copy of the palette this module refuses elsewhere, and it
# would fail the rule for the right reason under a different filename.
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".css", ".html")

# `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA` — the four lengths CSS gives meaning to,
# spelled out rather than as `{3,8}` so that `#abcde` (five, meaningless) is not
# reported and a real six-digit value is not matched three characters short.
HEX_LITERAL = re.compile(r"#(?:[0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b")

# Canvas blue, as a bare string in any case and with or without a `#`. Searched as
# a substring rather than as a colour, because the value is the thing forbidden
# however it is spelled: in a comment, in a Tailwind theme entry, in a test id.
CANVAS_BLUE = re.compile(r"0374B5", re.IGNORECASE)

# The four faces `docs/DESIGN_BRIEF.md` forbids by name. The brief also forbids
# "system font stacks", and that is deliberately **not** asserted here: every
# family in `design/tokens.css` ends in one — `'Literata', Georgia, serif` — so a
# rule against system stacks would refuse the repository's own token file. This
# module asserts the four names the brief spells, and nothing wider.
FORBIDDEN_FACES = ("Inter", "Roboto", "Arial", "Lato")

# A CSS font declaration: `font-family:` or any `--font*` custom property, and its
# value up to the terminator. Declarations rather than free text, because "Inter"
# is a substring of "interface" and of "Interactive elements never use Canvas
# blue" — the sentence in the design brief that states the *other* rule this
# module enforces. A search over prose would report that sentence as a forbidden
# typeface.
FONT_DECLARATION = re.compile(
    r"(?:font-family|--font[A-Za-z0-9_-]*)\s*:\s*(?P<value>[^;{}\n]*)", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Samples the readers are run against before they are trusted against the tree.
#
# Copied whole out of the files they come from, the line they start on included —
# `docs/MISTAKES.md` entry 3, whose rule is that a canary retyped from where you
# think a sentence begins is the thing the canary exists to disprove.
# ---------------------------------------------------------------------------

# design/tokens.css, the palette block. A raw hex and a comment on the same line.
TOKEN_DEFINITION = (
    "  --chalk: #F6F8F4;         "  # noqa: S105 - a design-token CSS line, not a credential
    "/* App/page background; also AiPanel inset fill. Cool paper, never pure white. */"
)

# design/tokens.css, the type block. Three families, none of them forbidden, and
# a system fallback that must not be read as one.
ALLOWED_FONT_DECLARATION = (
    "  --font-body: 'Schibsted Grotesk', 'Helvetica Neue', sans-serif;  "
    "/* UI copy, helpers, buttons, labels. */"
)

# docs/DESIGN_BRIEF.md, the anti-slop guardrails. It carries the forbidden colour
# *and* the word "Interactive", so it is the near miss for both readers at once:
# the colour search must find it, and the font search must not.
CANVAS_BLUE_IN_PROSE = (
    "- Interactive elements never use Canvas blue (#0374B5) — the host owns that color; "
    "borrowing it confuses what belongs to whom."
)

# Constructed rather than copied: nothing in this repository declares a forbidden
# face, which is the point. Written the way a scaffold generated from a template
# would write it, since that is how one would arrive.
FORBIDDEN_FONT_DECLARATION = "  font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;"

# Two lines that must survive every reader here. The first is how a component is
# meant to reach a colour; the second is a TypeScript line whose identifier
# contains a forbidden face as a substring.
TOKEN_REFERENCE = "  color: var(--spruce-60);"  # noqa: S105 - a CSS token reference, not a credential
IDENTIFIER_CONTAINING_A_FACE = "  const interval = window.setInterval(beat, 180);"


def tracked_under(prefix: str) -> list[Path]:
    """Every tracked path under `prefix`, as git reports it.

    `git ls-files` rather than a filesystem walk: `frontend/node_modules` and
    `frontend/dist` are gitignored and are not this repository's source, and a
    walk would have to carry a list of directories to avoid — a list that goes
    stale silently, which is the failure this module is otherwise about.
    """
    git = shutil.which("git")
    if git is None:  # pragma: no cover - git is present in CI and in `make ci`
        pytest.fail(
            "git is not on PATH, so this sweep cannot enumerate tracked files. It fails rather "
            "than skipping: a skip here is indistinguishable from a frontend with no raw hex in "
            "it."
        )

    # The argument list is a literal and the executable is a resolved absolute
    # path, so neither S603's untrusted input nor S607's partial path applies.
    listing = subprocess.run(  # noqa: S603
        [git, "ls-files", "-z", "--", prefix],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [REPO_ROOT / name for name in listing.stdout.split("\0") if name]


def readable_text(path: Path) -> str | None:
    """One file's text, or `None` if it is binary or absent from this checkout."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None


def source_files() -> list[Path]:
    """The component sources: tracked files under `frontend/src` with a source suffix."""
    return [
        path for path in tracked_under(FRONTEND_SOURCE) if path.suffix.lower() in SOURCE_SUFFIXES
    ]


def frontend_files() -> list[Path]:
    """Every tracked file under `frontend/`, whatever its suffix."""
    return tracked_under(FRONTEND)


def require_a_scanned_tree(scanned: list[Path], where: str, rule: str) -> None:
    """Fail loudly when the sweep found nothing to read.

    The verdicts below are all "nothing in the tree does the forbidden thing", and
    an empty tree satisfies every one of them perfectly. E1-04 lands the whole
    scaffold, so "there is no frontend yet" and "the frontend is clean" are the
    same green line unless this says otherwise.
    """
    assert scanned, "\n".join(
        [
            f"This sweep read no files under `{where}`, so it asserted nothing about {rule}.",
            "",
            "E1-04 is the ticket that lands `frontend/src` — the five landing views, the router "
            "and the components — so an empty scan here before the scaffold exists is expected "
            "and is a red rather than a pass. A rule enforced over nothing is not enforced.",
            "",
            "Two other ways to arrive here once it does exist: the files are written but not yet "
            "`git add`ed, since this reads the index rather than the working tree; or the "
            "scaffold landed somewhere other than `frontend/src`, in which case SPEC §13's tree "
            "is the thing to reconcile and this constant follows it.",
        ]
    )


def offending_lines(path: Path, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """Every line of one file that `pattern` matches, with its line number."""
    text = readable_text(path)
    if text is None:
        return []
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def forbidden_faces_in(value: str) -> list[str]:
    """The forbidden typefaces named in one declaration's value."""
    return [
        face
        for face in FORBIDDEN_FACES
        if re.search(rf"\b{re.escape(face)}\b", value, re.IGNORECASE)
    ]


def font_offences_in_text(text: str) -> list[tuple[int, str, list[str]]]:
    """Every font declaration in `text` that names a forbidden face.

    One reader, called both by the sweep and by the sweep's own controls
    (`docs/MISTAKES.md` entry 13). A second copy taking a path would be free to
    answer differently about the two sample lines than about the tree, which is
    the one thing the controls exist to rule out.
    """
    found: list[tuple[int, str, list[str]]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in FONT_DECLARATION.finditer(line):
            faces = forbidden_faces_in(match.group("value"))
            if faces:
                found.append((number, line.strip(), faces))
    return found


def font_offences(path: Path) -> list[tuple[int, str, list[str]]]:
    """Every font declaration in one file that names a forbidden face."""
    text = readable_text(path)
    if text is None:
        return []
    return font_offences_in_text(text)


def test_no_frontend_source_file_carries_a_raw_hex_colour() -> None:
    """E1-04 criterion 3, and SPEC §7.6's "no raw hex in components".

    A palette is a single source or it is not one. The moment a component spells
    `#DFA320` instead of `var(--marigold)`, the token file has stopped being the
    place the colour is decided and become one of the places it is written down —
    and the failure that follows is not a wrong colour, it is a colour that stays
    right for a year and then drifts in one component nobody re-reads.

    **The reader is exercised on both sides before the tree is swept.** It must
    find the hex in a line copied whole out of `design/tokens.css`, and it must
    leave a `var(--token)` reference alone. A pattern that matched nothing would
    report every file clean; one that matched everything would fail the scaffold
    whatever it said, and that failure would read as an unbuilt ticket rather than
    as a broken test.

    **The mutation this kills:** put one literal back — a `#F6F8F4` background on
    the landing wrapper, a `#1E3932` on a heading. **The near misses that must
    stay green:** `var(--chalk)` anywhere, a `#root` id selector or an `href="#top"`
    (neither is three hex digits), and a hex in `frontend/index.html`, which this
    rule deliberately does not reach because a `theme-color` meta tag cannot hold
    a custom property.

    **One known false positive, stated rather than designed around.** A three- or
    four-digit issue reference in a comment — `// see PR #1234` — is a well-formed
    CSS colour and is reported. The rule is not narrowed for it, because every
    narrowing that would exclude it also excludes `#000`, which is the single
    likeliest raw colour to appear in a stylesheet. In frontend source, write the
    reference without the `#`.
    """
    assert HEX_LITERAL.search(TOKEN_DEFINITION), (
        f"The hex reader does not see a colour in {TOKEN_DEFINITION.strip()!r}, which is a line "
        "copied whole out of `design/tokens.css`. It has gone blind, and the sweep below would "
        "report every component clean."
    )
    assert not HEX_LITERAL.search(TOKEN_REFERENCE), (
        f"The hex reader reports a raw colour in {TOKEN_REFERENCE.strip()!r}, which is exactly how "
        "a component is supposed to reach one. A reader this loose fails the ticket for doing the "
        "right thing."
    )

    scanned = source_files()
    require_a_scanned_tree(scanned, FRONTEND_SOURCE, "raw hex colour literals")

    offenders = {
        path.relative_to(REPO_ROOT): lines
        for path in scanned
        if (lines := offending_lines(path, HEX_LITERAL))
    }

    assert not offenders, "\n".join(
        [
            f"These files under `{FRONTEND_SOURCE}` carry a raw hex colour:",
            *(
                f"  {name}:{number}: {line}"
                for name, lines in sorted(offenders.items())
                for number, line in lines
            ),
            "",
            "SPEC §7.6: `tokens.css` is the single source for palette, type, spacing, radii, "
            "shadow and the focus ring, and components consume tokens only. E1-04 criterion 3 "
            "says the same thing in one line: no component carries a raw hex value.",
            "",
            "There is no exception list here on purpose. The palette lives in "
            "`design/tokens.css` and is imported; a second copy of it under `frontend/src` is the "
            "thing that makes 'single source' stop being true, and it would arrive looking exactly "
            "like a file this test is being unfair to.",
        ]
    )


def test_nothing_in_the_frontend_borrows_canvas_blue() -> None:
    """`docs/DESIGN_BRIEF.md`, hard rule: the host owns `#0374B5`.

    "Interactive elements never use Canvas blue (#0374B5) — the host owns that
    color; borrowing it confuses what belongs to whom." Pulse renders inside the
    Canvas iframe, so this is not a taste rule: a control painted in the host's
    blue reads as part of the host, which is a claim about who is asking the
    student for their answer.

    Asserted over everything under `frontend/`, not only over `src/`, because the
    borrowing that matters can happen in a Tailwind theme file, in `index.html`,
    or in a comment somebody later copies. The hex sweep above would catch it
    inside `src/` as one raw colour among many; this one names it, so the failure
    says which rule was broken.

    **The reader is exercised first**, against the sentence in the design brief
    that states the rule — a line that carries the value itself, so a search that
    has gone blind cannot report a clean tree.

    **The mutation this kills:** paint the focus ring, a link or a landing view's
    heading `#0374B5`, in any case and in any file the frontend ships. **The near
    miss that must stay green:** `#0374B6`, and any other blue that is not the
    host's — this rule is about one value, and the token palette is what decides
    the rest. **What it does not see, said plainly:** the same colour written
    `rgb(3, 116, 181)`, or an `oklch()` conversion of it. The hex sweep covers the
    `src/` half of that gap and nothing covers the rest.
    """
    assert CANVAS_BLUE.search(CANVAS_BLUE_IN_PROSE), (
        "The Canvas-blue reader does not find the value in the design brief's own sentence about "
        f"it: {CANVAS_BLUE_IN_PROSE!r}. It has gone blind, and the sweep below would report a "
        "clean frontend whatever the frontend says."
    )
    assert not CANVAS_BLUE.search("  --link: #0374B6;"), (
        "The Canvas-blue reader flags `#0374B6`, which is not the host's colour. A reader that "
        "matches near values refuses palettes this rule says nothing about."
    )

    # The wider sweep runs over everything tracked under `frontend/`, and that has
    # been one file — the workspace stub — since E1-02. So the precondition is the
    # source tree rather than the package: a rule enforced over a package with no
    # application in it is not enforced, and a green line saying so would be this
    # module's own subject.
    require_a_scanned_tree(source_files(), FRONTEND_SOURCE, "the host's blue")
    scanned = frontend_files()
    require_a_scanned_tree(scanned, FRONTEND, "the host's blue")

    offenders = {
        path.relative_to(REPO_ROOT): lines
        for path in scanned
        if (lines := offending_lines(path, CANVAS_BLUE))
    }

    assert not offenders, "\n".join(
        [
            "These files borrow Canvas blue:",
            *(
                f"  {name}:{number}: {line}"
                for name, lines in sorted(offenders.items())
                for number, line in lines
            ),
            "",
            "`docs/DESIGN_BRIEF.md`, under the anti-slop guardrails: 'Interactive elements never "
            "use Canvas blue (#0374B5) — the host owns that color; borrowing it confuses what "
            "belongs to whom.'",
            "",
            "The accent this product has is marigold, and it is the one hero colour: the current "
            "section's line and dot, focus rings, selected states (`design/Usage Rules.md` §2).",
        ]
    )


def test_no_font_declaration_names_a_face_the_design_brief_forbids() -> None:
    """`docs/DESIGN_BRIEF.md`, hard rule: no Inter, Roboto, Arial or Lato.

    "No Inter, Roboto, Arial, Lato, or system font stacks anywhere. (Canvas chrome
    is Lato — the type contrast is how the tool reads as its own considered thing
    inside the host.)" The three faces this product uses are named in
    `design/tokens.css`: Literata for display, Schibsted Grotesk for body, Spline
    Sans Mono for data.

    **Declarations, not text.** "Inter" is a substring of "interface", of
    "interval", and of the first word of the design brief's own sentence about
    Canvas blue. So the reader looks at `font-family:` and `--font*:` declarations
    and at the value side of them, and the two near misses below are run before
    the tree is swept.

    **The four names, and not the brief's wider sentence.** A rule against "system
    font stacks" would refuse `design/tokens.css` itself, every family in which
    ends in one — `'Literata', Georgia, serif`. Asserting more than the criterion
    would make this test the author of a rule nobody agreed to.

    **What this does not reach:** a face declared in JavaScript rather than in CSS
    — a Tailwind config object with `fontFamily: { sans: ['Inter'] }`. Tailwind 4
    puts its theme in CSS custom properties, which the `--font*` half of the
    pattern reads, so the gap is narrow rather than absent; it is stated because a
    reader who assumed otherwise would trust this further than it goes.

    **The mutation this kills:** add `font-family: Inter, sans-serif` to a landing
    view or to a global stylesheet — which is what a scaffold generated from a
    default template ships with, and therefore the way this arrives. **The near
    misses that must stay green:** `'Helvetica Neue'` in the body fallback, which
    the brief does not name; and any identifier or sentence containing one of the
    four words outside a font declaration.
    """
    assert forbidden_faces_in(FORBIDDEN_FONT_DECLARATION) == ["Inter"], (
        f"The font reader does not refuse {FORBIDDEN_FONT_DECLARATION.strip()!r}, which is the "
        "declaration a generated scaffold ships and the one thing this test exists to catch."
    )
    assert not forbidden_faces_in(ALLOWED_FONT_DECLARATION), "\n".join(
        [
            "The font reader refuses a declaration copied whole out of `design/tokens.css`:",
            f"  {ALLOWED_FONT_DECLARATION.strip()}",
            "",
            "That is the body face this product uses, with the fallback the token file ships. A "
            "reader that refuses it fails the ticket for following the design system.",
        ]
    )
    assert not font_offences_in_text(IDENTIFIER_CONTAINING_A_FACE), (
        f"The font reader reports a typeface in {IDENTIFIER_CONTAINING_A_FACE.strip()!r}. "
        "`setInterval` contains `Inter`, and so does the design brief's own sentence about Canvas "
        "blue; a reader that searches text rather than declarations refuses ordinary TypeScript."
    )
    assert not font_offences_in_text(CANVAS_BLUE_IN_PROSE), (
        "The font reader reports a typeface in the design brief's sentence about Canvas blue, "
        "which begins with the word 'Interactive'. That sentence is the other rule this module "
        "enforces, and a reader that cannot tell the two apart would refuse the document it is "
        "reading its rules out of."
    )

    # As above: the package has held one file since E1-02, so the source tree is
    # what decides whether this rule has anything to be enforced over.
    require_a_scanned_tree(source_files(), FRONTEND_SOURCE, "forbidden typefaces")
    scanned = frontend_files()
    require_a_scanned_tree(scanned, FRONTEND, "forbidden typefaces")

    offenders = {
        path.relative_to(REPO_ROOT): found for path in scanned if (found := font_offences(path))
    }

    assert not offenders, "\n".join(
        [
            "These font declarations name a face `docs/DESIGN_BRIEF.md` forbids:",
            *(
                f"  {name}:{number}: {line}  -> {faces}"
                for name, found in sorted(offenders.items())
                for number, line, faces in found
            ),
            "",
            "'No Inter, Roboto, Arial, Lato, or system font stacks anywhere. (Canvas chrome is "
            "Lato — the type contrast is how the tool reads as its own considered thing inside the "
            "host.)'",
            "",
            "`design/tokens.css` names the three faces this product uses and the jobs they do: "
            "Literata for display, Schibsted Grotesk for body, Spline Sans Mono for every number. "
            "A component reaches them through `--font-display`, `--font-body` and `--font-mono`.",
        ]
    )
