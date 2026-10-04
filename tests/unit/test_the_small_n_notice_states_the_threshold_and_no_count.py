"""The suppression notice states the threshold and no count — ticket E5.1-01, criterion 6.

SPEC §5.2's concealment rule: below the threshold the instructor sees no chip, no
count and no flag-type hint. E5.1-01 makes the notice per stream, and a notice that
said how many students answered, or how many commented, would hand an instructor
the very number the threshold is hiding — in a stream of one commenter, "1 student
commented" is the whole disclosure. So the notice states the threshold and nothing
counted (work order D6): the body's only placeholder is `{threshold}`, and the
`responded` and `enrolled` props the component used to fill are removed.

**What is asserted, and what deliberately is not.** The placeholders, not the
sentence: the copy's wording is governed by its own modules and transcribed by the
end-to-end drives, and a unit test holding the sentence would go red on an edit
that changed nothing an instructor learns (`docs/MISTAKES.md` entry 19). What no
edit may do is add a count, and a count reaches static copy only as a placeholder.

**Read through the collector the copy inventory reads**, `collect_frontend_copy`,
so this module sees the strings that inventory sees. The inventory module itself is
E5.1-03's and is not touched here.

**Marked `invariant` at the module level** (E5.1-12, Part B item 2). A count on
this notice is SPEC §4.1 item 3's disclosure by another route: below the
threshold an instructor sees no raw comment, and "1 student commented" tells them
whose the summary is. So this module runs in the isolated §4.1 pass, where a skip
or an empty collection fails CI. Its name carries `_no_count`, which
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
now reads as a denial shape, so deleting the `pytestmark` line below turns that
sweep red (this module itself stays green, since the marker changes where it
runs and not what it asserts).
"""

import re

import pytest
from fixtures.copy_inventory import FRONTEND_COPY_DIRECTORY, collect_frontend_copy

pytestmark = pytest.mark.invariant

# The two keys the work order (D6) keeps exactly. The copy inventory exempts the
# body by key, which is why the keys may not move.
NOTICE_TITLE_KEY = "instructor_report_comments.small_n.title"
NOTICE_BODY_KEY = "instructor_report_comments.small_n.body"

# A `{placeholder}` hole, as the copy files spell one (`fixtures/copy_inventory.py`:
# `fillCopy()` "substitutes `{placeholder}` holes").
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

THE_ONE_PLACEHOLDER = "threshold"


def notice_copy() -> dict[str, str]:
    """The notice's two strings, by key, from the collector the inventory reads."""
    strings = collect_frontend_copy(FRONTEND_COPY_DIRECTORY)
    collected = {string.key: string.text for string in strings}
    missing = [key for key in (NOTICE_TITLE_KEY, NOTICE_BODY_KEY) if key not in collected]
    assert not missing, (
        f"The frontend copy collector read no {missing}. The work order (D6) keeps the notice's "
        "keys exactly, and the copy inventory exempts the body by key, so a moved key is a notice "
        "this module and that inventory both stop seeing."
    )
    return {key: collected[key] for key in (NOTICE_TITLE_KEY, NOTICE_BODY_KEY)}


def test_the_placeholder_pattern_finds_holes_and_nothing_else() -> None:
    """The control. **A red here means this module is broken, not the copy.**

    The assertions below are about which placeholders a string carries, so the
    pattern has to find a hole where there is one and none where there is not —
    or a body with a count in it reads clean.
    """
    assert PLACEHOLDER.findall("shown when at least {threshold} students comment") == ["threshold"]
    assert PLACEHOLDER.findall("{responded} of {enrolled} answered") == ["responded", "enrolled"]
    assert PLACEHOLDER.findall("No raw comments are shown here this week") == []


def test_the_notice_body_states_the_threshold_and_no_count() -> None:
    """The body's only placeholder is `{threshold}`.

    **The mutation it kills:** the old notice's `{responded}` / `{enrolled}`
    holes left in the body — a count of the week's respondents on a notice that
    now sits inside one stream's group, where it reads as that stream's — or any
    commenter count added beside the threshold. **The near miss it must survive:**
    the threshold itself, which the body states, and which is the configured number
    rather than a count of anybody.
    """
    body = notice_copy()[NOTICE_BODY_KEY]
    assert body.strip(), "The notice body is empty, so it states nothing at all."
    holes = PLACEHOLDER.findall(body)
    assert holes == [THE_ONE_PLACEHOLDER], (
        f"The notice body carries the placeholders {holes}: {body!r}.\n\n"
        "SPEC §5.2: below the threshold the instructor sees no count. The work order (D6) has the "
        f"notice state the threshold — `{{{THE_ONE_PLACEHOLDER}}}`, once — and no count of any kind, "
        "because a count on a stream's notice is the number of people the threshold is hiding."
    )


def test_the_notice_title_carries_no_placeholder() -> None:
    """The title is a fixed sentence: no count, and no threshold either.

    **The mutation it kills:** a count moved into the title when it was taken out of
    the body — the same disclosure in a larger font.
    """
    title = notice_copy()[NOTICE_TITLE_KEY]
    assert title.strip(), "The notice title is empty."
    assert PLACEHOLDER.findall(title) == [], (
        f"The notice title carries placeholders {PLACEHOLDER.findall(title)}: {title!r}. The work "
        "order (D6) gives it a fixed sentence; a filled title is where a count goes when it is "
        "taken out of the body."
    )
