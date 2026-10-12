"""§4.1 item 3 up the chain: no comment on a roll-up, and the drill-down's hold across Mondays — E9-12 done-when 3.

> 3. **§4.1 item 3 up the chain (ruling 2).** No roll-up, tree, attention or
>    named-set response carries a comment's text, a summary, a theme or a
>    comment count. The drill-down of a section-week with a stream below the
>    threshold carries no comment text for that stream and carries its small-N
>    state, read this Monday and next across a release batch. Marked
>    `invariant`.

README ruling 2: "No comments on roll-up pages. Leaders read raw comments only
inside a section drill-down, under that section's own per-stream threshold and
release batches." SPEC §4.1 item 3: below the n-threshold "raw comments in that
stream are hidden from instructors and students alike" — and a leader reading the
drill-down reads the instructor's report wholesale (§5.5).

**The world** is E6-05's lead-review world over the canonical report world
(`tests/fixtures/report_api.py`): section `F1WW`'s course week 1 has five
commenters in the instructor stream (at the threshold, so its comments show);
course weeks 3 and 4 have three and two, each **below** it, so their comments are
held; together they are five distinct people, which is what opens ADR 0152's
release gate once week 4 has closed.

**The roll-up half** reads every roll-up response a lead, the chair and a dean
are served — trees, every node's figures with a card on every section, and a
named-set series — and requires none of the planted comment texts anywhere, and
no key naming a comment, a summary or a theme at any depth. **Its present twin:**
the lead's drill-down of the same section's week 1 does carry those texts, so
they are reachable and the absence above is the roll-up's.

**The drill-down half is a sequence, not a payload** (`docs/MISTAKES.md` entry
51): the clock stands at week 3's Monday, the cutter runs as the Monday beat
would, and week 3 is read; then at week 4's Monday, the cutter runs again, and
weeks 3 and 4 are read. A held comment must never appear under a week — not on
its own week's page on either Monday, and on the later Monday only in the
release, which names no week.

**Expected green on today's branch**; each test names its mutation and near miss.
"""

from typing import Any

import pytest
from fixtures.e9_invariant_pass import (
    BY_LEAD_KINDS,
    FIGURE_KINDS,
    a_named_set,
    body_of,
    comment_shaped_keys,
    drill_down_url,
    figures_url,
    found_in,
    owe_every_section,
    series_url,
    term_of,
    tree_nodes,
    tree_url,
)
from fixtures.lead_review import LeadReviewWorld, Reader
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    COMMENTS_FIELD,
    FIRST_HELD_WEEK,
    FULL_WEEK,
    FULL_WEEK_COMMENTS,
    HELD_COMMENTS,
    PAYLOAD_STREAM_KEY,
    RELEASED_MEMBER,
    SECOND_HELD_WEEK,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUPPRESSED_FIELD,
    TAUGHT_COHORT,
    once_the_report_has_opened,
)
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

DEAN_ROLE = "DEAN"
SIX_WEEKS = 6


def every_planted_comment() -> dict[str, str]:
    texts = {f"full week comment {i}": text for i, text in enumerate(FULL_WEEK_COMMENTS)}
    for week, held in HELD_COMMENTS.items():
        texts.update({f"held week {week} comment {i}": text for i, text in enumerate(held)})
    return texts


def held_texts() -> dict[str, str]:
    return {
        f"held week {week} comment {i}": text
        for week, held in HELD_COMMENTS.items()
        for i, text in enumerate(held)
    }


def drill(review: LeadReviewWorld, reader: Reader, course_week: int) -> Any:
    section = review.world.section_id(TAUGHT_COHORT)
    return body_of(
        review.ask("GET", drill_down_url(section, course_week), token=reader.token),
        f"{reader.label}'s drill-down of course week {course_week}",
    )


def instructor_stream(body: Any) -> dict[str, Any]:
    return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[INSTRUCTOR_STREAM]]


def stream_texts(body: Any) -> list[str]:
    return [str(card.get(COMMENT_TEXT_FIELD)) for card in instructor_stream(body)[COMMENTS_FIELD]]


# ---------------------------------------------------------------------------
# The roll-up half.
# ---------------------------------------------------------------------------


