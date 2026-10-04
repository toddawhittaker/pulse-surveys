"""E5.1-03 criterion 1 — the four entry pages say only what the copy registry says.

> Every sentence the four entry pages serve, plus `NOT_AN_INSTRUCTOR`, is a
> `CopyEntry` under a governed prefix. The items 4 and 5 sweep reads them.

The four entry pages are what either door answers with when it answers no
landing: the refusal page, the cancelled page, the no-account page and the
no-access page (`app.api.deps`). They are rendered for people who have not
signed in, and until this ticket every sentence on them was a literal in
`deps.py` that the SPEC §4.1 items 4 and 5 sweep never read. Ruling R1 of the
work order moves each sentence, byte for byte, into `backend/app/copy/entry.py`
under the `entry.` prefix, and the guard-name mapping stays in `deps.py` as
routing.

**What this module asserts, page by page.** Each page is rendered, its visible
text is read — everything outside `<head>`, `<style>`, `<script>` and `<title>`
— and two things are required of it:

  - **the page carries its own entries.** The refusal page carries
    `entry.refused.heading` and the entry its guard maps to; a guard nothing
    maps carries the heading and `entry.refused.default`; each argument-free
    page carries its heading and its message. The keys are R1's; the sentences
    are read out of the registry at run time and never written here
    (`docs/MISTAKES.md` entry 19), so rewording one is an edit to
    `entry.py` alone;
  - **nothing else on the page is a sentence.** Every run of visible text with
    three or more letter-words in a row must sit inside the text of some
    `entry.` registry entry. A sentence the registry does not hold is one the
    items 4 and 5 sweep never reads, which is the state this ticket ends.

The second half is what stops the first from being satisfied by a page that
renders the registry's sentence beside a literal of its own. The third half of
the criterion — the instructor gate's 401 — is driven over HTTP in
`tests/integration/test_the_instructor_gate_answers_with_its_registry_sentence.py`,
and "the items 4 and 5 sweep reads them" is asserted in the inventory module.

**Disclosed limits.** Visible text is read from the markup, not from a
rendering: CSS `content:` and anything a script would write are outside it, as
they are for the inventory. Two-word runs are not sentences here, for the
reason `tests/unit/test_the_api_deps_module_ships_no_ungoverned_sentence.py`
gives — the wordmark is two words — so a two-word heading written as a literal
would pass the second half; the first half still requires the registry's own
heading on the page.

**The controls come first.** The text reader and the governance check are run
on sample markup written here, in both directions. **A red in a control means
these tests are broken, not the code.**

**A missing registry is a FAILED, not an error.** Every page test begins with
`entry_registry()`, a plain call in the body that `pytest.fail`s naming
`backend/app/copy/entry.py` and the keys it owes if they are gone, never an
error at setup (`docs/MISTAKES.md` entry 44).

**Not marked `invariant`.** This asserts where the pages' words come from; the
§4.1 rules over those words are the inventory module's, and they are marked
there.
"""

from __future__ import annotations

import importlib
import inspect
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

import pytest
from fixtures.submit import copy_texts

# The registry prefix R1 settles for the entry pages.
ENTRY_PREFIX = "entry."

# R1's keys. The guard names are the vocabulary the two doors publish — the
# `LaunchRefusedError` subclasses and the web door's `SessionRefusedError` —
# transcribed from `tests/unit/test_the_refusal_page_repeats_nothing_it_was_
# handed.py::DOOR_GUARDS`, and each maps to the key R1's table gives it.
REFUSED_HEADING_KEY = "entry.refused.heading"
DEFAULT_REFUSAL_KEY = "entry.refused.default"
GUARD_KEYS = {
    "SignatureRefused": "entry.refused.signature",
    "AudienceRefused": "entry.refused.audience",
    "IssuerRefused": "entry.refused.issuer",
    "NonceRefused": "entry.refused.nonce",
    "NonceReplayedError": "entry.refused.nonce_replayed",
    "DeploymentRefused": "entry.refused.deployment",
    "MessageTypeRefused": "entry.refused.message_type",
    "VersionRefused": "entry.refused.version",
    "StateRefused": "entry.refused.state",
    "ClockSkewRefused": "entry.refused.clock_skew",
    "AnonymousLaunchRefused": "entry.refused.anonymous_launch",
    "SessionRefusedError": "entry.refused.session",
}

