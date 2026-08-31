"""A door page's focus indicator is visible against the page it is drawn on.

WCAG 2.2 SC 1.4.11 (non-text contrast) puts a 3:1 floor under a focus indicator
against its adjacent colours. `design/tokens.css` already carries that ruling and
the measurement behind it: the hero accent `--marigold` (`#DFA320`) measures
2.1:1 on `--chalk` and 2.2:1 on `--paper`, so the shipped focus ring is
`--marigold-deep` (`#8F6A10`) at 4.6:1 and 5.0:1. The E1 boundary review recorded
it as M10 and the fix landed in the design tokens.

**The door pages did not get that fix, because they cannot read those tokens.**
They are answered before any session exists and must render without the SPA
bundle, so `backend/app/api/deps.py` hand-inlines its own copy of the palette —
deliberately, with a comment saying why. A hand-inlined copy is a second place
the same decision is written, and this is the recurrence `docs/MISTAKES.md`
entry 13 is about: the hazard was written down and worked around in one of the
two places facing it. The re-review of 2026-08-31 found the door template's
`:focus-visible` rule still pointing at the accent.

**Judged as a property, never as a hex.** This computes the WCAG relative
luminance of the colour the rule actually resolves to and the colour of every
surface the template actually paints, and asserts the ratio. Pinning `#8F6A10`
would be holding the expectation in a copy of the thing being checked
(`docs/MISTAKES.md` entry 19) and would make an honest future palette change read
as a regression; the floor is the rule, and the rule is what is asserted.

**Every door page, not one.** The re-review's other finding on this ring was that
the design-token fix left two hand-copied duplicates of the superseded colour
behind, which is exactly what a per-surface copy of a palette produces. So all
four pages either door can answer with are judged, and a fix applied to one copy
and not another is red on the page that was missed rather than green on the one
that was not.

**What this cannot see**, said out loud rather than left to look like coverage
(`docs/MISTAKES.md` entry 14). It reads the stylesheet, not a rendering: it
cannot know which surface a given focusable element actually sits on, so it holds
the ring to the floor against *every* solid background the page paints, plus the
page background token itself. That is stricter than a browser would be if the
template ever paints a dark surface nothing focusable sits on. If that day comes,
the answer is to name the surfaces focusable content sits on, in the open, with
the reason beside it — never to lower the 3.0.

**This module is not marked `invariant`.** It asserts nothing about what a
student can see; it is an accessibility rule, and SPEC §4.1's isolated pass is
for the confidentiality invariants.
"""

import importlib
import inspect
import re
from typing import Any

import pytest

# The four answers either door can give that are not a landing, spelled as
# `tests/fixtures/landing.py`'s D5 note spells them: "`PAGE`, `refusal_page`,
# `cancelled_page`, `no_account_page` and the new `no_access` move into"
# `app.api.deps`. All four compose the same door template, which is where the
# palette and the focus rule are inlined; four cases rather than one because a
# hand-copied palette is exactly the thing that gets fixed in one copy.
DOOR_PAGES = ("refusal_page", "no_access", "cancelled_page", "no_account_page")

# SC 1.4.11's floor for a focus indicator against its adjacent colours.
CONTRAST_FLOOR = 3.0

# The page-background token, which is asserted to be judged against whatever else
# the template paints. Named because `design/tokens.css` calls it "App/page
# background" and the boundary review measured the accent against it (2.09:1).
PAGE_BACKGROUND_TOKEN = "--chalk"  # noqa: S105 - a CSS custom-property name, not a credential

# What is handed to any parameter a page takes. A real guard name, so a page that
# keys its copy off one finds an entry rather than a default, and so nothing here
# depends on which parameter is which — this module is about the stylesheet, and
# `tests/unit/test_the_refusal_page_repeats_nothing_it_was_handed.py` is where
# what a page does with its arguments is settled.
A_GUARD_NAME = "SignatureRefused"

STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

# CSS comments, removed before anything is parsed. The template's palette carries
# its reasoning beside it — `design/tokens.css` writes the measured ratios into a
# comment above the focus rule — and a hex inside that prose is not a colour
# anything paints. This is the same precaution
# `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` takes over
# the view catalog, for the same reason: a commented-out rule defines nothing.
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# A flat CSS rule: everything up to a `{`, and everything inside it. Nested
# at-rules are not matched as a unit, and their inner rules are found on their
# own, which is all this module needs from them.
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")

DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;]+)")

# `var(--name)` and `var(--name, fallback)`. The fallback is read because a
# hand-inlined palette is exactly where somebody writes one.
VAR_REFERENCE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*?)\s*)?\)")

HEX_COLOUR = re.compile(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})\b")

BACKGROUND_PROPERTIES = ("background-color", "background")
OUTLINE_PROPERTIES = ("outline-color", "outline")

FOCUS_SELECTOR = ":focus-visible"
ROOT_SELECTOR = ":root"

# How many times a `var()` may point at another before this gives up. A palette
# is one level deep; the cap is what stops a cycle from hanging the suite.
RESOLUTION_DEPTH = 8


def door_page(module_name: str, page_name: str) -> Any:
    """One door page out of `app.api.deps`, or a failure naming where it was looked for."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{module_name}` does not import ({missing}). E1-13 gathers the door pages there."
        )
    page = getattr(module, page_name, None)
    assert callable(page), (
        f"`{module_name}` exposes no callable `{page_name}`; it exposes "
        f"{sorted(name for name in vars(module) if not name.startswith('_'))}. The four door "
        f"pages {list(DOOR_PAGES)} are what either door answers with when it answers no landing."
    )
    return page


def render(page: Any, page_name: str) -> str:
    """Call `page` with a string for every parameter it takes, and answer the markup.

    The signature is read rather than assumed: three of these pages take nothing
    and one takes the guard name, and which is which is settled next door rather
    than here.
    """
    signature = inspect.signature(page)
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(A_GUARD_NAME)
        else:
            keyword[parameter.name] = A_GUARD_NAME
    try:
        rendered = page(*positional, **keyword)
    except Exception as failure:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{page_name}` raised {type(failure).__name__}: {failure} when called with a string "
            f"for each of {list(signature.parameters)}. A parameter that cannot take a string is "
            "an interface question for the pull request, not a pass."
        )
    return body_of(rendered, page_name)


def body_of(rendered: Any, page_name: str) -> str:
    """The markup a page answered with, whatever kind of object it answered with."""
    body = getattr(rendered, "body", None)
    if isinstance(body, bytes | bytearray):
        return bytes(body).decode("utf-8", "replace")
    if isinstance(body, str):
        return body
    if isinstance(rendered, str):
        return rendered
    text = str(rendered)
    assert "<" in text, (
        f"`{page_name}` answered {rendered!r}, which carries no `body` and does not look like "
        "markup, so this module cannot read the stylesheet a browser would be handed."
    )
    return text


def stylesheet(markup: str) -> str:
    """Every inline `<style>` block in the page, concatenated in document order.

    Inline only, and that is the subject rather than a limitation: the door pages
    render before any session exists and deliberately do not depend on the SPA
    bundle, so whatever styles them is in the document. Comments are blanked, so
    a hex quoted in the prose beside a rule is not read as a colour.
    """
    return CSS_COMMENT.sub(" ", "\n".join(STYLE_BLOCK.findall(markup)))


def rules(css: str) -> list[tuple[str, str]]:
    """Every flat rule in `css`, as its selector text and its declaration block."""
    return [(selector.strip(), block) for selector, block in CSS_RULE.findall(css)]


def declarations(block: str) -> list[tuple[str, str]]:
    """Every `property: value` in one declaration block, in order."""
    return [(name.strip().lower(), value.strip()) for name, value in DECLARATION.findall(block)]


def custom_properties(css: str) -> dict[str, str]:
    """The custom properties the page's own `:root` declares.

    Read out of `:root` rather than out of the whole sheet, because that is where
    the template's inlined palette lives and because a property redeclared under
    a media query answers a question about a different rendering.
    """
    found: dict[str, str] = {}
    for selector, block in rules(css):
        if ROOT_SELECTOR not in selector:
            continue
        for name, value in declarations(block):
            if name.startswith("--"):
                found[name] = value
    return found


def as_hex(colour: str) -> str | None:
    """`colour` as a six-digit lowercase hex, or `None` if it is not a solid one.

    `rgba()`, `transparent`, `currentColor`, a gradient and an eight-digit hex all
    answer `None`: none of them is a colour this module can put a luminance on,
    and guessing at one would be inventing the value under test.
    """
    match = HEX_COLOUR.fullmatch(colour.strip())
    if match is None:
        return None
    digits = match.group(1).lower()
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return f"#{digits}"


def resolve(value: str, palette: dict[str, str]) -> str | None:
    """The solid colour `value` resolves to through `palette`, or `None`.

    A declaration is a list of terms — `2px solid var(--marigold)` — so the colour
    is the first term that resolves to one. `var()` is followed through the
    palette, and its written fallback is used when the palette has no entry.
    """
    current = value
    for _ in range(RESOLUTION_DEPTH):
        direct = as_hex(current)
        if direct is not None:
            return direct
        reference = VAR_REFERENCE.search(current)
        if reference is not None:
            name, fallback = reference.group(1), reference.group(2)
            if name in palette:
                current = palette[name]
                continue
            if fallback:
                current = fallback
                continue
            return None
        literal = HEX_COLOUR.search(current)
        if literal is not None:
            return as_hex(literal.group(0))
        return None
    return None


def declared(block: str, properties: tuple[str, ...]) -> str | None:
    """The value of the last declaration in `block` naming one of `properties`.

    The last, because that is the one that wins, and the whole tuple in one pass
    so that `outline-color` written after `outline` is what is read.
    """
    found: str | None = None
    for name, value in declarations(block):
        if name in properties:
            found = value
    return found


def focus_outline_colours(css: str, palette: dict[str, str]) -> dict[str, str | None]:
    """The colour each `:focus-visible` rule draws its outline in, by selector.

    `None` for a rule that declares an outline this module cannot resolve to a
    solid colour — reported rather than dropped, because a rule silently skipped
    is a rule this file has stopped judging.
    """
    found: dict[str, str | None] = {}
    for selector, block in rules(css):
        if FOCUS_SELECTOR not in selector:
            continue
        value = declared(block, OUTLINE_PROPERTIES)
        if value is None:
            continue
        found[selector] = resolve(value, palette)
    return found


def painted_backgrounds(css: str, palette: dict[str, str]) -> dict[str, str]:
    """Every solid background colour the stylesheet paints, by the selector painting it."""
    found: dict[str, str] = {}
    for selector, block in rules(css):
        value = declared(block, BACKGROUND_PROPERTIES)
        if value is None:
            continue
        colour = resolve(value, palette)
        if colour is not None:
            found[selector] = colour
    return found


def relative_luminance(colour: str) -> float:
    """WCAG 2.x relative luminance of a six-digit hex colour."""
    channels = []
    for offset in (1, 3, 5):
        raw = int(colour[offset : offset + 2], 16) / 255
        channels.append(raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(one: str, other: str) -> float:
    """The WCAG contrast ratio between two six-digit hex colours."""
    first, second = relative_luminance(one), relative_luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("page_name", DOOR_PAGES)
def test_the_door_pages_focus_indicator_meets_the_non_text_contrast_floor(
    landing_contract: Any, configured_env: dict[str, str], page_name: str
) -> None:
    """SC 1.4.11: the focus ring measures at least 3:1 against what it is drawn on.

    The door template inlines its own palette because it must render without the
    SPA bundle, and a hand-inlined copy is a second home for a decision
    `design/tokens.css` already made: the hero accent is under the floor for a
    focus indicator, so the ring is the deep variant. That correction reached the
    tokens and not this copy.

    Nothing focusable renders on these pages in E1, which is why it is latent and
    not a defect anybody has met. It is also why it is worth asserting now: the
    first control any of these pages grows inherits whatever the template says
    today, and a focus ring nobody can see is not a thing a reviewer notices in a
    diff about something else.

    **The mutation this kills**: the `:focus-visible` rule pointing at the accent
    — `var(--marigold)`, `#DFA320`, or any hand-copied duplicate of it — which is
    the state of the template as this test is written and measures 2.09:1 on the
    page background. It kills a too-pale replacement just as surely, because the
    assertion is a computed ratio and not an equality against a value: a "deep"
    variant that is not deep enough fails with its own number printed.

    **The near miss it tolerates**: the accent staying exactly where it belongs
    everywhere else in the template. Only a rule whose selector carries
    `:focus-visible` is judged here, so a marigold heading rule, a marigold border
    or a marigold link is untouched by this test — `docs/DESIGN_BRIEF.md` calls
    the accent the hero and this is not a rule against using it.

    **Three controls, because a scan for a bad ratio is satisfied by finding no
    ratios at all.** The page must render markup with a stylesheet in it; that
    stylesheet must declare the page-background token, so this is judging a real
    surface; and at least one `:focus-visible` rule must resolve to a solid
    colour. A page with no focus rule is not a page that passes — it is a page
    with no visible focus indicator at all, which fails SC 2.4.7 instead, and it
    is reported here rather than counted as silence.
    """
    page = door_page(landing_contract.deps_module, page_name)

    markup = render(page, page_name)
    css = stylesheet(markup)

    assert css.strip(), (
        f"`{page_name}` rendered no inline `<style>` block, so there is no focus rule to measure "
        "and every assertion below is about nothing. These pages are answered before any session "
        "exists and cannot reach the SPA bundle, so whatever styles them is in the document."
    )

    palette = custom_properties(css)
    background = palette.get(PAGE_BACKGROUND_TOKEN)
    page_background = resolve(background, palette) if background else None
    assert page_background is not None, (
        f"`{page_name}`'s inline `:root` declares no resolvable `{PAGE_BACKGROUND_TOKEN}`; it "
        f"declares {sorted(palette)}. That token is the page background "
        '(`design/tokens.css`: "App/page background") and it is the surface the boundary review '
        "measured the accent against at 2.09:1. Without it this test would be judging the ring "
        "against whatever the template happened to paint, which may be nothing at all."
    )

    outlines = focus_outline_colours(css, palette)
    assert outlines, (
        f"`{page_name}` declares no `{FOCUS_SELECTOR}` rule with an outline this module can "
        "resolve to a solid colour. That is not a pass: a page with no focus indicator fails "
        "SC 2.4.7 rather than satisfying SC 1.4.11, and a rule whose colour cannot be resolved is "
        "a rule this test has stopped judging. The stylesheet read was:\n\n"
        f"{css}"
    )
    unresolved = sorted(selector for selector, colour in outlines.items() if colour is None)
    assert not unresolved, (
        f"The outline colour of {unresolved} on `{page_name}` did not resolve to a solid colour "
        f"through the inline palette {sorted(palette)}. A ratio cannot be computed for it, and a "
        "rule silently skipped is a rule nothing is holding to the floor."
    )

    surfaces = {f"{PAGE_BACKGROUND_TOKEN} (the page background)": page_background}
    surfaces.update(painted_backgrounds(css, palette))

    failures = [
        f"  {selector} drawn in {colour} on {where} ({surface}): {contrast(colour, surface):.2f}:1"
        for selector, colour in outlines.items()
        if colour is not None
        for where, surface in sorted(surfaces.items())
        if contrast(colour, surface) < CONTRAST_FLOOR
    ]
    assert not failures, "\n".join(
        [
            f"`{page_name}`'s focus indicator is under SC 1.4.11's {CONTRAST_FLOOR}:1 floor for "
            "non-text contrast:",
            *failures,
            "",
            "`design/tokens.css` already carries this ruling and the measurement behind it: the "
            "hero accent `--marigold` (#DFA320) is 2.1:1 on chalk and 2.2:1 on paper, so the "
            "shipped ring is `--marigold-deep` (#8F6A10) at 4.6:1 and 5.0:1. The door pages inline "
            "their own copy of the palette — deliberately, because they render without the SPA "
            "bundle — and that copy did not get the fix. `docs/MISTAKES.md` entry 13: a hazard "
            "written down and worked around in only one of the two places facing it.",
            "",
            "The repair is in `backend/app/api/deps.py`: add the deep variant to the inlined "
            "palette and point the `:focus-visible` rule at it. Not a lower floor here — 3:1 is "
            "the success criterion, not this file's opinion — and not a pinned hex either, since "
            "what is asserted is the measured ratio and a future palette is judged the same way.",
            "",
            "Only rules whose selector carries `:focus-visible` are judged. The accent staying the "
            "hero everywhere else in this template is not what failed above.",
        ]
    )
