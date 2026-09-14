"""The eight sentences the named-set API refuses with — E5-06 (SPEC §5.1).

`app.api.leadership` serves the surface leadership defines comparison sets on,
and it refuses eight ways: a session that is not a leadership session, a set id
nothing defined, somebody else's set on an edit or a delete, and the five rules
the database holds a set to — a name used once, a length out of SPEC §2.2's set,
a level out of SPEC §8's five, a member course at another level, and a member
that is no course at all.

**Each sentence names the rule and nothing else.** A refusal is answered to
anybody who can make a request, so it may describe only itself: no set name, no
course, no person, no count. The five write refusals are translations of what
Postgres refused — the route attempts the write and maps the constraint that
fired — so the sentence has to say which rule was broken without repeating the
value that broke it.

**No length and no level is spelled out here.** SPEC §2.2's eight lengths live in
`app.models.benchmark.CALENDAR_LENGTHS` and §8's five levels in
`app.models.org.CourseLevel`, and a sentence listing either would be a second
copy of a closed set, stale the day one of them moves (`docs/MISTAKES.md` entry
19). This package may not import an application module in any case — see the
package docstring — so the sentences say "one of this institution's course
lengths" and leave the enumeration where it is held.

**`COPY` is published and is deliberately empty, which is this module's one
oddity.** E2-11's inventory governs a key by its *surface* prefix, and leadership
set management is not a governed surface yet: a key published under a
`leadership_sets.` prefix is refused by
`tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`,
because no row in its governance map claims that prefix and an ungoverned prefix
is a body of strings SPEC §4.1 items 4 and 5 are checked over by nothing. E5-13
is the ticket that brings every E5 surface into that inventory — its scope names
"set-management copy" — so the entries and their governance row land together
there. `docs/tickets/e5/deferred.md` carries the gap with its done-when. This is
the position `app.api.instructor`'s two refusals sat in until E4-12, one step
further along: the sentences are in the registry package where the whole
application reads them from one place, and the inventory does not collect them
yet.

The constants are plain strings rather than `CopyEntry` values for the same
reason: an entry exists to be collected by key, and these have no key until the
surface is governed. `app.api.leadership` imports the strings and serves them;
nothing writes a refusal sentence at its raise site.
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
NOT_LEADERSHIP = (
    "Comparison sets are defined by leadership, and this request does not carry a leadership "
    "session."
)

# The 404 for a set id nothing defined — on the read, the preview, the edit and
# the delete alike. It names nothing it was handed: a body that echoed the id
# could not be identical to the body for a different one.
SET_UNAVAILABLE = "There is no comparison set here."

# The 403 for another leader's set on an edit or a delete. Deliberately a
# different sentence from the one above, because the two are different facts and
# a leader may read every set in the institution: telling somebody "this is not
# yours" says nothing they could not already see on the list.
NOT_THE_SETS_DEFINER = (
    "A comparison set is edited and deleted by the leader who defined it, and this one was "
    "defined by somebody else."
)

# The 409 the unique on `comparison_set.name` produces. A name is what a set is
# picked by on every later surface, so two cohorts sharing one cannot be told
# apart by the person choosing between them.
NAME_ALREADY_USED = "Another comparison set already uses this name, and a set is named once."

# The 422 the `length_is_a_calendar_length` check produces. The set is closed and
# has interior gaps, which is why the sentence says "one of" rather than a range.
LENGTH_NOT_A_CALENDAR_LENGTH = (
    "A comparison set runs one of this institution's course lengths, and that is not one of them."
)

# The 422 the `course_level` cast produces for a token that is not one of SPEC
# §8's five — including the right token in the wrong case.
LEVEL_NOT_A_COURSE_LEVEL = (
    "A comparison set is defined at one of this institution's course levels, and that is not one "
    "of them."
)

# The 422 the membership row's `the_levels_agree` check produces. SPEC §5.1 makes
# comparability an exact match on level, so a set holding two levels would
# average what the spec says must never be averaged together.
MEMBER_NOT_AT_THE_SETS_LEVEL = (
    "Every course in a comparison set sits at the level the set declares, and one of these does "
    "not."
)

# The 422 a member key that is no course produces. It names no id, for the same
# reason `SET_UNAVAILABLE` names none.
MEMBER_NOT_A_COURSE = "One of the courses named for this set is not a course this institution runs."

# Empty, and empty on purpose — see this module's docstring. The mapping is
# published rather than omitted because `app.copy.copy_modules()` enumerates the
# package directory and every module in it is read for one, so a module without
# it would be a registry that cannot be collected at all.
COPY: Mapping[str, CopyEntry] = {}
