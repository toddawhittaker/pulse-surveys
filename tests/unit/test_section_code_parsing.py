"""A section code splits into three parts, or it is refused — ticket E0-07.

Acceptance criteria 2 and 3, and the half of criterion 1 that needs no calendar:
`R3WW` and `Q2FF` parse to the values SPEC §2.2 describes, and a code with an
unknown modality or a missing ordinal raises a distinct error naming the
offending part. The rest of the criteria need a term and its start-letter map and
live in `tests/integration/test_section_date_derivation.py`.

**Where the line between the two modules falls, and why it falls there.** A start
letter means a length and a start date *within one term* (§2.2), and the map is
per-term admin configuration (E0-06). So "unknown start letter" is a question
about a term's map, not about the alphabet, and asserting it here would need this
file to invent a set of letters that are structurally legal — deciding, from the
test suite, that `A` may never be a start letter in any term anyone configures.
That criterion is asserted where the map exists. What is here is the grammar:
three parts, a closed set of two modality suffixes, and an ordinal that has to be
present.

**Nothing in this file names anything inside the service.** E0-07 spells the file
and the four values the derivation produces, and no callable, no error class and
no result shape. `tests/conftest.py`'s `SectionCodeService` does the finding and
says at length why; what is left here is a small constant listing the names a
part might be carried under, which is this file's choice and a one-line change.

**The full start-letter map is a property, not a list of examples.** SPEC §9.1
puts "section-code parsing tests across the full start-letter map" in the
invariant suite, and the Fall 2026 seed map has twenty start positions across
seven lengths — fourteen letters and the six numbers §2.2 gives the 3-week
sections. Writing twenty examples would test the same three lines of parsing
twenty times and still miss the combination nobody thought of, so the round trip
is generated. The numbered starts get an example of their own as well: a leading
digit is the one place where a parser can read the start position as the ordinal
and produce a well-formed answer to the wrong question.
"""

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# The two codes acceptance criterion 2 names, from SPEC §2.2's own examples.
SPEC_ONLINE_CODE = "R3WW"
SPEC_FACE_TO_FACE_CODE = "Q2FF"

# SPEC §2.2's Fall 2026 seed map, as start positions only: 12-week U/R/Q, 6-week
# E/F/H, 8-week X/Y/Z, 10-week S/T, 15-week V/D, 16-week K, and the 3-week
# sections, which §2.2 numbers 2 through 7 rather than lettering. Lengths and
# dates belong to a term's map row and are asserted in the integration module;
# what this file needs is the set of first characters a real code can carry.
LETTERED_STARTS = ("U", "R", "Q", "E", "F", "H", "X", "Y", "Z", "S", "T", "V", "D", "K")
NUMBERED_STARTS = ("2", "3", "4", "5", "6", "7")
SEED_MAP_STARTS = LETTERED_STARTS + NUMBERED_STARTS

# SPEC §2.2: "Modality: `WW` online, `FF` face-to-face." A closed set of two —
# E0-07: "Unknown suffixes are an error, not a silent default."
ONLINE_SUFFIX = "WW"
FACE_TO_FACE_SUFFIX = "FF"

# **This file's choice**, and the only names here that are not in a ticket or the
# spec. E0-07 calls the three parts "start letter, ordinal, and modality"; these
# are the spellings a result could plausibly carry them under, most likely first,
# so a rename is one line. `SectionCodeService.part` prints both sides when none
# of them is there.
START_LETTER_NAMES = ("start_letter", "start", "letter")
ORDINAL_NAMES = ("ordinal", "number", "index")
MODALITY_NAMES = ("modality",)

# **Also this file's choice.** Criterion 3 wants an error "naming the offending
# part", and a message is prose. Each part is accepted under any of the words
# below, matched case-insensitively, so an implementation is free to phrase the
# sentence and is not free to raise the same anonymous "invalid section code" for
# all three.
PART_WORDS: dict[str, tuple[str, ...]] = {
    "modality": ("modality", "suffix"),
    "ordinal": ("ordinal",),
}

# Codes that are not `{startLetter}{ordinal}{modality}` in any reading. The
# definition of done asks for parsing to be total — "no code path where a
# malformed code silently produces a valid-looking section" — and these are the
# shapes a roster sync can hand it: a truncation, a repeat, a separator, a code
# with the parts in the wrong order, and the empty string.
MALFORMED_CODES = (
    "",
    "R",
    "R3",
    "R3W",
    "3WW",
    "RRWW",
    "WW3R",
    "R-3WW",
    "R3WWW",
    "R33WWFF",
)


