"""E5.1-03 criterion 5 — the token values have one source.

> Both pages use one design-token CSS block, and a test reads its values from
> `design/tokens.css`.

The door pages (`backend/app/api/deps.py`) and the development console
(`backend/app/api/dev.py`) each render without the SPA bundle, so each inlines
the design tokens it needs. Until this ticket each held its own copy of the
palette, and a hand-copied palette is the shape
`tests/unit/test_the_door_page_focus_ring_meets_the_contrast_floor.py` was
written about: the focus-ring fix reached `design/tokens.css` and not the copy.
Ruling R6 of the work order gives `deps.py` one constant, `DESIGN_TOKENS_CSS` —
one `:root` rule holding the custom properties both pages use — which the door
template takes through a format field and `dev.py`'s `STYLE` begins with.

**What is asserted, and where each expectation comes from.**

  - Every `--name: value` the block declares is the value `design/tokens.css`
    declares for that name. The expectation is read out of `design/tokens.css`
    at run time, never written here (`docs/MISTAKES.md` entry 19): rewording a
    token there and nowhere else is a red, which is the point.
  - Every door page and the console's stylesheet contain the block, declare no
    custom property outside it, and reference no custom property it does not
    declare. The last is what "both pages use one block" means in a form a
    browser would notice: a `var(--x)` the block lacks renders as nothing.

**How values are compared.** Whitespace is normalised, hex digits are compared
case-insensitively, and the two quote characters are treated as one — a font
name in `"..."` and in `'...'` is the same CSS. Nothing else is forgiven: `.06`
and `0.06` are different spellings, and R6 settles the spelling as the one
`design/tokens.css` uses.

**The controls come first.** The token parser must read the real
`design/tokens.css` and find `--chalk` in it, and the comparison must name a
planted wrong value while leaving a correctly spelled one alone. The samples
are written here. **A red in a control means these tests are broken, not the
code.**

**A missing token block is a FAILED, not an error.** Every rule fails by name if
`app.api.deps.DESIGN_TOKENS_CSS` is gone — a plain call in each test body, never
a fixture (`docs/MISTAKES.md` entry 44).

**Not marked `invariant`.** This is a design-system rule, not a SPEC §4.1 one,
for the reason the focus-ring module gives about itself.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENS_PATH = REPO_ROOT / "design" / "tokens.css"

DEPS_MODULE = "app.api.deps"
DEV_MODULE = "app.api.dev"
BLOCK_NAME = "DESIGN_TOKENS_CSS"
CONSOLE_STYLE_NAME = "STYLE"

# The four answers either door gives that are not a landing, spelled as
# `tests/unit/test_the_door_page_focus_ring_meets_the_contrast_floor.py` spells
# them. Each composes the one door template, which is where the block goes.
DOOR_PAGES = ("refusal_page", "no_access", "cancelled_page", "no_account_page")

# Handed to any parameter a page takes. A real guard name, so a page keying its
# copy off one renders a mapped entry rather than raising.
A_GUARD_NAME = "SignatureRefused"

# The canary token: the page background, certainly declared in
# `design/tokens.css` and certainly used by both pages.
CANARY_TOKEN = "--chalk"  # noqa: S105 - a CSS custom-property name, not a credential

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
ROOT_RULE = re.compile(r":root\s*\{([^{}]*)\}")
CUSTOM_PROPERTY = re.compile(r"(--[\w-]+)\s*:\s*([^;{}]+?)\s*(?:;|(?=\}))")
DECLARED_NAME = re.compile(r"(--[\w-]+)\s*:")
REFERENCED_NAME = re.compile(r"var\(\s*(--[\w-]+)")
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
HEX = re.compile(r"#[0-9A-Fa-f]+")

# ---------------------------------------------------------------------------
# Samples. Written here; the values are chosen to sit beside the real ones
# without being them, so a comparison that passed them would be comparing
# nothing.
# ---------------------------------------------------------------------------

A_SAMPLE_TOKENS_FILE = "\n".join(
    [
        "/* a sample tokens file */",
        ":root {",
        "  --sample-ink: #1A2B3C;     /* a comment on the line,",
        "                               carried onto the next */",
        "  --sample-font: 'Sample Serif', Georgia, serif;",
        "  --sample-shadow: 0 1px 2px rgba(1, 2, 3, .5);",
        "}",
        "",
        ":focus-visible { outline: 2px solid var(--sample-ink); }",
    ]
)

A_MATCHING_BLOCK = (
    ":root { color-scheme: light; --sample-ink: #1a2b3c; "
    '--sample-font: "Sample Serif",  Georgia, serif; '
    "--sample-shadow: 0 1px 2px rgba(1,2,3,.5); }"
)

A_WRONG_BLOCK = ":root { --sample-ink: #1A2B3D; --sample-invented: 4px; }"

A_PAGE_WITH_A_STRAY_DECLARATION = (
    A_MATCHING_BLOCK + " .card { --sample-local: 8px; color: var(--sample-ink); }"
)
A_PAGE_REFERENCING_AN_UNDECLARED_TOKEN = (
    A_MATCHING_BLOCK + " .card { color: var(--sample-missing); border: var(--sample-ink); }"
)


# ---------------------------------------------------------------------------
# The readers.
# ---------------------------------------------------------------------------


def without_comments(css: str) -> str:
    """`css` with every comment blanked, so prose beside a token is never read as one."""
    return CSS_COMMENT.sub(" ", css)


def custom_properties_in(css: str) -> dict[str, str]:
    """Every `--name: value` in `css`, comments removed, the last declaration winning."""
    return {name: value.strip() for name, value in CUSTOM_PROPERTY.findall(without_comments(css))}


def root_tokens(css: str) -> dict[str, str]:
    """The custom properties a tokens file's `:root` rules declare."""
    found: dict[str, str] = {}
    for block in ROOT_RULE.findall(without_comments(css)):
        found.update(custom_properties_in(block))
    return found


