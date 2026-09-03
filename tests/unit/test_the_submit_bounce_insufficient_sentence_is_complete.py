"""E2-15 item 2 / criterion 2 — the bounce sentence gets its missing complement, byte-exact.

`docs/tickets/e2/E2-15-student-surface-and-local-gate-repairs.md` scope item 2:

> `submit.bounce.insufficient` (`backend/app/copy/submit.py:88-95`) ships "…a
> few words on their own are too brief to." — a truncated infinitive on the
> epic's first student-visible surface, and no assertion pins the sentence.
> Repair the sentence and pin the shipped string (or its shape) where the copy
> tests live.

Criterion 2: "The shipped bounce sentence is complete English and a test pins
it." `docs/tickets/e2/boundary-review.md`'s exit-review finding: "the shipped
bounce sentence ends in a truncated infinitive ('are too brief to.') and
nothing pins the string."

**The replacement sentence is settled, not chosen here.** It changes only the
truncated infinitive ("to." → "to be useful."); the rest of the sentence,
including the quoted example and its register — it judges the words, never
the person — is unchanged. A test that asserted only "the sentence does not
end mid-infinitive" would leave the rest of the wording, and any accidental
change to it, unpinned; the pin below is byte-exact for that reason.

**This is a unit test with no database and no application, on purpose** —
`app.copy` is a package of constants (see
`tests/unit/test_the_submit_paths_copy_is_externalised.py`'s own module
docstring), and a test that needed `Settings` or a built application to state
one sentence would be a defect worth its own failure.

**What this test does not do.** It does not re-run §4.1 item 1's comparison
sweep or the shaming sweep — those are
`tests/unit/test_the_submit_paths_copy_is_externalised.py`'s, which E2-14
owns this round and which this ticket's work order forbids editing. This
module asserts one thing only: the exact text shipped under one key.
"""

import importlib
from collections.abc import Mapping
from typing import Any

import pytest
from fixtures.submit import COPY_MAPPING_NAME, SUBMIT_COPY_MODULE

# E2-15's own settled name for the entry, transcribed from the ticket's scope
# item 2 and from `docs/tickets/e2/E2-15-student-surface-and-local-gate-repairs.md`'s
# work order ("the pin test asserts the shipped
# `COPY["submit.bounce.insufficient"].text` equals this string exactly").
BOUNCE_INSUFFICIENT_KEY = "submit.bounce.insufficient"

# The settled replacement, byte-exact, transcribed from the work order rather
# than composed here: only the truncated infinitive changes ("to." → "to be
# useful."); everything else — the quoted example, the register — is
# unchanged.
EXPECTED_SENTENCE = (
    "A sentence about your week is what counts here, and a few words on their own "
    'are too brief to be useful. Something like "the pacing in week 3 was too fast" '
    "gives your instructor a specific thing to act on."
)


def bounce_insufficient_entry() -> Any:
    """The `CopyEntry` shipped under `submit.bounce.insufficient`, or a named failure.

    Read directly off `app.copy.submit`'s own `COPY` mapping rather than
    through the discovery walk `tests/unit/test_the_submit_paths_copy_is_externalised.py`
    builds, because that module is E2-14's this round and this one may not
    import from it (the partition in E2-15's work order). `SUBMIT_COPY_MODULE`
    and `COPY_MAPPING_NAME` are E2-08's own settled names, transcribed in
    `tests/fixtures/submit.py` and imported from there rather than respelled.
    """
    try:
        module = importlib.import_module(SUBMIT_COPY_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{SUBMIT_COPY_MODULE}` does not import ({missing}). E2-08 established this module "
            "as the submit path's copy, and E2-15 repairs one sentence inside it."
        )
    mapping = getattr(module, COPY_MAPPING_NAME, None)
    if not isinstance(mapping, Mapping):
        pytest.fail(
            f"`{SUBMIT_COPY_MODULE}` exposes `{COPY_MAPPING_NAME}`={mapping!r}, not a mapping. "
            "E2-08's shape is `COPY: Mapping[str, CopyEntry]` keyed by dotted keys."
        )
    entry = mapping.get(BOUNCE_INSUFFICIENT_KEY)
    if entry is None:
        pytest.fail(
            f"`{SUBMIT_COPY_MODULE}.{COPY_MAPPING_NAME}` holds no entry keyed "
            f"`{BOUNCE_INSUFFICIENT_KEY}`; it holds {sorted(mapping)}. E2-15's scope item 2 names "
            "that key by the file and line it already ships at "
            "(`backend/app/copy/submit.py:88-95`); a renamed key is a dispute rather than "
            "something this test should guess past."
        )
    return entry


def test_the_bounce_insufficient_sentence_is_the_settled_byte_exact_replacement() -> None:
    """Criterion 2: the shipped sentence equals the settled replacement, exactly.

    **The mutation this kills:** the sentence left as it ships today — "…a few
    words on their own are too brief to." — a truncated infinitive that reads
    as a sentence fragment on the epic's first student-visible surface. Any
    other departure from the settled text is caught the same way, because the
    comparison is equality rather than a substring or a regular expression: a
    reworded sentence that also happens to be grammatical, or one that drops
    the quoted example, fails here exactly as the truncated original does.

    **The near miss this does not soften:** a sentence that is grammatically
    complete but not this one — SPEC's/E2-15's ruling is a specific string,
    not "any complete infinitive", so a fix that resolves the truncation with
    different wording is still a red here and is a dispute rather than a pass.
    """
    entry = bounce_insufficient_entry()
    shipped = str(getattr(entry, "text", entry))
    assert shipped == EXPECTED_SENTENCE, (
        f"`{SUBMIT_COPY_MODULE}.{COPY_MAPPING_NAME}[{BOUNCE_INSUFFICIENT_KEY!r}].text` reads:\n"
        f"  {shipped!r}\n"
        "and E2-15's settled replacement is:\n"
        f"  {EXPECTED_SENTENCE!r}\n\n"
        "The ticket's own measurement is that the shipped sentence ends in a truncated "
        "infinitive — '…are too brief to.' — and the settled repair changes only that "
        "('to.' → 'to be useful.'), leaving the quoted example and the register (it judges the "
        "words, never the person) unchanged."
    )
