"""E2-08 criterion 4 — the copy registry, its shape, and the words it may use.

> Every user-facing string this path serves is externalized where E2-11's
> inventory will read it, and says what §4.1 items 4-5 permit.

Two halves, and this module is the registry half. That a *served* refusal is one
of these strings is asserted where the refusal is served, in
`tests/integration/test_the_submit_path_answers_the_validity_matrix.py` and in
`tests/integration/test_the_submit_path_follows_adr_0056s_taxonomy.py`, through
`externalized_key_for` — a route that writes its sentence inline passes nothing
there.

**§4.1 item 5 is not asserted here and that is deliberate.** "Confidentiality
copy appears exactly once per surface (survey: once per screen, in the submit
area)" is a statement about a rendered surface, and the survey form is E2-10's —
the count on a screen carrying two open surveys is E2-17's
`tests/e2e/student-survey-confidentiality.spec.ts`. What this ticket owes
item 5 is that the shape exists for E2-11's inventory to count against, which is
what `test_copy_modules_enumerates_the_packages_own_modules` is about.

**The two vocabulary sweeps each carry a canary** (`docs/MISTAKES.md` entry 3). A
sweep over copy that happens to contain none of the forbidden words is satisfied
by a sweep that has gone blind — a pattern that no longer compiles, a
normalisation that lower-cases the wrong side — so each one is run against a
string that certainly trips it and against a string that certainly does not,
before it is run against what ships.

**Nothing here reads a database or builds an application.** The registry is a
package of constants; a module that needed `Settings` to state a sentence would
be a defect worth its own failure.

**One of the two vocabulary sweeps now lives next door.** The §4.1 item 1 one —
`test_no_shipped_copy_string_shows_a_student_a_comparison` — is a confidentiality
denial and held its `invariant` marker per test, which is the currency
`test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
refuses. E2-14 moved it unchanged to
`test_the_shipped_copy_names_nothing_a_student_may_not_see.py`, whose stem
carries a denial shape so that sweep governs it. Its control stayed here, because
that control is deliberately unmarked and a module-level marker would have
enrolled it in the pass; `FORBIDDEN_COMPARISONS`, `forbidden_in` and
`every_entry` also stay here and are imported from there, so there is one
vocabulary rather than two. The shame-state sweep is untouched.
"""

import importlib
import re
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fixtures.submit import (
    CLASSIFIER_DOWN_KEY,
    COPY_ENTRY_CLASS,
    COPY_MAPPING_NAME,
    COPY_MODULES_FUNCTION,
    COPY_PACKAGE,
    NOT_A_STUDENT_KEY,
    SUBMIT_COPY_MODULE,
)

# SPEC §7.4's two refused verdicts, transcribed. The bounce copy is found by them
# rather than by a key name, because E2-08's work order settles the registry's
# *shape* and the two keys below and settles no key for the bounces — so a
# vocabulary the spec owns is a better handle than a spelling nobody has chosen.
INSUFFICIENT = "insufficient"
NONSENSE = "nonsense"

# The two fields E2-08's work order gives `CopyEntry`: "frozen dataclass:
# `key: str`, `text: str`".
COPY_ENTRY_FIELDS = ("key", "text")

# §4.1 item 1, as words a student-facing string may not carry: "Students never see
# comparables, benchmarks, university averages, or other sections — in charts,
# text, tooltips, exports, or aria labels." Item 4's ranking rule is folded in
# because it forbids the same family of sentence: "no ranking, no composite
# scores, and no score-sorting anywhere", and "'needs attention,' never
# 'underperforming'".
FORBIDDEN_COMPARISONS = (
    "benchmark",
    "comparable",
    "comparison set",
    "university average",
    "university-wide",
    "other sections",
    "other students",
    "average student",
    "underperform",
    "ranking",
    "ranked",
    "percentile",
    "composite score",
    "top performer",
)

# A sentence that certainly trips the sweep above, and one that certainly does
# not. Both are this module's own and neither is quoted from the registry: the
# point of a canary is to fail when the sweep stops seeing, and a canary copied
# out of the thing being swept goes blind with it.
A_COMPARING_SENTENCE = "Your answers are below the university average for other sections."
A_PERMITTED_SENTENCE = "Your answers go to your instructor without your name attached."