def parse(section_codes: Any, code: str) -> Any:
    """Parse `code`, or fail saying which call shape the service refused."""
    return section_codes.call(section_codes.parse, code=code)


def refusal(section_codes: Any, code: str) -> BaseException:
    """The exception parsing `code` raised, or a failure saying it raised none.

    `Exception` and not `BaseException`: `pytest.fail` raises an outcome that
    inherits from `BaseException`, and catching it here would turn a fixture's
    diagnosis — "there is no such module", "there are two candidate parsers" —
    into a passing assertion that the code was refused. That is
    `docs/MISTAKES.md` entry 3 exactly: the test would go green on a service
    that does not exist.
    """
    try:
        parsed = parse(section_codes, code)
    except Exception as raised:
        return raised
    pytest.fail(
        f"Parsing {code!r} returned {parsed!r} instead of raising. E0-07: 'reject malformed "
        "codes with a specific error naming what failed', and the definition of done asks for "
        "no code path where a malformed code silently produces a valid-looking section. A code "
        "that parses to something is a section with a length, a start date and an end date "
        "derived from nothing."
    )


def assert_names_the_part(failure: BaseException, part: str, code: str) -> None:
    """The error says which part of `code` was wrong."""
    words = PART_WORDS[part]
    message = str(failure).lower()
    assert any(word in message for word in words), (
        f"Parsing {code!r} raised {failure!r}, whose message names none of {list(words)}. "
        "Criterion 3 wants 'a distinct error naming the offending part': the code arrives from "
        "the LMS, so the person reading the failure is an operator looking at a roster sync, and "
        "'invalid section code' tells them to go and work out which of the three parts is wrong. "
        "If the part is named in a word this file does not list, add it to `PART_WORDS`."
    )


def assert_raised_by_the_service(section_codes: Any, failure: BaseException, code: str) -> None:
    """The error is one this project defines, not one that leaked out of a builtin."""
    assert section_codes.raised_by_the_service(failure), (
        f"Parsing {code!r} raised {failure!r}, which `{type(failure).__module__}` defines rather "
        "than this project. E0-07's definition of done: section codes arrive from the LMS, so "
        "confirm parsing is total, with 'no exception type that escapes as a 500'. A `KeyError` "
        "off a letter lookup, an `IndexError` off a short string or a `ValueError` out of "
        "`int()` is what an unguarded parser raises, and none of them is something a caller can "
        "catch on purpose or turn into a 4xx."
    )


def modality_meaning(value: Any) -> str:
    """A modality rendered as text, whether it is an enum member or a string.

    E0-07 does not say what a modality *is* — a `str`, a `StrEnum`, an `Enum`
    whose members are named for the two meanings — so the tests read it as text
    and ask what it says. `Modality.ONLINE`, `"online"` and `"ONLINE"` all
    answer; the raw suffix `"WW"` does not, and that is the point: the ticket
    calls this a mapping, and a value that still spells the suffix has not
    mapped anything.
    """
    return str(getattr(value, "value", value)).lower() + " " + str(value).lower()