# A name no guard class has. The refusal page answers it with the default.
AN_UNMAPPED_GUARD = "e5-1-03-guard-nothing-maps"

# The three pages that take no argument, each with its two keys.
REFUSAL_PAGE = "refusal_page"
ARGUMENT_FREE_PAGES = {
    "cancelled_page": ("entry.cancelled.heading", "entry.cancelled.message"),
    "no_account_page": ("entry.no_account.heading", "entry.no_account.message"),
    "no_access": ("entry.no_access.heading", "entry.no_access.message"),
}

EVERY_KEY = (
    REFUSED_HEADING_KEY,
    DEFAULT_REFUSAL_KEY,
    *GUARD_KEYS.values(),
    *(key for keys in ARGUMENT_FREE_PAGES.values() for key in keys),
)

DEPS_MODULE = "app.api.deps"

# Three or more letter-words in a row, each a word on its own — the rule the
# `deps.py` sweep uses, for the reason that module's docstring gives.
SENTENCE = re.compile(r"(?<![\w-])[A-Za-z]+(?: [A-Za-z]+){2,}(?![\w-])")

# Elements whose text no reader sees on the page.
UNSEEN_ELEMENTS = frozenset({"head", "style", "script", "title"})

# ---------------------------------------------------------------------------
# Samples. Written here; none of these sentences ships.
# ---------------------------------------------------------------------------

A_SAMPLE_HEADING = "The sample heading reads plainly"
A_SAMPLE_MESSAGE = "Close this tab and open the sample again from your course."

A_SAMPLE_PAGE = "\n".join(
    [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        "<title>Pulse Surveys Sample Title</title>",
        "<style>",
        "  :root { --font-body: 'Schibsted Grotesk', 'Helvetica Neue', sans-serif; }",
        "  body { font-family: var(--font-body); }",
        "</style>",
        "</head>",
        "<body>",
        '<main data-testid="sample-entry" data-reason="SampleRefused">',
        '<p class="wordmark">Pulse Surveys</p>',
        f"<h1>{A_SAMPLE_HEADING}</h1>",
        '<p>Close this tab and open the <a href="/">sample</a> again from your course.</p>',
        "</main>",
        "<script>const unseen = 'a script sentence nobody reads';</script>",
        "</body>",
        "</html>",
    ]
)

A_STRAY_SENTENCE = "This sentence is in no registry at all."


