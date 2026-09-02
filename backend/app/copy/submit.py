"""What the weekly survey's submit path says to a student (SPEC §3.2, §3.3, §4.1).

Every sentence the route in `app.api.student` serves, keyed by a dotted key the
route looks it up by. Nothing in that module writes a sentence of its own, which
is what makes E2-11's inventory able to see all of them at once.

**The bounce copy is where §3.3 is most specific**, so it is worth quoting the
sentence these two entries are written against:

> a student typing "it was okay" is told immediately that the answer is too brief
> to count, before submission — never silently penalized after the fact, with
> coaching copy and one concrete example, never a shame state.

Three things follow, and each is visible in the two `submit.bounce.*` entries
below. *Coaching*: the sentence says what a useful answer looks like rather than
what the student did. *One concrete example*, in quotation marks, because an
instruction with no example is the copy that sentence exists to rule out — §3.3
writes its own examples the same way. *Never a shame state*: the student has done
nothing wrong, a classifier has judged one sentence, and the words are the whole
of what they experience.

**The two refused verdicts get two different sentences.** "It was okay" and
"adfasdfa" are different things to have typed, and one sentence for both tells a
student who wrote a terse real answer that they typed nonsense.

**SPEC §4.1 item 1 governs every string here**, not only the bounces: a student
never sees a comparable, a benchmark, a university average or another section, and
copy is a surface exactly as a chart is. So no sentence here says anything about
anybody but the reader.

**Two keys are settled outside this file.** `student.not_a_student` is the refusal
`app.api.deps.require_student` serves, and `submit.classifier_down` is ADR 0114's
honest retryable refusal. They are named in E2-08's work order, so they are the
two spellings this module may not choose.

**`student.not_a_student` lives in this module rather than one of its own**
because this is the surface it is served on: the student API's one write route.
E2-09 adds the read path's module beside this one and the two share the key.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY"]

# The refusal a request carrying no student session gets, and the refusal a
# request carrying somebody else's session gets — one sentence for both, because
# the two answers are required to be indistinguishable (E2-08's work order). It
# says what is true and names no role: "this is not a student session" and "there
# is no session" have to read alike, or the difference is a statement about which
# routes exist for which role.
NOT_A_STUDENT = "not signed in as a student"

# ADR 0114's refusal, for the provider failures ADR 0056 keeps outside the §3.3
# floor. Three things in one sentence, and each is load-bearing: the check did not
# happen (so the student is not told their comment was judged), the answers are
# still in front of them (so they do not retype the week), and there is a length of
# time worth waiting — which is the `Retry-After: 60` the route serves beside it.
CLASSIFIER_DOWN = (
    "We could not check your comment just now. Your answers are still in the form, "
    "so nothing is lost — please try again in a minute."
)

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        CopyEntry(key="student.not_a_student", text=NOT_A_STUDENT),
        CopyEntry(key="submit.classifier_down", text=CLASSIFIER_DOWN),
        # §3.3's two refused verdicts. Each says what a useful answer looks like
        # and gives one example in quotation marks, and neither says anything
        # about the person who typed it.
        CopyEntry(
            key="submit.bounce.insufficient",
            text=(
                "A sentence about your week is what counts here, and a few words on their own "
                'are too brief to. Something like "the pacing in week 3 was too fast" gives '
                "your instructor a specific thing to act on."
            ),
        ),
        CopyEntry(
            key="submit.bounce.nonsense",
            text=(
                "This did not come through as a comment about the course. One short, real "
                'sentence is plenty — "the lab instructions were hard to follow" is the kind of '
                "thing that helps."
            ),
        ),
        # SPEC §3.1: "Missed weeks cannot be back-filled." The section is the
        # student's own, so the refusal is honest about what happened rather than
        # pretending the section is not there.
        CopyEntry(
            key="submit.window_closed",
            text=(
                "This week's survey has closed, so it can no longer take a submission. The next "
                "one opens on its own schedule and nothing here is missed permanently."
            ),
        ),
        # The one answer a section the student cannot reach gets, and the one
        # answer a section that does not exist gets. They are the same sentence
        # on purpose (SPEC §4.1 item 1): a refusal that distinguished them would
        # answer "does this section exist" for any signed-in student, one request
        # at a time.
        CopyEntry(
            key="submit.section_unavailable",
            text="There is no weekly survey here for you to answer.",
        ),
        # SPEC §3.3's first condition: "All required fields answered." §3.2 makes a
        # comment required when the rating beside it is low, and the rule is read
        # off the question rows rather than written here.
        CopyEntry(
            key="submit.answer_required",
            text="One of the questions still needs an answer before this week can be submitted.",
        ),
        # ADR 0110's two edges. Two sentences and not one, because "40 is the most
        # you can enter" and "half hours only" are two different things to fix.
        CopyEntry(
            key="submit.value_out_of_range",
            text="One of the answers is outside the range its question allows.",
        ),
        CopyEntry(
            key="submit.value_off_step",
            text=(
                "One of the answers falls between two of the steps its question moves in — the "
                "workload slider, for instance, moves in half hours."
            ),
        ),
        # The question the submission named is not one of this set's, or the value
        # it carried is not the shape that question takes. A malformed submission
        # rather than a wrong answer, and the sentence says so without quoting
        # anything the caller sent.
        CopyEntry(
            key="submit.answer_not_recognised",
            text="This submission does not match this week's questions.",
        ),
        # ADR 0115's one refusal: a comment a model has already judged is part of
        # the record for that week, and `classification.answer_id`'s `RESTRICT` is
        # what says so. Revising it is fine; removing it is what this refuses, and
        # the sentence says which of the two is available.
        CopyEntry(
            key="submit.comment_already_judged",
            text=(
                "A comment that has already been checked stays with the week it was written "
                "in. You can change what it says, and it cannot be taken back out."
            ),
        ),
        # SPEC §8's one-response-per-(student, section, week) rule, met by two
        # submissions in flight at once. The student's answers did land — the other
        # request stored them — so the sentence says that rather than reporting a
        # failure.
        CopyEntry(
            key="submit.already_submitted",
            text=(
                "Your answers for this week are already recorded. Reload the page to see what "
                "was stored."
            ),
        ),
    )
}
