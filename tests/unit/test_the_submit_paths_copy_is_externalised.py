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

**That sweep's exemption and its controls live here for the same reason.** Since
`docs/disputes/E5-13-01.md`, the §4.1 item 1 sweep skips six keys by name —
`LEADERSHIP_ONLY_REFUSAL_KEYS`, the named-set API's refusals that are answered
only to a request which has already passed the leadership gate and that the
sweep would otherwise catch — and the reader
that applies them is `comparisons_offending`. The three controls on that
exemption are here and unmarked: they measure the instrument rather than what
ships, and a red in one of them means the exemption is broken rather than that
the copy is. The one refusal of that surface a student can be served,
`leadership_comparison_sets.not_leadership`, is asserted here to be published and
not exempt.
"""

import importlib
import re
from collections.abc import Mapping
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

# The §4.1 item 1 sweep's one exemption, spelled as keys rather than as a surface
# or as a gap in the vocabulary above. The dispute `docs/disputes/E5-13-01.md`
# ruled it: these sentences are answered only to a request that has already
# passed the leadership gate, so no student can be served any of them, while
# `leadership_comparison_sets.not_leadership` — of the same surface — is what
# `app.api.deps.require_leadership` answers a student with and therefore stays
# inside the sweep. By key and not by prefix for exactly that reason: the surface
# holds a key a student can be served.
#
# **Six rows, where the ruling said seven.** The ruling counted the refusals that
# are answered only behind the leadership gate; what an exemption row has to
# earn is that the sweep would otherwise catch its sentence. The seventh,
# `leadership_comparison_sets.member_not_a_course`, carries no word in
# `FORBIDDEN_COMPARISONS` at all — it names courses rather than the set — so a
# row for it would be excusing nothing, which is `docs/MISTAKES.md` entry 14's
# shape and what the row-by-row control below measured. It stays inside the
# sweep, where it passes.
#
# Beside each key is the gate that must hold for it to be unreachable and the
# route that answers it, taken from E5-06's contract as
# `tests/fixtures/named_sets.py` transcribes it ("reads carry
# `require_leadership`, writes carry `csrf_verified_leadership`") and from the
# dispute's ruling, rather than from the implementation. **If one of these
# refusals ever becomes reachable without a leadership session, its row leaves
# this tuple in the same change** — that consequence is ADR 0177's.
#
# The key spellings are not held to be correct by being written here: every row
# is required below to be a key the registry actually publishes, and to be a key
# whose shipped text the sweep would otherwise catch.
LEADERSHIP_SETS_PREFIX = "leadership_comparison_sets."

LEADERSHIP_ONLY_REFUSAL_KEYS = (
    # 404, the unknown-or-out-of-scope set, on the set-id routes of
    # `/leadership/comparison-sets/{set_id}` (and its `/preview`): reads behind
    # `require_leadership`, the edit and the delete behind
    # `csrf_verified_leadership`.
    f"{LEADERSHIP_SETS_PREFIX}set_unavailable",
    # 403, a set another leader defined, on `PUT` and `DELETE
    # /leadership/comparison-sets/{set_id}`, behind `csrf_verified_leadership`.
    f"{LEADERSHIP_SETS_PREFIX}not_the_sets_definer",
    # 409, the duplicate name, on `POST /leadership/comparison-sets` and `PUT
    # /leadership/comparison-sets/{set_id}`, behind `csrf_verified_leadership`.
    f"{LEADERSHIP_SETS_PREFIX}name_already_used",
    # 422, a length that is not a calendar length, raised by
    # `app.services.comparison_sets` on the same two write routes, behind
    # `csrf_verified_leadership`.
    f"{LEADERSHIP_SETS_PREFIX}length_not_a_calendar_length",
    # 422, a level that is not a course level, on the same two write routes,
    # behind `csrf_verified_leadership`.
    f"{LEADERSHIP_SETS_PREFIX}level_not_a_course_level",
    # 422, a member course at another level than the set's, on the same two write
    # routes, behind `csrf_verified_leadership`.
    f"{LEADERSHIP_SETS_PREFIX}member_not_at_the_sets_level",
)

# The refusal of that surface a student can actually be served, which is *not*
# exempt: `require_leadership` answers it to any session that is not a leadership
# session, a student's included, so §4.1 item 1 governs it exactly as it governs
# a bounce.
NOT_LEADERSHIP_KEY = f"{LEADERSHIP_SETS_PREFIX}not_leadership"

# A student-facing prefix and a sentence of this module's own, for the reader's
# control below. Not quoted from the registry: a canary copied out of the thing
# being swept goes blind with it.
A_STUDENT_PREFIXED_KEY = "student.a_probe_this_module_writes"
A_BENCHMARKING_SENTENCE = "Your section sits below the benchmark for this comparison set."

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


def comparisons_offending(
    entries: Mapping[str, Any], exempt: tuple[str, ...] = ()
) -> dict[str, tuple[str, list[str]]]:
    """Every entry whose text carries a forbidden comparison, keyed by key.

    Keys in `exempt` are skipped. The exemption is a parameter rather than a
    constant read inside, so that a control can run the same reader with a row
    taken away and show that the row is load-bearing — the shape
    `confidentiality_strings(..., exempt={})` already has next door in
    `test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`.
    """
    skipped = set(exempt)
    found: dict[str, tuple[str, list[str]]] = {}
    for key, entry in entries.items():
        if key in skipped:
            continue
        text = str(entry.text)
        words = forbidden_in(text, FORBIDDEN_COMPARISONS)
        if words:
            found[key] = (text, words)
    return found


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


def a_synthetic_entry(key: str, text: str) -> Any:
    """One `CopyEntry` of this module's own making, of the registry's real class.

    The real class rather than a stand-in, so that a control over the reader is a
    control over the reader as the shipped registry feeds it.
    """
    package = imported_copy_package()
    entry_class = getattr(package, COPY_ENTRY_CLASS, None)
    assert entry_class is not None, (
        f"`{COPY_PACKAGE}` exposes no `{COPY_ENTRY_CLASS}`, so no synthetic entry can be built of "
        "the class the registry uses."
    )
    return entry_class(key=key, text=text)


def test_the_comparison_reader_catches_a_student_key_and_skips_an_exempt_one() -> None:
    """The control on the exemption (`docs/disputes/E5-13-01.md`, decision 2).

    One sentence, filed twice: under a student prefix, where the sweep has to
    catch it, and under one of the exempt leadership keys, where the sweep has to
    let it by. Same words both times, so what is being measured is the key and
    nothing else.

    **The mutation it kills:** an exemption written as a prefix or as a word
    dropped from `FORBIDDEN_COMPARISONS`, either of which would let the same
    sentence through under a student key as well. **The near miss it spares:** the
    exempt key carrying the very words the vocabulary forbids, which is the whole
    point of exempting by key.

    **A red here means the reader or the exemption is broken, not that the copy
    is.** It is deliberately unmarked: it asserts nothing about what ships.
    """
    entries = {
        A_STUDENT_PREFIXED_KEY: a_synthetic_entry(A_STUDENT_PREFIXED_KEY, A_BENCHMARKING_SENTENCE),
        LEADERSHIP_ONLY_REFUSAL_KEYS[0]: a_synthetic_entry(
            LEADERSHIP_ONLY_REFUSAL_KEYS[0], A_BENCHMARKING_SENTENCE
        ),
    }
    offending = comparisons_offending(entries, exempt=LEADERSHIP_ONLY_REFUSAL_KEYS)
    assert sorted(offending) == [A_STUDENT_PREFIXED_KEY], (
        f"The reader reported {sorted(offending)} over two entries carrying the same sentence, one "
        f"under {A_STUDENT_PREFIXED_KEY!r} and one under "
        f"{LEADERSHIP_ONLY_REFUSAL_KEYS[0]!r}. It should report the student-prefixed one only: the "
        "exemption is by key, and a sweep that misses a student's benchmark sentence is §4.1 item "
        "1 unenforced."
    )


@pytest.mark.parametrize("key", LEADERSHIP_ONLY_REFUSAL_KEYS)
def test_removing_an_exemption_row_puts_its_key_back_in_the_offending_set(key: str) -> None:
    """Each exemption is load-bearing, proven by taking it away rather than by saying so.

    Run over the shipped registry with this one row removed, the sweep must report
    this key. Two things follow: the row is excusing a real string rather than
    decorating the tuple, and the sweep can still see the words on the surface the
    exemption covers.

    **The mutation it kills:** a row added to the tuple for a sentence nothing was
    catching — an exemption that silences a future red nobody has looked at
    (`docs/MISTAKES.md` entry 14). **The near miss it spares:** the same key with
    its row in place, which the sweep must not report.

    **If this reds because the key is not reported even without its row**, that
    sentence no longer carries any forbidden word and the answer is to delete the
    row rather than to keep an excuse for a string nothing was excusing. **A red
    here means the exemption and the copy have come apart, not that the copy is
    wrong.**
    """
    entries = every_entry()
    without_this_row = tuple(other for other in LEADERSHIP_ONLY_REFUSAL_KEYS if other != key)

    with_every_row = comparisons_offending(entries, exempt=LEADERSHIP_ONLY_REFUSAL_KEYS)
    assert key not in with_every_row, (
        f"{key!r} is reported by the sweep while its exemption row is in place: {with_every_row}. "
        "The row then exempts nothing, and the sweep next door stays red on a sentence the ruling "
        "released."
    )

    without_it = comparisons_offending(entries, exempt=without_this_row)
    assert key in without_it, (
        f"With {key!r} taken out of the exemption, the sweep reports {sorted(without_it)} and not "
        f"{key!r}. The row is excusing nothing: either the shipped sentence no longer carries any "
        f"word in {list(FORBIDDEN_COMPARISONS)}, in which case the row belongs deleted, or the key "
        "is spelled here in a way the registry does not publish."
    )


def test_every_exempt_key_is_a_key_the_registry_publishes() -> None:
    """An exemption for a key nobody publishes is a stale row.

    **The mutation it kills:** a refusal renamed or deleted in the registry with
    its exemption left behind, which leaves the sweep carrying a licence for a
    string that no longer exists and would silently cover a new entry that took
    the old spelling. **The near miss it spares:** a published key that is not
    exempt, which is the ordinary case and must not be reported here.

    **A red here means the exemption and the registry have come apart, not that
    the copy is wrong.**
    """
    published = set(every_entry())
    unpublished = [key for key in LEADERSHIP_ONLY_REFUSAL_KEYS if key not in published]
    on_the_surface = sorted(key for key in published if key.startswith(LEADERSHIP_SETS_PREFIX))
    assert not unpublished, (
        "These keys are exempted from the §4.1 item 1 sweep and the registry publishes none of "
        f"them: {unpublished}. It publishes {on_the_surface} under that prefix. An exemption is a "
        "statement about a shipped sentence; one naming no sentence is a licence waiting for "
        "whatever is spelled that way next."
    )


def test_the_not_leadership_refusal_is_published_and_is_not_exempt() -> None:
    """The one refusal of that surface a student can be served stays inside the sweep.

    `app.api.deps.require_leadership` answers this sentence to any session that is
    not a leadership session, a student's included, which is why
    `docs/disputes/E5-13-01.md` exempted some of that surface's refusals and not
    all eight.

    **The mutation it kills:** this key added to the exemption tuple, which would
    release the one sentence on the surface that §4.1 item 1 actually governs.
    **The near miss it spares:** the six keys beside it, which are exempt and
    stay exempt.

    **A red here means the exemption has been widened or the refusal has been
    unpublished, not that the copy is wrong.**
    """
    assert NOT_LEADERSHIP_KEY in every_entry(), (
        f"The registry publishes no {NOT_LEADERSHIP_KEY!r}. It is the 401 any session that is not "
        "a leadership session is refused with, so it is a string a student reads and the sweep "
        "next door has to be reading it."
    )
    assert NOT_LEADERSHIP_KEY not in LEADERSHIP_ONLY_REFUSAL_KEYS, (
        f"{NOT_LEADERSHIP_KEY!r} is in the exemption. The dispute's ruling exempts the "
        "refusals answered only behind `require_leadership`; this one is answered *by* "
        "`require_leadership`, to whoever failed it."
    )


# The §4.1 item 1 sweep this control exists for is
# `test_the_shipped_copy_names_nothing_a_student_may_not_see.py`, from E2-14. It
# stood here, holding `@pytest.mark.invariant` on the test rather than on the
# module, which is the currency
# `test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
# refuses; it moved unchanged into a module whose name carries a denial shape, so
# that the sweep governs it and its next denial test inherits the marker. The
# vocabulary and the reader stay here and are imported from there.