def test_no_rollup_tree_figures_card_or_series_response_carries_a_comment(
    lead_review: LeadReviewWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every roll-up response to three readers: no planted comment text, no comment-shaped key.

    **The present twin:** the lead's drill-down of week 1 carries the full week's
    comments, so the texts are live in this world.

    **The mutation it kills:** a `summary`, `themes`, `comments` or
    `comment_count` member put on the roll-up schema (even left null — the key
    alone is caught); comments pooled at a course or prefix node, or at a by-lead
    group (whose figures are read for the chair and the dean too, and at least
    one is required to have been read); a card that quotes a comment. **The near
    miss it spares:** section counts, rates, means and labels.
    """
    review = lead_review
    assert review.lead is not None and review.chair is not None
    dean = review.a_leader("e9-12-dean", grants=((DEAN_ROLE, review.college),))
    owe_every_section(monkeypatch)
    term = term_of(review)
    set_id = a_named_set(review, review.own_course, length=SIX_WEEKS, level_of=review.own_course)

    answers: dict[str, Any] = {}
    for reader in (review.lead, review.chair, dean):
        tree = body_of(review.ask("GET", tree_url(term), token=reader.token), f"{reader.label}")
        answers[f"{reader.label}'s tree"] = tree
        for node in tree_nodes(tree):
            if node.get("kind") in (*FIGURE_KINDS, *BY_LEAD_KINDS):
                url = figures_url(node["kind"], node["id"], term)
                answers[f"{reader.label}'s {node['kind']} {node.get('name')}"] = body_of(
                    review.ask("GET", url, token=reader.token), f"{reader.label}'s figures"
                )
        answers[f"{reader.label}'s series"] = body_of(
            review.ask("GET", series_url(set_id, term), token=reader.token), f"{reader.label}"
        )

    twin = drill(review, review.lead, FULL_WEEK)
    shown = found_in(twin, {f"full {i}": t for i, t in enumerate(FULL_WEEK_COMMENTS)})
    assert shown, (
        "The present twin failed: the lead's drill-down of week 1 carries none of the full "
        "week's comments, so this world does not show a comment anywhere."
    )
    assert any(
        "attention" in str(body) for body in answers.values()
    ), "No figures answer was read, so the cards were never looked at."
    by_lead = [where for where in answers if any(f"'s {kind} " in where for kind in BY_LEAD_KINDS)]
    assert by_lead, (
        f"No by-lead group's figures were read; the reads were {sorted(answers)}. The chair and "
        "the dean are offered by-lead mode (E9-07), and its groups are roll-up responses too."
    )
    texts = {where: found_in(body, every_planted_comment()) for where, body in answers.items()}
    texts = {where: found for where, found in texts.items() if found}
    keys = {where: comment_shaped_keys(body) for where, body in answers.items()}
    keys = {where: found for where, found in keys.items() if found}
    assert not texts, f"Roll-up responses carry comment text: {texts}. README ruling 2."
    assert not keys, (
        f"Roll-up responses carry members naming a comment, a summary or a theme: {keys}. README "
        "ruling 2: aggregate pages carry figures and attention cards only."
    )


# ---------------------------------------------------------------------------
# The drill-down half: this Monday and the next, across a release batch.
# ---------------------------------------------------------------------------


def cut_now(review: LeadReviewWorld, comment_contract: Any) -> int:
    """Run the release cutter once, as the Monday beat does; how many batches it cut."""
    review.door.door.refresh()
    session = review.door.world.session
    cut = comment_contract.cut()(session)
    session.commit()
    return int(cut or 0)


def test_a_held_stream_shows_no_comment_under_its_week_on_this_monday_or_the_next(
    lead_review: LeadReviewWorld, comment_contract: Any
) -> None:
    """Week 3's Monday, then week 4's: a held comment never appears under a week.

    On week 3's Monday, week 3's instructor stream is held (three commenters):
    its small-N state says suppressed, its list is empty, and no held text is
    anywhere in the page. On week 4's Monday, after the cutter has run: week 3's
    page still holds none, and week 4's page carries the held texts **only** in
    the release, which names no week.

    **The premise, asserted:** a batch exists by week 4's Monday (five distinct
    people across weeks 3 and 4), so the sequence really crosses a release.
    **The present twin:** week 1's comments are shown in its stream.

    **The mutation it kills:** the drill-down serving a held stream's comments to
    a leader; the release placed on the page of the week its comments were held
    in (which names their week); a batch cut on week 3's Monday out of comments
    whose week had not closed. **The near miss it spares:** the release on the
    latest week's page, with no week named.
    """
    review = lead_review
    assert review.lead is not None
    door = review.door.door
    held = held_texts()

    door.pretend(once_the_report_has_opened(FIRST_HELD_WEEK))
    first_cut = cut_now(review, comment_contract)
    week3_then = drill(review, review.lead, FIRST_HELD_WEEK)

    door.pretend(once_the_report_has_opened(SECOND_HELD_WEEK))
    second_cut = cut_now(review, comment_contract)
    week3_now = drill(review, review.lead, FIRST_HELD_WEEK)
    week4_now = drill(review, review.lead, SECOND_HELD_WEEK)
    week1_now = drill(review, review.lead, FULL_WEEK)

    assert first_cut + second_cut >= 1, (
        f"The cutter cut {first_cut} then {second_cut} batches, so this world never crosses a "
        "release and the sequence below is not the one the criterion names. A broken world."
    )
    assert set(stream_texts(week1_now)) & set(
        FULL_WEEK_COMMENTS
    ), "The present twin failed: week 1's shown stream carries none of its comments."
    for what, page in (("week 3 on its Monday", week3_then), ("week 3 a week later", week3_now)):
        stream = instructor_stream(page)
        assert stream[SMALL_N_MEMBER][SUPPRESSED_FIELD] is True, (
            f"{what}: the instructor stream's small-N state is {stream[SMALL_N_MEMBER]!r}; three "
            "commenters is below the threshold."
        )
        assert stream[COMMENTS_FIELD] == [], f"{what}: the held stream lists comments."
        leaked = found_in(page, held)
        assert not leaked, (
            f"{what} carries held comments: {leaked}. A held comment surfaces only in a release "
            "batch, with no week named (SPEC §4)."
        )
    stream = instructor_stream(week4_now)
    assert stream[SMALL_N_MEMBER][SUPPRESSED_FIELD] is True
    assert stream[COMMENTS_FIELD] == [], "Week 4's held stream lists comments."
    released = found_in(week4_now.get(RELEASED_MEMBER), held)
    assert released, (
        "Week 4's page carries no held comment in its release after the cutter ran; the premise "
        "of the sequence (a release by the later Monday) does not hold."
    )
    rest_of_the_page = {key: value for key, value in week4_now.items() if key != RELEASED_MEMBER}
    outside = found_in(rest_of_the_page, held)
    assert not outside, f"Week 4's page carries held comments outside the release: {outside}."
