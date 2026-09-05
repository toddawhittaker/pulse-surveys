# E3 — items a ticket deferred rather than fixed

Created by E3-06's PR, per the epic README: a PR that defers something adds it
here in the same PR, and E3-08 runs the cleanup pass over this file. Each entry
names the ticket that owns it and what "done" means, so the deferral is a
scheduled decision rather than a hope.

## A lowered participation score is not announced, and nothing explains the credit rule to a student — E8

Settled by E3-06, and settled as a decision rather than left open: **v1 does not
announce an adjustment.** SPEC §3.3 now says so, where it previously said that
whether an adjustment is announced was "a separate and still-open question".

The behaviour that raises the question is correct and stays. A comment accepted
under §3.3's fail-open floor is classified later; a later verdict that refuses it
lowers that week's numerator; and E3-06's weekly sweep posts the lower value into
a gradebook a student may already have looked at. So a student who saw 92% can
see 85% a week later without having done anything, and nothing tells them why.

The reason the answer is "no" for v1 is that there is nothing to announce it
*through*. E3 renders no participation score to anybody: the posted number and
the per-week ledger in its AGS comment are the only visible trace, and the ledger
is the only place §3.4's arithmetic appears at all (ADR 0125). A notification
built now would be the sole student-facing surface in the product for a figure the
product does not otherwise show, and it would have to explain a credit rule
nothing has explained yet.

So the explanation is carried to the surface that will show the score. **Done
when** E8's results view states the credit rule — that a week's items are counted
against the items it offered, and that a comment refused by §3.3 does not complete
its item — and states that a posted score can be adjusted downwards afterwards
when a comment is re-classified. Whether that surface also pushes a notification
is E8's call to make against a real screen; what this entry fixes is that the
explanation is owed and where it is owed from.

Sources: SPEC §3.3 and §3.4, ADR 0125, ADR 0137, and E3-06's ticket, which lists
"Whether a lowered score is announced anywhere" among the decisions it settles.
