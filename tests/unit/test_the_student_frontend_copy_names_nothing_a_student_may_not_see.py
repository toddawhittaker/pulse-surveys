"""SPEC §4.1 item 1 over the student pages' frontend copy — E8-05, done-when 3.

> 3. **Student copy is swept for comparison words in the isolated pass.** An
>    `invariant`-marked test runs the item 1 word check (`comparisons_offending`)
>    over every `student_*` key of the frontend copy inventory, with a planted
>    offender as its control.

`test_the_shipped_copy_names_nothing_a_student_may_not_see.py` sweeps the backend
copy registry only (`every_entry`). The pages a student reads — the survey, the
results page, the landing — render frontend copy modules under `student_*`
prefixes, which the E8 boundary review found swept for item 1 nowhere in the
isolated pass: the enclosure one level out (`docs/MISTAKES.md` entry 53).

**Read the way the copy inventory reads it**: `collect_frontend_copy` over
`FRONTEND_COPY_DIRECTORY` (`tests/fixtures/copy_inventory.py`), the same
collector `test_the_shipped_copy_inventory_holds_to_items_four_and_five.py` uses,
and the same word check and vocabulary as the registry sweep, imported rather
than copied (entry 13).

**The control is in the test's own body**, because CI's isolated pass runs only
marked tests and a control outside it would not run where the rule does: a
`student_*` key carrying a comparing sentence is planted beside the collected
inventory and must be reported; a permitted sentence under the same prefix, and
the comparing sentence under a non-student prefix, must not be. And the
collection must find the two student pages' prefixes, so a collector gone blind
cannot pass (entries 3 and 35).
"""

import pytest
from fixtures.copy_inventory import (
    FRONTEND_COPY_DIRECTORY,
    CopyString,
    collect_frontend_copy,
    prefix_of,
)
from test_the_submit_paths_copy_is_externalised import (
    A_COMPARING_SENTENCE,
    A_PERMITTED_SENTENCE,
    comparisons_offending,
)

pytestmark = [pytest.mark.invariant]

STUDENT_PREFIX = "student_"
# Two student pages whose copy the collector must find, or the sweep read nothing.
PAGES_THAT_MUST_BE_FOUND = ("student_survey", "student_results")

PLANTED_OFFENDER = CopyString("student_results.a_planted_probe", A_COMPARING_SENTENCE, "planted")
PLANTED_PERMITTED = CopyString("student_results.a_permitted_probe", A_PERMITTED_SENTENCE, "planted")
PLANTED_ELSEWHERE = CopyString("instructor_report_page.a_probe", A_COMPARING_SENTENCE, "planted")


def student_keys(strings: list[CopyString]) -> dict[str, CopyString]:
    """Every collected string under a `student_*` prefix, by key."""
    return {
        string.key: string for string in strings if prefix_of(string.key).startswith(STUDENT_PREFIX)
    }


def test_no_student_page_copy_string_names_a_comparison() -> None:
    """Every `student_*` frontend string, swept for item 1's words, after its planted control.

    **The mutations this kills:** a sentence such as "most students in other
    sections rated this higher" added to the results page's copy (a comparison
    reaching a student through a page string, which no payload test sees), and a
    student copy module the sweep stops reading. **The near misses:** the permitted
    sentence under a student prefix, and the comparing sentence under the
    instructor's, which this sweep does not govern.
    """
    collected = collect_frontend_copy(FRONTEND_COPY_DIRECTORY)
    swept = student_keys(collected)
    found = {prefix_of(key) for key in swept}
    missing = [page for page in PAGES_THAT_MUST_BE_FOUND if page not in found]
    assert not missing, (
        f"The frontend collector found no `{missing}` strings (it found {sorted(found)}), so this "
        "sweep would pass over pages it never read."
    )

    planted = student_keys([*collected, PLANTED_OFFENDER, PLANTED_PERMITTED, PLANTED_ELSEWHERE])
    caught = comparisons_offending(planted)
    assert PLANTED_OFFENDER.key in caught, "The sweep missed a planted comparing student string."
    assert PLANTED_PERMITTED.key not in caught, "The sweep took a permitted student string."
    assert PLANTED_ELSEWHERE.key not in planted, "The selection took a non-student prefix."

    offending = comparisons_offending(swept)
    assert not offending, (
        f"These student-page strings show a student a comparison: {offending}. SPEC §4.1 item 1: "
        "students never see comparables, benchmarks, university averages, or other sections — in "
        "charts, text, tooltips, exports, or aria labels."
    )