# §3.3: the bounce is "coaching copy and one concrete example, never a shame
# state". These are the words a shame state is written in. `invalid` is
# deliberately absent — it is this system's own word for a response that does not
# count and appears in `response.is_valid`, so forbidding it would be forbidding
# the vocabulary rather than the shaming.
FORBIDDEN_SHAMING = (
    "lazy",
    "you failed",
    "failure",
    "penalt",
    "punish",
    "violation",
    "warning:",
    "bad answer",
    "poor answer",
    "not good enough",
)

A_SHAMING_SENTENCE = "That was a bad answer and there will be a penalty."
A_COACHING_SENTENCE = 'A sentence about this week helps, like "the pacing in week 3 was too fast".'

# How "one concrete example" is recognised. §3.3 gives the examples in quotation
# marks — "the pacing in week 3 was too fast" / "it was okay" / "adfasdfa" — and a
# quoted fragment is the one mechanically checkable form of "an example" a
# `(key, text)` pair can carry. A bounce that coaches with an unquoted example is
# a dispute rather than a defect, and it is named as such in the failure below.
# The curly quotation marks are built from their code points rather than written
# as characters, because ruff reads each as a confusable of the straight one
# beside it and this repository spells such characters out rather than adding an
# ignore (`tests/integration/test_survey_schema.py` makes the same choice for
# SPEC §3.2's en dashes). In order: left single, right single, left double,
# right double.
CURLY_QUOTES = "".join(chr(point) for point in (0x2018, 0x2019, 0x201C, 0x201D))
QUOTE_CHARACTERS = "\"'" + CURLY_QUOTES
QUOTED_FRAGMENT = re.compile(f"[{QUOTE_CHARACTERS}]([^{QUOTE_CHARACTERS}]{{8,}})")


def forbidden_in(text: str, vocabulary: tuple[str, ...]) -> list[str]:
    """Every member of `vocabulary` that appears in `text`, case-insensitively."""
    lowered = text.lower()
    return sorted(word for word in vocabulary if word in lowered)