def normalised(value: str) -> str:
    """A value as R6 compares it: whitespace collapsed, hex lowercased, quotes unified."""
    value = value.replace('"', "'")
    value = HEX.sub(lambda match: match.group(0).lower(), value)
    value = " ".join(value.split())
    value = re.sub(r"\s*([,()])\s*", r"\1", value)
    return value


def disagreements(block: dict[str, str], tokens: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Every name the block declares with a value the tokens file does not, or does not declare.

    A name the tokens file has never heard of is a disagreement too: it is a
    value nothing in the design system decided.
    """
    return {
        name: (value, tokens.get(name, "<not declared in design/tokens.css>"))
        for name, value in block.items()
        if name not in tokens or normalised(value) != normalised(tokens[name])
    }


def declared_outside(css: str, block: str) -> list[str]:
    """Every custom property `css` declares anywhere but inside `block`."""
    remainder = without_comments(css.replace(block, " ", 1))
    return sorted(set(DECLARED_NAME.findall(remainder)))


def referenced_but_not_declared(css: str, block: str) -> list[str]:
    """Every `var(--name)` in `css` whose name the block does not declare."""
    declared = set(custom_properties_in(block))
    return sorted(
        {name for name in REFERENCED_NAME.findall(without_comments(css)) if name not in declared}
    )


def design_tokens() -> dict[str, str]:
    """`design/tokens.css`'s `:root` tokens, or a failure naming the file."""
    if not TOKENS_PATH.is_file():
        pytest.fail(
            f"{TOKENS_PATH.relative_to(REPO_ROOT)} does not exist. It is the design system's "
            "single source of truth for the tokens, and R6's comparison reads it."
        )
    return root_tokens(TOKENS_PATH.read_text(encoding="utf-8"))


def module(name: str) -> Any:
    """An application module, or a failure naming the one that does not import."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == name or name.startswith(f"{absent}.")):
            raise
        pytest.fail(f"`{name}` does not exist; the door pages and the console live there.")


def design_tokens_css() -> str:
    """`app.api.deps.DESIGN_TOKENS_CSS`, or a failure naming the deliverable."""
    value = getattr(module(DEPS_MODULE), BLOCK_NAME, None)
    if not isinstance(value, str) or not value.strip():
        pytest.fail(
            f"`{DEPS_MODULE}` exposes no non-empty `{BLOCK_NAME}` (it holds {value!r}). E5.1-03's "
            "ruling R6 puts the one design-token block there: a single `:root` rule holding every "
            "custom property the door pages and the console use, spelled as `design/tokens.css` "
            "spells it, which the door template takes through a format field and `dev.py`'s "
            "`STYLE` begins with."
        )
    return value


def body_of(rendered: Any, page_name: str) -> str:
    """The markup a page answered with, whatever kind of object it answered with."""
    body = getattr(rendered, "body", None)
    if isinstance(body, bytes | bytearray):
        return bytes(body).decode("utf-8", "replace")
    if isinstance(body, str):
        return body
    if isinstance(rendered, str):
        return rendered
    pytest.fail(f"`{page_name}` answered {rendered!r}, which carries no markup this can read.")


def rendered_door_page(page_name: str) -> str:
    """One door page, rendered with a guard name for every parameter it takes."""
    page = getattr(module(DEPS_MODULE), page_name, None)
    if not callable(page):
        pytest.fail(f"`{DEPS_MODULE}` exposes no callable `{page_name}`.")
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for parameter in inspect.signature(page).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(A_GUARD_NAME)
        else:
            keyword[parameter.name] = A_GUARD_NAME
    return body_of(page(*positional, **keyword), page_name)


def stylesheet_of(target: str) -> str:
    """The CSS one page carries: a door page's inline `<style>`, or the console's `STYLE`."""
    if target == CONSOLE_STYLE_NAME:
        style = getattr(module(DEV_MODULE), CONSOLE_STYLE_NAME, None)
        if not isinstance(style, str) or not style.strip():
            pytest.fail(
                f"`{DEV_MODULE}` exposes no non-empty `{CONSOLE_STYLE_NAME}`. R6 has the console's "
                f"stylesheet begin with `{BLOCK_NAME}`."
            )
        return style
    return "\n".join(STYLE_BLOCK.findall(rendered_door_page(target)))


# Every page R6 governs: the four door answers, and the console's stylesheet.
PAGES = (*DOOR_PAGES, CONSOLE_STYLE_NAME)


# ---------------------------------------------------------------------------
# Controls. A red here means these tests are broken, not the code.
# ---------------------------------------------------------------------------


def test_the_token_parser_reads_a_tokens_file_written_the_way_the_real_one_is() -> None:
    """A `:root` with trailing comments, a comment carried over two lines, a font stack.

    **The mutation it kills:** a parser that keeps a trailing comment in the
    value, or that reads the `:focus-visible` rule's `var(...)` as a token. **A
    red here means this module is broken, not that the code is.**
    """
    read = root_tokens(A_SAMPLE_TOKENS_FILE)
    assert read == {
        "--sample-ink": "#1A2B3C",
        "--sample-font": "'Sample Serif', Georgia, serif",
        "--sample-shadow": "0 1px 2px rgba(1, 2, 3, .5)",
    }, f"The parser read {read} out of the sample tokens file."


def test_the_token_parser_finds_the_canary_in_the_real_design_tokens() -> None:
    """The real `design/tokens.css` parses, and `--chalk` is in it.

    A comparison against an empty expectation agrees with every block
    (`docs/MISTAKES.md` entry 3), so the expectation is required to hold the
    token both pages certainly use. **The mutation it kills:** a parser that
    finds no `:root` in the real file. **A red here means this module is
    broken, or `design/tokens.css` lost its page background.**
    """
    tokens = design_tokens()
    assert CANARY_TOKEN in tokens, (
        f"The parser read {sorted(tokens)} out of {TOKENS_PATH.relative_to(REPO_ROOT)}, without "
        f"`{CANARY_TOKEN}`, the page background every surface paints."
    )


def test_the_comparison_accepts_a_respelled_value_and_names_a_wrong_one() -> None:
    """Both directions of R6's comparison, on samples.

    **Accepted:** the same values with lowercased hex, the other quote
    character, doubled spaces and no spaces after commas. **Refused:** one hex
    digit off, and a token the tokens file never declared. **The mutation it
    kills:** an exact-string comparison, which is red against a correct block
    for a cosmetic reason; and a comparison that reads only the names the tokens
    file declares, which passes an invented token. **A red here means this
    module is broken.**
    """
    tokens = root_tokens(A_SAMPLE_TOKENS_FILE)
    accepted = disagreements(custom_properties_in(A_MATCHING_BLOCK), tokens)
    assert accepted == {}, f"The comparison refused a correctly spelled block: {accepted}."

    refused = disagreements(custom_properties_in(A_WRONG_BLOCK), tokens)
    assert sorted(refused) == ["--sample-ink", "--sample-invented"], (
        f"The comparison named {sorted(refused)} in a block holding one wrong value and one "
        "invented token; it should name both and nothing else."
    )


def test_the_page_readers_name_a_stray_declaration_and_an_undeclared_reference() -> None:
    """A custom property declared outside the block, and a `var()` the block lacks, are named.

    **The near miss:** `var(--sample-ink)` in a page rule is a use of the block,
    not a declaration and not a gap. **The mutation it kills:** a reader that
    counts `var(--name)` as a declaration, and one that cannot see past the
    block to the rest of the sheet. **A red here means this module is broken.**
    """
    stray = declared_outside(A_PAGE_WITH_A_STRAY_DECLARATION, A_MATCHING_BLOCK)
    assert stray == ["--sample-local"], f"The reader named {stray} as declared outside the block."
    missing = referenced_but_not_declared(A_PAGE_REFERENCING_AN_UNDECLARED_TOKEN, A_MATCHING_BLOCK)
    assert missing == ["--sample-missing"], f"The reader named {missing} as undeclared."


# ---------------------------------------------------------------------------
# The rules.
# ---------------------------------------------------------------------------


def test_every_token_the_block_declares_has_the_value_design_tokens_gives_it(
    configured_env: dict[str, str],
) -> None:
    """Criterion 5: the block's values are `design/tokens.css`'s values.

    **The mutation it kills:** a token copied wrong — the focus ring's
    superseded accent, a hex one digit off, a font stack missing a fallback —
    and a token invented beside the design system. **Its near miss** is a value
    respelled without being changed, which the comparison control above shows
    is accepted. The block is required to declare `--chalk` first: an empty
    block agrees with everything.

    `configured_env` is depended on and not used, for the reason the page tests
    below give.
    """
    block = design_tokens_css()
    declared = custom_properties_in(block)
    assert CANARY_TOKEN in declared, (
        f"`{BLOCK_NAME}` declares {sorted(declared)}, without `{CANARY_TOKEN}`. Both pages paint "
        "the page background, so a block without it is not the block both pages use."
    )
    wrong = disagreements(declared, design_tokens())
    assert not wrong, (
        f"These tokens in `{BLOCK_NAME}` do not say what `design/tokens.css` says, as (the block's "
        f"value, the design system's): {wrong}.\n\n"
        "The block is a copy of the design system's tokens for two pages that cannot load the SPA "
        "bundle. A copy that drifts is the defect the focus-ring test was written about; the fix is "
        "the value `design/tokens.css` gives, spelled the way it spells it."
    )


@pytest.mark.parametrize("target", PAGES)
def test_every_page_carries_the_one_token_block(
    target: str, configured_env: dict[str, str]
) -> None:
    """Criterion 5: each door page, and the console's stylesheet, contains the block itself.

    **The mutation it kills:** a page that keeps its own `:root` copy beside a
    block it no longer renders — which is what the console's `STYLE` held until
    this ticket. **Its near miss** is a page whose block is the same text
    reached through a different name, which this accepts: the criterion is one
    block, not one import.

    `configured_env` is depended on and not used: `app.api.deps` and
    `app.api.dev` are application modules, and anything they import may build
    a `Settings` (`docs/MISTAKES.md` entry 40).
    """
    block = design_tokens_css()
    css = stylesheet_of(target)
    assert block in css, (
        f"`{target}`'s stylesheet does not contain `{BLOCK_NAME}`. R6: the door template takes it "
        "through a format field and the console's `STYLE` begins with it. The stylesheet begins "
        f"{css[:300]!r}."
    )


@pytest.mark.parametrize("target", PAGES)
def test_no_page_declares_a_token_outside_the_block(
    target: str, configured_env: dict[str, str]
) -> None:
    """Criterion 5: no page declares a custom property anywhere but in the one block.

    **The mutation it kills:** a second `:root` left in a page beside the block,
    or a token redeclared in a page rule, either of which is a second home for a
    value and the next fix lands in one of them. **Its near miss** is a
    `var(--name)` use, which the reader control shows is not a declaration.
    """
    block = design_tokens_css()
    stray = declared_outside(stylesheet_of(target), block)
    assert not stray, (
        f"`{target}` declares {stray} outside `{BLOCK_NAME}`. Every token value has one source, "
        "and on these pages that source is the block."
    )


@pytest.mark.parametrize("target", PAGES)
def test_no_page_uses_a_token_the_block_does_not_declare(
    target: str, configured_env: dict[str, str]
) -> None:
    """Criterion 5's practical half: everything a page uses is in the block it carries.

    A `var(--name)` the block does not declare resolves to nothing in a browser:
    a missing colour, a missing font, a page that looks unstyled. R6's block is
    the union of what both pages use, and this is that word asserted. **The
    mutation it kills:** a token left out of the union because only one of the
    two pages uses it. **Its near miss** is a `var()` with the token declared,
    which the reader control leaves alone.
    """
    block = design_tokens_css()
    missing = referenced_but_not_declared(stylesheet_of(target), block)
    assert not missing, (
        f"`{target}` uses {missing}, and `{BLOCK_NAME}` declares none of them. The block holds the "
        "union of the custom properties both pages use; a use outside it renders as nothing."
    )