class VisibleText(HTMLParser):
    """Every run of text a reader sees on a page, whitespace collapsed, in order.

    Text inside `<head>`, `<style>`, `<script>` or `<title>` is not collected:
    none of it is on the page. Attributes are not text, so a testid or a
    `data-reason` value is never read as a sentence. Character references are
    decoded, so a registry sentence holding an apostrophe matches its escaped
    rendering.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.unseen_depth = 0
        self.runs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in UNSEEN_ELEMENTS:
            self.unseen_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in UNSEEN_ELEMENTS and self.unseen_depth:
            self.unseen_depth -= 1

    def handle_data(self, data: str) -> None:
        collapsed = " ".join(data.split())
        if collapsed and not self.unseen_depth:
            self.runs.append(collapsed)


def visible_runs(markup: str) -> list[str]:
    """The runs of text a reader sees in `markup`."""
    reader = VisibleText()
    reader.feed(markup)
    reader.close()
    return reader.runs


def visible_text(markup: str) -> str:
    """Everything a reader sees in `markup`, as one whitespace-collapsed string."""
    return " ".join(" ".join(visible_runs(markup)).split())


def collapsed(text: str) -> str:
    """`text` with its whitespace collapsed, as the page reader collapses it."""
    return " ".join(text.split())


def ungoverned_sentences(markup: str, governed: Mapping[str, str]) -> list[str]:
    """Every visible run holding a sentence that sits inside no governed text.

    A run is compared by containment rather than equality, because inline
    markup splits a sentence into runs: a link inside a message leaves the words
    before and after it as runs of their own, each still inside the entry.
    """
    texts = [collapsed(text) for text in governed.values()]
    return [
        run
        for run in visible_runs(markup)
        if SENTENCE.search(run) and not any(run in text for text in texts)
    ]


def entry_registry() -> dict[str, str]:
    """Every `entry.` text in the copy registry, or a failure naming the keys owed.

    The deliverable guard: called as the first statement of every page test, so
    a tree without `app/copy/entry.py` reds as a FAILED naming it.
    """
    texts = copy_texts()
    entries = {key: text for key, text in texts.items() if key.startswith(ENTRY_PREFIX)}
    missing = [key for key in EVERY_KEY if not entries.get(key, "").strip()]
    if missing:
        pytest.fail(
            f"The copy registry publishes no non-empty {missing}.\n\n"
            "E5.1-03's ruling R1 moves every sentence the four entry pages serve, byte for byte, "
            "into `backend/app/copy/entry.py` under the `entry.` prefix — `CopyEntry` constants and "
            "a `COPY` mapping, the package's usual shape — so that the SPEC §4.1 items 4 and 5 "
            "sweep reads them."
        )
    return entries


def rendered(page_name: str, *arguments: str) -> str:
    """One entry page out of `app.api.deps`, rendered, as markup.

    Every parameter the page takes is handed `arguments[0]` when given, which is
    how the refusal page receives its guard name without this module naming the
    parameter (`tests/unit/test_the_refusal_page_repeats_nothing_it_was_handed.py`
    gives the reason).
    """
    module = importlib.import_module(DEPS_MODULE)
    page = getattr(module, page_name, None)
    if not callable(page):
        pytest.fail(f"`{DEPS_MODULE}` exposes no callable `{page_name}`.")
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for parameter in inspect.signature(page).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        value = arguments[0] if arguments else ""
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keyword[parameter.name] = value
    answer = page(*positional, **keyword)
    body = getattr(answer, "body", None)
    if isinstance(body, bytes | bytearray):
        return bytes(body).decode("utf-8", "replace")
    if isinstance(body, str):
        return body
    if isinstance(answer, str):
        return answer
    pytest.fail(f"`{page_name}` answered {answer!r}, which carries no markup this can read.")


def assert_the_page_says_only_its_entries(
    markup: str, keys: tuple[str, ...], entries: Mapping[str, str], what: str
) -> None:
    """Both halves of the criterion over one rendered page."""
    seen = visible_text(markup)
    absent = [key for key in keys if collapsed(entries[key]) not in seen]
    assert not absent, (
        f"{what} does not carry the text of {absent}. What a reader sees on it is {seen!r}.\n\n"
        "R1 moves each sentence byte for byte and the page renders the entry's `.text`, so the "
        "registry's sentence is the one on the page."
    )
    stray = ungoverned_sentences(markup, entries)
    assert not stray, (
        f"{what} shows {stray}, which sits inside no `entry.` registry text. A sentence on an "
        "entry page that the registry does not hold is one the items 4 and 5 sweep never reads."
    )


# ---------------------------------------------------------------------------
# Controls. A red here means these tests are broken, not the code.
# ---------------------------------------------------------------------------


def test_the_text_reader_reads_the_page_and_not_its_head_styles_or_scripts() -> None:
    """The reader collects what a reader sees and nothing else.

    **The mutation it kills:** a reader that collects the title, the stylesheet
    or a script, each of which would put a non-sentence or an unseen sentence in
    front of the governance check; and one that drops text around inline markup,
    which would split a message so that its halves match nothing. **A red here
    means this module is broken, not that the code is.**
    """
    seen = visible_text(A_SAMPLE_PAGE)
    assert A_SAMPLE_HEADING in seen and A_SAMPLE_MESSAGE in seen, (
        f"The reader read {seen!r}; it should hold the heading and the message, the latter "
        "joined across the link inside it."
    )
    for unseen in ("Sample Title", "font-family", "script sentence", "SampleRefused"):
        assert unseen not in seen, f"The reader collected {unseen!r}, which no reader sees."


def test_the_governance_check_names_a_stray_sentence_and_spares_the_rest() -> None:
    """Both directions: a sentence in no registry text is named; governed runs are not.

    **Spared:** the heading, the two halves of a message split by a link, and a
    two-word wordmark. **Named:** a sentence the governed texts do not hold.
    **The mutation it kills:** an equality comparison, which names each half of
    a split message; and a check that passes any run because some entry exists.
    **A red here means this module is broken.**
    """
    governed = {"sample.heading": A_SAMPLE_HEADING, "sample.message": A_SAMPLE_MESSAGE}
    assert ungoverned_sentences(A_SAMPLE_PAGE, governed) == [], (
        f"The check named {ungoverned_sentences(A_SAMPLE_PAGE, governed)} on a page whose every "
        "sentence is a governed text."
    )
    planted = A_SAMPLE_PAGE.replace("</main>", f"<p>{A_STRAY_SENTENCE}</p></main>")
    assert ungoverned_sentences(planted, governed) == [A_STRAY_SENTENCE], (
        f"With {A_STRAY_SENTENCE!r} planted, the check named "
        f"{ungoverned_sentences(planted, governed)}."
    )


# ---------------------------------------------------------------------------
# The rules.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("guard", sorted(GUARD_KEYS))
def test_the_refusal_page_for_each_guard_says_only_its_registry_entries(
    guard: str, configured_env: dict[str, str]
) -> None:
    """Criterion 1 over the refusal page, once per guard the doors publish.

    The page carries `entry.refused.heading` and the entry R1 maps this guard
    to, and no other sentence. **The mutation it kills:** a sentence left as a
    literal in `deps.py` while the registry holds a copy of it, which this
    passes only if the two are identical and the inventory then reads the copy
    nobody serves — so the page is also required to carry no sentence the
    registry lacks; and a guard mapped to the wrong entry. **Its near miss** is
    the unmapped guard below, which carries the default instead.

    `configured_env` is depended on and not used: `app.api.deps` is an
    application module and anything it imports may build a `Settings`
    (`docs/MISTAKES.md` entry 40).
    """
    entries = entry_registry()
    markup = rendered(REFUSAL_PAGE, guard)
    assert_the_page_says_only_its_entries(
        markup,
        (REFUSED_HEADING_KEY, GUARD_KEYS[guard]),
        entries,
        f"The refusal page for `{guard}`",
    )


def test_the_refusal_page_for_an_unmapped_guard_says_the_default_entry(
    configured_env: dict[str, str],
) -> None:
    """Criterion 1 over the refusal page's default, which a guard nothing maps is shown.

    The page carries `entry.refused.heading` and `entry.refused.default`, and
    no other sentence. **The mutation it kills:** the default left as a literal beside the moved
    mapping, which is the one sentence on this page no mapped guard reaches.
    **Its near miss** is every mapped guard above, which carries its own entry
    rather than the default.
    """
    entries = entry_registry()
    markup = rendered(REFUSAL_PAGE, AN_UNMAPPED_GUARD)
    assert_the_page_says_only_its_entries(
        markup,
        (REFUSED_HEADING_KEY, DEFAULT_REFUSAL_KEY),
        entries,
        f"The refusal page for the unmapped guard `{AN_UNMAPPED_GUARD}`",
    )


@pytest.mark.parametrize("page_name", sorted(ARGUMENT_FREE_PAGES))
def test_each_argument_free_entry_page_says_only_its_registry_entries(
    page_name: str, configured_env: dict[str, str]
) -> None:
    """Criterion 1 over the cancelled, no-account and no-access pages.

    Each carries its own heading and message from the registry, and no other
    sentence. **The mutation it kills:** one of the three pages missed by the
    move — each is a separate pair of constants today, and a move that reached
    two leaves the third's words swept by nothing. **Its near miss** is the
    page's testid and wordmark, which are not sentences and are not required to
    be registry text.
    """
    entries = entry_registry()
    markup = rendered(page_name)
    assert_the_page_says_only_its_entries(
        markup, ARGUMENT_FREE_PAGES[page_name], entries, f"`{page_name}`"
    )
