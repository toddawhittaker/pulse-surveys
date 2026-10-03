"""The eight sentences the named-set API refuses with — E5-06 (SPEC §5.1).

`app.api.leadership` serves the surface leadership defines comparison sets on,
and it refuses eight ways: a session that is not a leadership session, a set id
nothing defined, somebody else's set on an edit or a delete, and the five rules
the database holds a set to — a name used once, a length of at least one week,
a level out of SPEC §8's five, a member course at another level, and a member
that is no course at all.

**Each sentence names the rule and nothing else.** A refusal is answered to
anybody who can make a request, so it may describe only itself: no set name, no
course, no person, no count. The five write refusals are translations of what
Postgres refused — the route attempts the write and maps the constraint that
fired — so the sentence has to say which rule was broken without repeating the
value that broke it.

**No level is spelled out here.** §8's five levels live in
`app.models.org.CourseLevel`, and a sentence listing them would be a second copy
of a closed set, stale the day one of them moves (`docs/MISTAKES.md` entry 19).
This package may not import an application module in any case — see the package
docstring — so the sentence says "one of this institution's course levels" and
leaves the enumeration where it is held. A length is no longer a closed set at
all: since E5-14 the table holds a set's length to at least one week, and the
sentence says exactly that.

**All eight are registry entries on the comparison-set surface, and `COPY` is
filled from them — E5-13, ADR 0176.** They are published under the
`leadership_comparison_sets.` prefix, which is the same prefix
`frontend/src/copy/leadershipComparisonSetCopy.ts` publishes the screen's own
words under: one surface read by one person, from two sources. That is exactly
the relationship `app.copy.instructor_report`'s two refusals have to the
report's four frontend prefixes (ADR 0158), and item 5 counts the screen a
person reads rather than the file a string came out of. A prefix of this
module's own would have been a second surface for half of one screen, and until
this ticket the eight were plain strings with an empty `COPY`, which put them
where `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
could not read a word of them: SPEC §4.1 item 4's vocabulary was swept over the
screen and not over what the API answers it with.

**Each entry has a public constant beside it holding its text, and that is what
the application imports.** The entry is where the words are written; the
constant is the entry's own `text`, so the two cannot drift and there is one
sentence per refusal in this repository. The constants keep the names they have
always had because every route, service and test that serves or pins a refusal
reaches it by name, and a refusal is served as a `detail` string rather than as
an entry. `app.api.instructor` does the same join at its end instead, which is
the only difference between the two surfaces' shapes.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "COPY",
    "LENGTH_NOT_A_CALENDAR_LENGTH",
    "LEVEL_NOT_A_COURSE_LEVEL",
    "MEMBER_NOT_AT_THE_SETS_LEVEL",
    "MEMBER_NOT_A_COURSE",
    "NAME_ALREADY_USED",
    "NOT_LEADERSHIP",
    "NOT_THE_SETS_DEFINER",
    "SET_UNAVAILABLE",
]

# The 401 every route answers a session that is not a leadership session — none
# at all, a student's, an instructor's, and the instructor session of somebody
# who also holds a leadership assignment. One sentence for all of them, because
# the difference between "not signed in" and "signed in as somebody else" is a
# fact about who holds the token.
#
# It is the one refusal here a student can be served, so it names no comparison
# set: SPEC §4.1 item 1 forbids that vocabulary in anything a student reads, and
# the sentence does its job without it (ADR 0177).
_NOT_LEADERSHIP = CopyEntry(
    key="leadership_comparison_sets.not_leadership",
    text="This request does not carry a leadership session.",
)

# The 404 for a set id nothing defined — on the read, the preview, the edit and
# the delete alike. It names nothing it was handed: a body that echoed the id
# could not be identical to the body for a different one.
_SET_UNAVAILABLE = CopyEntry(
    key="leadership_comparison_sets.set_unavailable",
    text="There is no comparison set here.",
)

# The 403 for another leader's set on an edit or a delete. Deliberately a
# different sentence from the one above, because the two are different facts and
# a leader may read every set in the institution: telling somebody "this is not
# yours" says nothing they could not already see on the list.
_NOT_THE_SETS_DEFINER = CopyEntry(
    key="leadership_comparison_sets.not_the_sets_definer",
    text=(
        "A comparison set is edited and deleted by the leader who defined it, and this one was "
        "defined by somebody else."
    ),
)

# The 409 the unique on `comparison_set.name` produces. A name is what a set is
# picked by on every later surface, so two cohorts sharing one cannot be told
# apart by the person choosing between them.
_NAME_ALREADY_USED = CopyEntry(
    key="leadership_comparison_sets.name_already_used",
    text="Another comparison set already uses this name, and a set is named once.",
)

# The 422 the `length_weeks_is_at_least_one` check produces — a length of zero
# weeks or fewer. The key keeps its E5-06 name, which every reader of the
# registry and the frontend reaches it by; only the rule, and so the sentence,
# changed when the owner ruled at E5-14 that a set's length is data rather than
# one of SPEC §2.2's eight.
_LENGTH_NOT_A_CALENDAR_LENGTH = CopyEntry(
    key="leadership_comparison_sets.length_not_a_calendar_length",
    text="A comparison set's length is at least one week.",
)

# The 422 the `course_level` cast produces for a token that is not one of SPEC
# §8's five — including the right token in the wrong case.
_LEVEL_NOT_A_COURSE_LEVEL = CopyEntry(
    key="leadership_comparison_sets.level_not_a_course_level",
    text=(
        "A comparison set is defined at one of this institution's course levels, and that is not "
        "one of them."
    ),
)

# The 422 the membership row's `the_levels_agree` check produces. SPEC §5.1 makes
# comparability an exact match on level, so a set holding two levels would
# average what the spec says must never be averaged together.
_MEMBER_NOT_AT_THE_SETS_LEVEL = CopyEntry(
    key="leadership_comparison_sets.member_not_at_the_sets_level",
    text=(
        "Every course in a comparison set sits at the level the set declares, and one of these "
        "does not."
    ),
)

# The 422 a member key that is no course produces. It names no id, for the same
# reason `SET_UNAVAILABLE` names none.
_MEMBER_NOT_A_COURSE = CopyEntry(
    key="leadership_comparison_sets.member_not_a_course",
    text="One of the courses named for this set is not a course this institution runs.",
)

# What the application serves. Each is its entry's own text, so a reworded
# refusal is one edit above and nothing here can fall out of step with the
# inventory.
NOT_LEADERSHIP = _NOT_LEADERSHIP.text
SET_UNAVAILABLE = _SET_UNAVAILABLE.text
NOT_THE_SETS_DEFINER = _NOT_THE_SETS_DEFINER.text
NAME_ALREADY_USED = _NAME_ALREADY_USED.text
LENGTH_NOT_A_CALENDAR_LENGTH = _LENGTH_NOT_A_CALENDAR_LENGTH.text
LEVEL_NOT_A_COURSE_LEVEL = _LEVEL_NOT_A_COURSE_LEVEL.text
MEMBER_NOT_AT_THE_SETS_LEVEL = _MEMBER_NOT_AT_THE_SETS_LEVEL.text
MEMBER_NOT_A_COURSE = _MEMBER_NOT_A_COURSE.text

# What the inventory reads, keyed the way every copy module in this package is.
COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        _NOT_LEADERSHIP,
        _SET_UNAVAILABLE,
        _NOT_THE_SETS_DEFINER,
        _NAME_ALREADY_USED,
        _LENGTH_NOT_A_CALENDAR_LENGTH,
        _LEVEL_NOT_A_COURSE_LEVEL,
        _MEMBER_NOT_AT_THE_SETS_LEVEL,
        _MEMBER_NOT_A_COURSE,
    )
}
