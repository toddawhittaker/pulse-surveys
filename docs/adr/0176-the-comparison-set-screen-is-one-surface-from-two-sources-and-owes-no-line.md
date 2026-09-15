# 0176 — The comparison-set screen is one surface from two sources and owes no confidentiality line

**Status:** Accepted — E5-13, extending [0158](0158-the-copy-inventory-grows-over-four-surfaces-and-two-of-them-owe-no-confidentiality-line.md).

## Context

[SPEC §4.1](../SPEC.md) items 4 and 5 are asserted over the copy inventory, and
both footnotes say the inventory grows with each UI epic. ADR 0158 grew it over
E4's report and settled the two questions that growth raises: what counts as one
surface, and what a surface that carries no confidentiality line has to record.

E5 ships a screen the earlier answers do not obviously cover. Leadership defines
comparison sets on it, and its words arrive from two places: the screen's own
copy module, `frontend/src/copy/leadershipComparisonSetCopy.ts`, which E5-09
shipped with 44 keys under the `leadership_comparison_sets.` prefix; and eight
refusal sentences the named-set API answers with, which E5-06 put in
`backend/app/copy/leadership_sets.py` as plain strings with an empty `COPY`
because no governance row claimed a prefix for them yet.

So two things were open. Whether those eight are a surface of their own or the
same surface as the screen. And whether the screen carries item 5's standing
confidentiality line, which nothing had answered: the brief gives it none, and
item 5's parenthetical names only the survey.

## Decision

**The screen and the API's refusals are one surface, published under one
prefix.** The eight sentences are now `CopyEntry` values under
`leadership_comparison_sets.`, the prefix the screen's own module already
publishes under, and `COPY` is filled from them. This is exactly the shape 0158
gave the report, whose `instructor_report.` refusals sit on the `report` surface
beside four frontend prefixes: item 5 counts the screen a person reads, not the
file a string came out of. The texts are unchanged, and each public constant in
the copy module is now its own entry's `text`, so the routes and the service go
on importing a sentence by name while the words are written in one place.

**The surface owes item 5 no confidentiality line**, and the answer is recorded
in `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` with its reason, as 0158 requires of
any surface that carries none. A set is a name, a length, a level and the courses
in it; the preview is two counts; the eight refusals say who may act and what is
not there to act on. Nothing on the screen is anybody's response, so item 5's
sentence would have no subject, and a promise made where nothing keeps it is
worse than no promise. All eight are swept for item 4's vocabulary with
everything else.

## Alternatives rejected and why

**A `leadership_sets.` prefix of its own, governed as a second surface.** It
would have been a second item-5 verdict over half of one screen, and it makes
"how many surfaces does this product have" a question about which side of the
wire a sentence is written on. The report settled that question the other way a
month earlier.

**A standing confidentiality line on the screen.** Item 5's line is a promise
about what happens to a person's response. There are no responses here, so the
line would either say something the screen cannot keep or repeat the product's
promise in a second place the exactly-once rule cannot see — which is the state
0158's two maps exist to make impossible.

**Leaving the eight refusals ungoverned.** That was the shipped state, recorded
in `docs/tickets/e5/deferred.md`, and it means SPEC §4.1 item 4's vocabulary
sweep reads the screen's words and not a word of what the API answers the same
reader with. An ungoverned prefix is a body of user-facing text nothing checks.

## Consequences

The comparison-set surface is the fifth governed surface and the third that owes
item 5 no line, so 0158's counts in its title and in the inventory's records are
out of date and were corrected in this ticket rather than left to be read as
current.

The surface is the first that can lose half its strings without any other rule
in the inventory changing colour: either source alone keeps the prefix collecting
and keeps the zero looking like an answer. So the inventory asserts both halves
in their own currency before it believes the zero
(`test_the_comparison_set_surface_owes_no_line_and_collects_from_both_its_sources`).

The eight sentences name the thing they refuse, so they carry the words
"comparison set" into the backend registry for the first time, and the
registry-wide SPEC §4.1 item 1 sweep forbids that phrase in any entry. That
collision was disputed (`docs/disputes/E5-13-01.md`) and is settled in
[0177](0177-the-item-1-registry-sweep-exempts-the-refusals-only-a-leader-can-be-served.md):
seven of the eight are answered only behind `require_leadership` and are exempted
from the sweep by key, and the eighth — the sentence that gate answers a session
that is not a leadership session, a student's included — was reworded to name no
comparison set. So the entry count on this surface is unchanged; one of its texts
is not the text this record was written against.
