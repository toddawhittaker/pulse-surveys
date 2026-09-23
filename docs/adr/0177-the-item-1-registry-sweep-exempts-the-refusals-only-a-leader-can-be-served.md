# 0177 — The item 1 registry sweep exempts, by key, the refusals only a leader can be served

**Status:** Accepted — E5-13, narrowing a SPEC §4.1 item 1 gate. Settles `docs/disputes/E5-13-01.md`.

## Context

[SPEC §4.1](../SPEC.md) item 1 says students never see comparables, benchmarks,
university averages or other sections, "in charts, text, tooltips, exports, or
aria labels". E2 made a word list the currency that sentence is checked in, and
the registry sweep in
`test_the_shipped_copy_names_nothing_a_student_may_not_see.py` applies that list
to every entry in the backend copy registry.

Sweeping every entry was a faithful reading of the item while every string in the
registry was a string a student could be served. E5-13 ends that. The named-set
API answers eight refusals, and seven of them are answered only behind
`require_leadership` — the 404, the 403, the 409 and the four 422s of
`app.api.leadership` and `app.services.comparison_sets`. Each has to name the thing
it refuses to be any use to the leader reading it, so six of them say "comparison
set" and the sweep reds on those six. The eighth,
`leadership_comparison_sets.not_leadership`, is the sentence
`app.api.deps.require_leadership` answers to any session that is *not* a
leadership session — a student's included.

So the gate and the surface disagreed, and both had something wrong with them:
the sweep read "is in the backend registry" as "is read by a student", and the
one sentence a student really could be served did name a comparison set.

## Decision

**The `not_leadership` sentence is reworded** to "This request does not carry a
leadership session." It is served to students, so item 1 governs it, and the
argument its comment makes — one sentence for the absent, malformed, expired,
foreign and wrong-role session alike — never needed the words it lost.

**The sweep gains an exemption by key**, in the shape
[0158](0158-the-copy-inventory-grows-over-four-surfaces-and-two-of-them-owe-no-confidentiality-line.md)
gave the small-N body: a named tuple of the registry keys answered only behind
`require_leadership`, each with the gate and the route that guards it written
beside it, and the sweep skips exactly those keys. Seven refusals sit behind that
gate; six of them need the exemption, because
`leadership_comparison_sets.member_not_a_course` names the courses and not the
set and so carries none of the swept words in the first place. By key and not by
surface, because the surface has one key a student can be served and that key
stays inside the sweep. The module keeps its controls — a synthetic entry
carrying a forbidden word under a student prefix is still caught, the
`not_leadership` key is asserted present in the registry and absent from the
exempt tuple, and removing an exemption row puts its key back in the count.

## Alternatives rejected and why

**Exempting by surface — skipping the `leadership_comparison_sets.` prefix.** It
is the obvious shape and it is wrong here: one key on that surface is exactly
what a student is answered with, so a prefix-shaped exemption would have carried
the one sentence that needed the gate out through it.

**Rewording all eight.** The other seven are answered to a leader who has just
been refused and has to learn which rule stopped the write. A refusal that will
not name what it refused is a refusal a reader cannot act on, and dodging a word
list that does not govern the sentence is the quiet reword the inventory's own
failure messages forbid.

**An audience field on `CopyEntry`.** The honest shape — each string carrying who
can be served it — but the entry is pinned to exactly two fields, `key` and
`text`, by the copy package's own frozen-entry rule, and widening a frozen
contract to soften a confidentiality gate is the wrong trade in the wrong
direction.

## Consequences

The exemption is a standing obligation on the routes, not only on the test. If a
refusal in the tuple ever becomes reachable by a student — a gate removed, a
route moved out from behind `require_leadership`, a sentence reused on a student
surface — the change that does it has to take that key out of the tuple in the
same change, and the sweep then holds the sentence to item 1 like any other.

The coverage given up is six sentences no student can be served. Everything else
in the registry is swept exactly as before, and the exempt keys are still swept
for item 4's vocabulary with the rest of the inventory.

The tuple is small and its rows carry their own reasons, so what is excused is a
handful of strings a reader of that file can weigh, rather than a hole in the
sweep's vocabulary that nobody can see. A row that excuses nothing is the same
kind of blind spot in miniature, so a key whose sentence the sweep would not
catch anyway does not belong in it.