def imported_copy_package() -> ModuleType:
    """`app.copy`, or a failure naming what E2-08's work order puts there."""
    try:
        return importlib.import_module(COPY_PACKAGE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{COPY_PACKAGE}` does not import ({missing}). E2-08 establishes the string-"
            "externalization shape E2-11's inventory will read: a package whose `__init__` "
            f"defines `{COPY_ENTRY_CLASS}` and `{COPY_MODULES_FUNCTION}()` and nothing else, and "
            "one module per surface. E2-09 and E2-10 then follow it — three tickets inventing "
            "three shapes is how the inventory decays into a hand-kept list."
        )


def copy_modules_of(package: ModuleType) -> list[ModuleType]:
    """Whatever `copy_modules()` enumerates, or a failure saying it is not there."""
    function = getattr(package, COPY_MODULES_FUNCTION, None)
    if not callable(function):
        pytest.fail(
            f"`{COPY_PACKAGE}` exposes no callable `{COPY_MODULES_FUNCTION}`; it exposes "
            f"{sorted(name for name in vars(package) if not name.startswith('_'))}."
        )
    return list(function())


def entries_of(module: ModuleType) -> dict[str, Any]:
    """One copy module's `COPY` mapping, or a failure naming the convention."""
    mapping = getattr(module, COPY_MAPPING_NAME, None)
    if mapping is None:
        pytest.fail(
            f"`{module.__name__}` publishes no `{COPY_MAPPING_NAME}`. Each surface adds one "
            f"module defining `{COPY_MAPPING_NAME}: Mapping[str, {COPY_ENTRY_CLASS}]` keyed by "
            "dotted keys, which is what makes the package enumerable."
        )
    return dict(mapping)


def every_entry() -> dict[str, Any]:
    """Every entry every copy module publishes, keyed by its dotted key."""
    package = imported_copy_package()
    collected: dict[str, Any] = {}
    for module in copy_modules_of(package):
        collected.update(entries_of(module))
    assert collected, (
        "The copy registry publishes no entries at all. Every sweep below would then pass over "
        "nothing, which is `docs/MISTAKES.md` entry 3 exactly — a rule satisfied by emptiness."
    )
    return collected


# ---------------------------------------------------------------------------
# The shape the work order settles.
# ---------------------------------------------------------------------------


def test_the_copy_package_publishes_a_frozen_copy_entry_of_a_key_and_a_text() -> None:
    """`CopyEntry` is a frozen dataclass carrying `key` and `text`.

    **The mutation it kills:** a mutable entry, or one carrying anything else. A
    registry whose entries can be edited after import is a registry E2-11's
    inventory reads at one moment and the application serves at another, and a
    third field is a place for a rule to live where the inventory will not look.
    """
    package = imported_copy_package()
    entry = getattr(package, COPY_ENTRY_CLASS, None)
    assert entry is not None and isinstance(entry, type), (
        f"`{COPY_PACKAGE}` exposes `{COPY_ENTRY_CLASS}`={entry!r}. E2-08's work order: "
        f'"`__init__.py` defines `{COPY_ENTRY_CLASS}` (frozen dataclass: `key: str`, '
        '`text: str`)".'
    )
    assert is_dataclass(entry), f"`{COPY_ENTRY_CLASS}` is not a dataclass."

    declared = tuple(field.name for field in fields(entry))
    assert declared == COPY_ENTRY_FIELDS, (
        f"`{COPY_ENTRY_CLASS}` declares {declared}; the settled shape is {COPY_ENTRY_FIELDS}. A "
        "field the inventory does not know about is a rule that ships where nothing will read it."
    )

    made = entry(key="e2-08.probe", text="a probe")
    with pytest.raises((AttributeError, TypeError)):
        made.text = "something else"  # type: ignore[misc]


def test_copy_modules_enumerates_the_packages_own_modules() -> None:
    """`copy_modules()` finds every module in the package, and no list decides which.

    E2-08's work order: "there is NO central list (a guard's inventory must not be
    shrinkable — the E2-11 inventory will enumerate the package's modules)". So
    the assertion is against the package *directory*: whatever `.py` files are
    there, other than `__init__`, are what has to come back.

    **The mutation it kills:** `copy_modules()` returning a hand-written tuple. A
    list is shrinkable by an edit to the very module it is meant to inventory —
    `docs/MISTAKES.md` entry 35's shape — and a surface dropped from it would be
    a surface E2-11 reports nothing about while its strings ship.
    """
    package = imported_copy_package()
    locations = [Path(entry) for entry in getattr(package, "__path__", [])]
    assert (
        locations
    ), f"`{COPY_PACKAGE}` has no `__path__`, so it is a module rather than a package."

    on_disk = {
        path.stem
        for location in locations
        for path in location.glob("*.py")
        if path.stem != "__init__"
    }
    assert on_disk, (
        f"There are no modules under {locations} besides `__init__`, so this test would pass "
        "against a registry holding no copy at all. E2-08 adds `submit.py` there."
    )

    enumerated = {module.__name__.rsplit(".", 1)[-1] for module in copy_modules_of(package)}
    assert enumerated == on_disk, (
        f"`{COPY_MODULES_FUNCTION}()` enumerates {sorted(enumerated)} and the package directory "
        f"holds {sorted(on_disk)}. The two have to agree by construction rather than by anyone "
        "remembering: a module the enumeration misses is copy that ships with nothing counting it, "
        "and a name in the enumeration that is not on disk is an inventory of something that does "
        "not exist."
    )


def test_every_copy_entry_is_keyed_by_the_key_it_carries() -> None:
    """A mapping key and its entry's `key` are the same string, and no text is blank.

    **The mutation it kills:** an entry filed under one key and carrying another.
    E2-11's inventory reads the key off the entry and the route looks the entry up
    by the mapping key, so a disagreement makes a string that is served
    unfindable and a string that is inventoried unserved — and neither side goes
    red on its own.
    """
    mismatched = {}
    blank = []
    for key, entry in every_entry().items():
        carried = getattr(entry, "key", None)
        if carried != key:
            mismatched[key] = carried
        if not str(getattr(entry, "text", "")).strip():
            blank.append(key)

    assert not mismatched, (
        f"These entries are filed under one key and carry another: {mismatched}. The route looks "
        "a string up by the mapping key and the inventory reads it off the entry, so the two "
        "disagreeing hides a string from exactly one of them."
    )
    assert not blank, (
        f"These entries carry no text: {blank}. An empty string is a surface with nothing to say, "
        "and it also makes `externalized_key_for` match every response body there is."
    )


def test_the_registry_carries_the_two_keys_the_work_order_spells() -> None:
    """`student.not_a_student` and `submit.classifier_down` are both there.

    The only two key names E2-08 settles by name — the first is
    `require_student`'s refusal and the second is ADR 0114's honest retryable
    refusal — so they are the two that can be asserted as spellings rather than
    by role.

    **The mutation it kills:** either sentence written inline at its raise site.
    A refusal that is not in the registry is a refusal E2-11's inventory cannot
    see, and both of these are strings a student reads.
    """
    keys = set(every_entry())
    missing = [key for key in (NOT_A_STUDENT_KEY, CLASSIFIER_DOWN_KEY) if key not in keys]
    assert not missing, (
        f"The copy registry publishes no {missing}. It publishes {sorted(keys)}. E2-08's work "
        f"order spells both: `{NOT_A_STUDENT_KEY}` for the 401 a request without a student "
        f"session is refused with, and `{CLASSIFIER_DOWN_KEY}` for ADR 0114's honest retryable "
        "refusal."
    )


def test_the_submit_module_holds_the_paths_copy() -> None:
    """`app.copy.submit` exists and is one of the modules the package enumerates.

    Its own test rather than folded above, because "the package enumerates its
    modules" and "this ticket added its module" are different failures: the first
    is the shape E2-09 and E2-10 inherit, and the second is this ticket's own
    copy existing at all.
    """
    package = imported_copy_package()
    names = {module.__name__ for module in copy_modules_of(package)}
    assert SUBMIT_COPY_MODULE in names, (
        f"`{SUBMIT_COPY_MODULE}` is not among the modules `{COPY_MODULES_FUNCTION}()` enumerates "
        f"({sorted(names)}). E2-08's work order: 'This ticket adds `backend/app/copy/submit.py` "
        "with every user-facing string the submit path serves'."
    )
    assert entries_of(
        importlib.import_module(SUBMIT_COPY_MODULE)
    ), f"`{SUBMIT_COPY_MODULE}` publishes an empty `{COPY_MAPPING_NAME}`."


# ---------------------------------------------------------------------------
# SPEC §3.3 — the bounce is coaching copy with one concrete example, and never a
# shame state.
# ---------------------------------------------------------------------------


def bounce_copy() -> dict[str, dict[str, str]]:
    """The bounce entry for each of §7.4's two refused verdicts, found by the verdict token."""
    entries = every_entry()
    found: dict[str, dict[str, str]] = {}
    for verdict in (INSUFFICIENT, NONSENSE):
        matched = {key: str(entry.text) for key, entry in entries.items() if verdict in key.lower()}
        if len(matched) != 1:
            pytest.fail(
                f"{len(matched)} registry keys carry the verdict {verdict!r} ({sorted(matched)}); "
                f"the registry holds {sorted(entries)}. SPEC §3.3 bounces a submission with 'the "
                "verdict's coaching copy', so there is one entry per refused verdict. The two "
                "verdict tokens are §7.4's own vocabulary; if the keys spell them another way, "
                "that is an interface question for the ticket rather than a defect."
            )
        found[verdict] = matched
    return found


def test_each_refused_verdict_has_its_own_coaching_copy() -> None:
    """`insufficient` and `nonsense` bounce with different sentences.

    §3.3 names them as two different things a student did — "it was okay" against
    "adfasdfa" — and coaching that cannot tell them apart is not coaching. Half of
    what a bounce owes.

    **The mutation it kills:** one sentence served for both verdicts, which reads
    correct at every call site and tells a student who wrote a terse real answer
    that they typed nonsense.
    """
    found = bounce_copy()
    texts = {verdict: next(iter(matched.values())) for verdict, matched in found.items()}
    assert texts[INSUFFICIENT] != texts[NONSENSE], (
        f"Both refused verdicts bounce with the same sentence: {texts[INSUFFICIENT]!r}. §3.3 "
        "gives 'it was okay' and 'adfasdfa' as two different things, and the copy is the only "
        "place the difference reaches the student."
    )


@pytest.mark.parametrize("verdict", [INSUFFICIENT, NONSENSE])
def test_the_bounce_copy_carries_one_concrete_example(verdict: str) -> None:
    """§3.3: the bounce carries "coaching copy and one concrete example".

    An example is recognised as a quoted fragment, which is how §3.3 writes its
    own three — "the pacing in week 3 was too fast" among them — and is the one
    mechanically checkable form a `(key, text)` pair can carry.

    **The mutation it kills:** a bounce that states the rule and gives no example
    ("your comment is too brief to count"), which is exactly the copy §3.3 was
    written to rule out. **The near miss it names rather than tolerates:** an
    example written without quotation marks is a dispute about how the criterion
    is checked, not a pass.
    """
    text = next(iter(bounce_copy()[verdict].values()))
    quoted = QUOTED_FRAGMENT.findall(text)
    assert quoted, (
        f"The {verdict} bounce reads {text!r} and carries no quoted example. SPEC §3.3: a student "
        "is told immediately, 'with coaching copy and one concrete example, never a shame state'. "
        "If the example is written without quotation marks, that is a disagreement about how this "
        "criterion is checked — raise it as a dispute rather than dropping the example."
    )


def test_the_shame_sweep_sees_a_shaming_sentence_and_leaves_a_coaching_one() -> None:
    """The control on the sweep below (`docs/MISTAKES.md` entry 3).

    A sweep for words that do not appear is satisfied by a sweep that cannot see,
    so it is run against a sentence that certainly trips it and one that
    certainly does not — neither of them quoted from the registry, because a
    canary copied out of the thing being swept goes blind with it.

    **A red here means this module is broken, not that the copy is.**
    """
    assert forbidden_in(A_SHAMING_SENTENCE, FORBIDDEN_SHAMING), (
        f"The sweep found nothing in {A_SHAMING_SENTENCE!r}, which carries two of "
        f"{list(FORBIDDEN_SHAMING)}. Every assertion below it would then pass over any copy at all."
    )
    assert not forbidden_in(A_COACHING_SENTENCE, FORBIDDEN_SHAMING), (
        f"The sweep flagged {A_COACHING_SENTENCE!r}, which is the shape §3.3 asks for. A sweep "
        "that refuses the permitted case makes the rule unimplementable."
    )


@pytest.mark.parametrize("verdict", [INSUFFICIENT, NONSENSE])
def test_the_bounce_copy_is_not_a_shame_state(verdict: str) -> None:
    """§3.3: "never silently penalized after the fact ... never a shame state".

    **The mutation it kills:** coaching rewritten as a telling-off. The student
    has done nothing wrong — the classifier judged one sentence — and the words
    are the whole of what they experience.
    """
    text = next(iter(bounce_copy()[verdict].values()))
    found = forbidden_in(text, FORBIDDEN_SHAMING)
    assert not found, (
        f"The {verdict} bounce reads {text!r} and carries {found}. SPEC §3.3 requires coaching "
        "with an example and 'never a shame state'; a student who typed a short sentence is being "
        "told they did something wrong."
    )


# ---------------------------------------------------------------------------
# SPEC §4.1 items 1 and 4 — what a student-facing string may not say.
# ---------------------------------------------------------------------------


def test_the_comparison_sweep_sees_a_comparing_sentence_and_leaves_a_permitted_one() -> None:
    """The control on the invariant next door (`docs/MISTAKES.md` entry 3).

    The invariant this controls is
    `test_the_shipped_copy_names_nothing_a_student_may_not_see.py::test_no_shipped_copy_string_shows_a_student_a_comparison`,
    which stood below this test until E2-14 moved it into a module whose name
    carries a denial shape; that module's docstring records the direction and
    why. It reads `FORBIDDEN_COMPARISONS` and `forbidden_in` from here, so this
    control is still the control on exactly the instrument that sweep uses.

    **A red here means this module is broken, not that the copy is.** It is not
    marked `invariant`, and that is why it stayed: it asserts nothing about what
    ships, and CI's isolated §4.1 pass should fail on the rule rather than on its
    instrument.
    """
    assert forbidden_in(A_COMPARING_SENTENCE, FORBIDDEN_COMPARISONS), (
        f"The sweep found nothing in {A_COMPARING_SENTENCE!r}, which names a university average "
        "and other sections. The invariant below would then pass over any copy at all, including "
        "copy that shows a student a benchmark."
    )
    assert not forbidden_in(A_PERMITTED_SENTENCE, FORBIDDEN_COMPARISONS), (
        f"The sweep flagged {A_PERMITTED_SENTENCE!r}, which says only where a student's answers "
        "go. A sweep that refuses permitted copy makes §4.1 item 5's confidentiality line "
        "unwritable."
    )


# The §4.1 item 1 sweep this control exists for is
# `test_the_shipped_copy_names_nothing_a_student_may_not_see.py`, from E2-14. It
# stood here, holding `@pytest.mark.invariant` on the test rather than on the
# module, which is the currency
# `test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
# refuses; it moved unchanged into a module whose name carries a denial shape, so
# that the sweep governs it and its next denial test inherits the marker. The
# vocabulary and the reader stay here and are imported from there.