def test_the_spec_example_code_parses_into_its_three_parts(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """Criterion 2, first half: `R3WW` parses to the values §2.2 describes.

    Start letter `R`, ordinal 3, online. All three in one test because the
    criterion is about one code being read correctly, and a start letter that is
    right while the ordinal is wrong is one defect, not two.

    The three parts are read by name rather than by position, so a result that
    carries them in the wrong order is caught rather than silently reindexed.

    `configured_env` sets every variable `.env.example` documents before the
    module is imported. Nothing in a parser should need configuration, but a
    service module that reaches a session type through `app.db` builds an engine
    out of `Settings()` at import — the epic README's second settled rule — and
    that is a failure worth seeing as an import error in CI rather than as a
    collection error here.
    """
    parsed = parse(section_codes, SPEC_ONLINE_CODE)

    start_letter = section_codes.part(parsed, START_LETTER_NAMES, "start letter")
    ordinal = section_codes.part(parsed, ORDINAL_NAMES, "ordinal")
    modality = section_codes.part(parsed, MODALITY_NAMES, "modality")

    assert str(start_letter) == "R", (
        f"{SPEC_ONLINE_CODE!r} parsed to a start letter of {start_letter!r}. SPEC §2.2 reads the "
        "code as `{startLetter}{ordinal}{modality}`, so the start letter is the single leading "
        "character `R` — the whole term's calendar for this section hangs off it, since the "
        "letter is what the start-letter map is keyed by."
    )
    assert int(ordinal) == 3, (
        f"{SPEC_ONLINE_CODE!r} parsed to an ordinal of {ordinal!r} rather than 3. The ordinal is "
        "what distinguishes one section of a course from the next in the same term, and reading "
        "it off the wrong character is how `23WW` becomes section 2 of nothing."
    )
    assert "online" in modality_meaning(modality), (
        f"{SPEC_ONLINE_CODE!r} parsed to a modality of {modality!r}. SPEC §2.2: '`WW` online, "
        "`FF` face-to-face'. A value that still spells the suffix has not mapped it, and every "
        "later reader has to keep the mapping in their head."
    )


def test_the_spec_face_to_face_example_parses_into_its_three_parts(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """Criterion 2, second half: `Q2FF` parses to the values §2.2 describes.

    The second of the two codes the criterion names, and not a duplicate of the
    first: every part differs. It is the case that fails against a parser that
    reads the ordinal from a fixed offset that happens to work for one code, and
    the only one of the two that can catch a modality hardcoded to online.
    """
    parsed = parse(section_codes, SPEC_FACE_TO_FACE_CODE)

    start_letter = section_codes.part(parsed, START_LETTER_NAMES, "start letter")
    ordinal = section_codes.part(parsed, ORDINAL_NAMES, "ordinal")
    modality = section_codes.part(parsed, MODALITY_NAMES, "modality")

    assert str(start_letter) == "Q", (
        f"{SPEC_FACE_TO_FACE_CODE!r} parsed to a start letter of {start_letter!r} rather than "
        "'Q'. §2.2's Fall 2026 seed map has Q as a 12-week letter starting 9/28."
    )
    assert (
        int(ordinal) == 2
    ), f"{SPEC_FACE_TO_FACE_CODE!r} parsed to an ordinal of {ordinal!r} rather than 2."
    assert "face" in modality_meaning(modality), (
        f"{SPEC_FACE_TO_FACE_CODE!r} parsed to a modality of {modality!r}. SPEC §2.2: '`FF` "
        "face-to-face'. This is the half a parser defaulting to online passes anyway, which is "
        "why both spec examples are asserted rather than one."
    )


def test_the_two_modality_suffixes_do_not_parse_to_the_same_value(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """`WW` and `FF` are two meanings, not one field carried along.

    The two codes differ only in the suffix, so a parser that returns a constant
    modality — or that copies the suffix straight through without mapping, and
    then has both compare equal after some normalisation — is caught here. It is
    a separate test from the two above because it fails for a different reason:
    those check that each suffix means the right thing, and this checks that the
    field is a distinction at all, which is what makes an "unknown suffix" error
    worth raising in the first place.
    """
    online = section_codes.part(parse(section_codes, "R3WW"), MODALITY_NAMES, "modality")
    face_to_face = section_codes.part(parse(section_codes, "R3FF"), MODALITY_NAMES, "modality")

    assert online != face_to_face, (
        f"`R3WW` and `R3FF` both parse to a modality of {online!r}. SPEC §2.2 maps the two "
        "suffixes to two modalities, and §5.1's comparison sets and the aggregate views both "
        "read it — a single value collapses online and face-to-face sections into one "
        "population without anything reporting that it did."
    )


@pytest.mark.parametrize("code", ["R3WF", "R3FW"])
def test_a_modality_suffix_one_character_from_a_known_one_is_refused(
    configured_env: dict[str, str], section_codes: Any, code: str
) -> None:
    """The suffix set is closed, and the near misses are the ones that get in.

    `WF` and `FW` each differ from both `WW` and `FF` by a single character, so
    they are what a check written as "starts with W", "ends with F", "contains a
    W", or `set(suffix) <= {"W", "F"}` accepts. Every one of those passes the two
    spec examples above and every obviously-wrong suffix below, and quietly
    invents a modality for a code the LMS never meant to send.

    E0-07: "Unknown suffixes are an error, not a silent default."
    """
    failure = refusal(section_codes, code)

    assert_raised_by_the_service(section_codes, failure, code)
    assert_names_the_part(failure, "modality", code)


def test_an_unknown_modality_suffix_is_refused_and_the_error_names_it(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """Criterion 3: an unknown modality raises an error naming the modality.

    `R3ZZ` is well-formed in every other respect — a start letter §2.2 maps, an
    ordinal, a two-character suffix — so nothing but the modality can be what is
    refused.
    """
    code = "R3ZZ"
    failure = refusal(section_codes, code)

    assert_raised_by_the_service(section_codes, failure, code)
    assert_names_the_part(failure, "modality", code)


def test_a_code_with_no_ordinal_is_refused_and_the_error_names_the_ordinal(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """Criterion 3: a missing ordinal raises an error naming the ordinal.

    `RWW` is the case the criterion names. It is chosen over `2WW`, which is
    missing an ordinal too, because `2WW` has two readings — a numbered 3-week
    start with no ordinal, or an ordinal with no start — and an implementation
    that names either part is answering honestly. `RWW` has one reading, so the
    error has one right thing to name.

    The interesting failure this catches is not a parser that crashes. It is one
    that treats the ordinal as optional and defaults it to 1: every `RWW` in a
    roster then becomes section 1 of its course, silently colliding with the real
    `R1WW` under E0-06's uniqueness rule over `(course, term, code)` — or worse,
    not colliding, and running as a second section 1.
    """
    code = "RWW"
    failure = refusal(section_codes, code)

    assert_raised_by_the_service(section_codes, failure, code)
    assert_names_the_part(failure, "ordinal", code)


def test_an_unknown_modality_and_a_missing_ordinal_raise_errors_a_caller_can_tell_apart(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """Criterion 3's word "distinct", for the two failures that need no map.

    The third — an unknown start letter — is a question about a term's map and is
    asserted alongside these two in
    `tests/integration/test_section_date_derivation.py`, which has one.

    Distinct means a caller can tell which part failed without reading English:
    either the exception types differ, or the messages do. One anonymous
    `SectionCodeError("bad code")` for every case satisfies "raises an error" and
    satisfies nothing else, and it is what the E1 roster sync will have to
    surface to an operator.
    """
    modality_failure = refusal(section_codes, "R3ZZ")
    ordinal_failure = refusal(section_codes, "RWW")

    different_types = type(modality_failure) is not type(ordinal_failure)
    different_messages = str(modality_failure) != str(ordinal_failure)

    assert different_types or different_messages, (
        f"`R3ZZ` and `RWW` both raise {modality_failure!r}: same type, same message. Criterion 3 "
        "asks for a *distinct* error naming the offending part for each of the three failures. "
        "Two different defects in a roster feed — a modality nobody configured and a code that "
        "lost its ordinal — need two different things done about them."
    )


@pytest.mark.parametrize("code", MALFORMED_CODES)
def test_a_malformed_code_is_refused_by_the_services_own_error(
    configured_env: dict[str, str], section_codes: Any, code: str
) -> None:
    """The definition of done: parsing is total and refuses what it cannot read.

    "No code path where a malformed code silently produces a valid-looking
    section", and no exception type that escapes as a 500. Each of these is a
    shape a roster sync can hand the parser: a truncation, a repeat, a separator,
    the parts in the wrong order, the empty string.

    The empty string is the one worth naming. It is what an LMS field that was
    never filled in arrives as, and it is the input that turns an unguarded
    `code[0]` into an `IndexError` — a 500 on the sync rather than a named
    section that could not be read.
    """
    failure = refusal(section_codes, code)

    assert_raised_by_the_service(section_codes, failure, code)


def test_a_numbered_three_week_code_reads_its_leading_digit_as_the_start_position(
    configured_env: dict[str, str], section_codes: Any
) -> None:
    """§2.2's 3-week sections are "numbered 2-7" where every other length is lettered.

    `23WW` is start position 2, ordinal 3 — not start position nothing, ordinal
    23, and not start position 2 with the ordinal missing. This is the boundary
    case the ticket calls out ("Handle the 3-week case, which §2.2 numbers 2-7
    rather than lettering"), and it has two distinct wrong answers that both look
    plausible:

      - A parser written `^([A-Z])(\\d+)(WW|FF)$` refuses every 3-week section in
        the institution. That fails loudly, at roster sync, for a sixth of the
        start positions in the map.
      - A parser that consumes digits greedily from the front reads the ordinal
        as 23 and finds no start position. That one is worse, because a code
        whose ordinal is a plausible number produces a section that looks fine
        and is keyed to nothing in the letter map.

    Whether a start position outside 2-7 is legal is a question about a term's
    map and is asserted in the integration module, not here.
    """
    parsed = parse(section_codes, "23WW")

    start = section_codes.part(parsed, START_LETTER_NAMES, "start letter")
    ordinal = section_codes.part(parsed, ORDINAL_NAMES, "ordinal")

    assert str(start) == "2", (
        f"`23WW` parsed to a start position of {start!r} rather than '2'. SPEC §2.2 numbers the "
        "3-week sections 2 through 7 instead of lettering them, so the first character of a code "
        "is a start position whether it is a letter or a digit."
    )
    assert int(ordinal) == 3, (
        f"`23WW` parsed to an ordinal of {ordinal!r} rather than 3. Reading the digits greedily "
        "gives 23, which is a perfectly plausible ordinal and leaves the start position empty — "
        "a section that parses, derives from no map row, and is wrong in a way nothing reports."
    )


@settings(
    max_examples=200,
    # `configured_env` is function-scoped, so Hypothesis is right to warn that
    # examples share it. It sets environment variables and moves the working
    # directory, and no example changes either, so there is no state to reset
    # between them.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    start=st.sampled_from(SEED_MAP_STARTS),
    ordinal=st.integers(min_value=1, max_value=9),
    suffix=st.sampled_from((ONLINE_SUFFIX, FACE_TO_FACE_SUFFIX)),
)
def test_every_start_position_in_the_fall_2026_map_survives_the_round_trip(
    configured_env: dict[str, str],
    section_codes: Any,
    start: str,
    ordinal: int,
    suffix: str,
) -> None:
    """SPEC §9.1: section-code parsing across the full start-letter map.

    Every start position in §2.2's Fall 2026 seed map, against both modalities
    and every single-digit ordinal — 240 codes, of which a hand-written list
    would hold three. What generation buys over examples here is the
    combinations: a parser that mishandles `F` because the letter also appears in
    the `FF` suffix, or `Z` because it appears in nothing, or one of the six
    digits, is found without anyone having thought of that letter.

    Ordinals stop at 9 deliberately. Whether a section can be `R10WW` is not
    something §2.2 says, and generating a two-digit ordinal would make this
    property decide it.
    """
    code = f"{start}{ordinal}{suffix}"
    parsed = parse(section_codes, code)

    assert str(section_codes.part(parsed, START_LETTER_NAMES, "start letter")) == start, (
        f"{code!r} did not parse back to the start position {start!r}. Every start position in "
        "SPEC §2.2's Fall 2026 seed map has to survive the round trip: the letter is the key the "
        "start-letter map is read by, so a letter that parses wrong derives its dates from "
        "another cohort's row."
    )
    assert (
        int(section_codes.part(parsed, ORDINAL_NAMES, "ordinal")) == ordinal
    ), f"{code!r} did not parse back to the ordinal {ordinal}."

    meaning = modality_meaning(section_codes.part(parsed, MODALITY_NAMES, "modality"))
    expected = "online" if suffix == ONLINE_SUFFIX else "face"
    assert (
        expected in meaning
    ), f"{code!r} parsed to a modality that does not read as {expected!r}: {meaning!r}."


@settings(
    max_examples=300,
    # Two seconds per example, against a function that does no I/O. This is the
    # only assertion available for the definition of done's "no unbounded loop":
    # a parser that backtracks catastrophically on a crafted code does not fail
    # an assertion, it stops answering, and a deadline is what turns that into a
    # test failure rather than a hung CI job. Two seconds and not two hundred
    # milliseconds because the number that matters is the difference between
    # "slow on a loaded runner" and "not coming back", and a tight deadline here
    # buys a flake rather than a finding.
    deadline=2000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(code=st.text(max_size=12))
def test_parsing_arbitrary_text_either_answers_or_raises_the_services_own_error(
    configured_env: dict[str, str], section_codes: Any, code: str
) -> None:
    """The definition of done, in one property: parsing is total.

    "Section codes arrive from the LMS, so confirm parsing is total: no unbounded
    loop, no exception type that escapes as a 500." A section code is a string
    off a launch claim or a roster payload, so the input space is whatever the
    platform sends — including empty strings, whitespace, unicode, and codes from
    an institution that spells them differently.

    Two outcomes are allowed and no third one is: a parsed answer, or an error
    this project defines and a caller can catch. What this refuses is the leaked
    builtin — `ValueError` out of `int()`, `IndexError` off `code[0]`, `KeyError`
    off a suffix lookup, `AttributeError` off a `None`. Every one of those
    reaches FastAPI as an unhandled exception and leaves the operator with a 500
    where they should have had "this section code could not be read".

    The property deliberately does not say which strings parse. `st.text()`
    generates valid codes now and then, and a parser that accepts them is right
    to.
    """
    try:
        section_codes.call(section_codes.parse, code=code)
    except Exception as failure:
        assert section_codes.raised_by_the_service(failure), (
            f"Parsing {code!r} raised {failure!r}, defined by "
            f"`{type(failure).__module__}` rather than by this project. E0-07's definition of "
            "done asks for no exception type that escapes as a 500. This one is not a decision "
            "the service made about a code it could not read — it is the shape of the "
            "implementation showing through, and the caller has nothing to catch."
        )
