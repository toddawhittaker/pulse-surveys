"""E2-14 item 3 — the copy registry's §4.1 denial, in the marker currency the sweep demands.

The test below is E2-08's, moved here unchanged from
`test_the_submit_paths_copy_is_externalised.py`, where it held
`@pytest.mark.invariant` **per test**. That is the currency
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
refuses, and it escaped that sweep only by filename: the host module's stem
carries no denial shape, so nothing demanded anything of it. The E2 boundary
review recorded the character precisely — the test **is** collected into the
isolated pass today, so this is a currency inconsistency and not lost coverage.

**The direction taken is extract, not widen, and the alternative is recorded
rather than left implied.** The other way to make the currency consistent is to
add the two host modules' stems to `DENIAL_NAME_SHAPES`. That was rejected: those
two modules hold about twenty-five tests between them that are not §4.1 denials —
registry shapes, key spellings, coaching copy, step rules — and widening the
shapes would enrol every one of them in CI's isolated pass on the strength of
their module's name. It would also put two sentences into a vocabulary that
otherwise says only what a module *denies*. Nothing is added to
`DENIAL_NAME_SHAPES` by this ticket.

**Where the moved docstring says "the sweep's own control above", the control is
now next door.** It is
`test_the_submit_paths_copy_is_externalised.py::test_the_comparison_sweep_sees_a_comparing_sentence_and_leaves_a_permitted_one`,
and it stays there on purpose: that test is deliberately **not** marked
`invariant` — "it asserts nothing about what ships, and CI's isolated §4.1 pass
should fail on the rule rather than on its instrument" — so moving it into a
module whose `pytestmark` carries the marker would have enrolled it in the pass
and contradicted its own reason for existing. A red in that control means the
sweep below is broken rather than that the copy is, exactly as before; what
changed is that the two now live one file apart, and this paragraph is the
pointer.

**What is not vacuous about this test on its own**, inside the isolated pass
where the control does not run: `every_entry` fails if the registry publishes no
entries at all, which is the emptiness this sweep could otherwise be satisfied
by.

**The sweep's vocabulary and its reader stay in the host module**, imported here
rather than copied — `FORBIDDEN_COMPARISONS` is E2-11's inventory's neighbour and
two copies of a word list is two lists to keep in step (`docs/MISTAKES.md` entry
13). The host module sits in this same directory, so pytest has already put
`tests/unit` on `sys.path` before this module is imported.

**This module's stem carries `names_nothing`, deliberately**, so the denial sweep
governs it from the day it lands: a later denial test added here inherits the
module-level marker, and a marker moved back onto a test turns that sweep red.

**What is swept, and what is exempt.** The sweep runs over every entry the copy
registry publishes, with six keys skipped by name:
`LEADERSHIP_ONLY_REFUSAL_KEYS`, the named-set API's 404, 403, 409 and three of
its 422s, each carrying the gate and the route that guards it beside it in the
host module. `docs/disputes/E5-13-01.md` ruled the narrowing and ADR 0177 records
it. The ruling's count was seven; six is what the rows earn, because the fourth
422 — `leadership_comparison_sets.member_not_a_course` — carries no swept word
and an exemption row for it would be excusing nothing. The reason the rest are
exempt is that those sentences are answered only to a request that has
already passed the leadership gate, so no student can be served one, and the
registry stopped being a registry of students' strings when E5-13 put them in it
— a sweep with no audience model is the closed-set guard `docs/MISTAKES.md` entry
53 describes, one level out, where what encloses the set is who can be served the
string.

**The exemption is by key and not by surface**, because the same surface has a
refusal a student can be served, `leadership_comparison_sets.not_leadership`,
which `app.api.deps.require_leadership` answers to any session that is not a
leadership session — a student's included. That key stays inside the sweep, and a control
next door asserts it is published and not exempt. A leadership-only refusal that
later becomes reachable by a student leaves the tuple in the same change.

**The exemption's own controls are next door too**, unmarked, for the reason this
module's other control is: the reader catching a benchmark sentence under a
student prefix while letting the same sentence by under an exempt key; each
exemption row being load-bearing, proven by removing it and watching its key come
back into the offending set; and every exempt key being one the registry actually
publishes, so that a renamed refusal cannot leave a licence behind.
"""

import pytest
from test_the_submit_paths_copy_is_externalised import (
    LEADERSHIP_ONLY_REFUSAL_KEYS,
    comparisons_offending,
    every_entry,
)

pytestmark = pytest.mark.invariant


def test_no_shipped_copy_string_shows_a_student_a_comparison() -> None:
    """SPEC §4.1 item 1, asserted from E2 as that item says it is.

    > Students never see comparables, benchmarks, university averages, or other
    > sections — in charts, text, tooltips, exports, or aria labels. *(Asserted
    > from **E2**, the first epic with a student-visible path ...)*

    Every string in the registry is swept, not only this ticket's, because the
    package is the shape E2-09 and E2-10 add to and the rule is about what a
    student reads rather than about which ticket wrote it. Item 4's ranking
    vocabulary is swept with it, for the same reason: it forbids the same family
    of sentence. The six keys of `LEADERSHIP_ONLY_REFUSAL_KEYS` are the one
    exemption, ruled in `docs/disputes/E5-13-01.md` and recorded in ADR 0177; this
    module's docstring says what they are and why, and the other two refusals of
    the same surface stay swept — one because `require_leadership` answers it to
    students, one because it carries no swept word to excuse.

    **The mutation it kills:** a helpful sentence added to a bounce — "most
    students in your section wrote more" — which is a comparison reaching a
    student through copy rather than through a chart, and which no chart test
    would ever see. **The near miss it spares:** the same words in a refusal only
    a leadership session can provoke, which is what the exemption releases and
    what a row-by-row control next door proves is released deliberately. **What
    makes it non-vacuous:** the sweep's own control above, the exemption's three
    controls next door, and the assertion that the registry is not empty in
    `every_entry`.
    """
    offending = comparisons_offending(every_entry(), exempt=LEADERSHIP_ONLY_REFUSAL_KEYS)
    assert not offending, (
        f"These shipped strings show a student a comparison: {offending}. SPEC §4.1 item 1 is a "
        "hard visibility invariant, and copy is a surface exactly as a chart is — the item names "
        "'charts, text, tooltips, exports, or aria labels'. A string here that no student can be "
        "served is a dispute about the exemption in `LEADERSHIP_ONLY_REFUSAL_KEYS` rather than a "
        "sentence to reword quietly."
    )
