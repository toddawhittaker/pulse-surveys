# Carried into E7 — requirements parked before its breakdown

Each entry states what is owed, why it lands here, and what was verified at
parking time. E7's breakdown is written from this file plus whatever its
predecessors' carried files hand it.

## The professor's name reaches the student, through a sanctioned channel

**Ruled 2026-09-03** at the owner's review of the merged E2 survey page: the
page should show the section's professor somewhere (the heading area is the
natural spot). Parked here because E7 is the first epic whose own scope
requires an instructor's name on a student surface — §14.3 E7's
"non-anonymous posting" and respond-on-behalf "with honest attribution"
cannot be built without the same channel — and building the channel earlier
would open an identity widening for a cosmetic want alone.

**Verified at parking time (2026-09-03, seeded database):**

- The data exists: every seeded section carries exactly one `INSTRUCTOR`
  `role_assignment`, and each instructor's `person.identity_name` is
  populated (category Staff) via the roster sync.
- The serving role cannot read it, by design: `pulse_app` holds no grant on
  `person` or `user_identity`; names are reachable only by the migration
  owner and the three definer channels (Care reveal, roster writer, id
  resolver — the resolver sees no names).

**The shape to build (contestable — the ticket owes an ADR):** a fourth
narrow SECURITY DEFINER channel in the house pattern — "the instructor
display name for this section", nothing else — with §4.1-style tests in both
directions: a student gets their own section's instructor's name; any other
section answers nothing; no refusal body carries it. A plain column grant is
the wrong shape (`person` holds students too, and a grant cannot filter
rows).

**Done when** the survey page's heading area and E7's response attribution
both render the instructor's name through that one channel, the channel has
its ADR and its two-direction §4.1 pins, and E8's student results view can
consume it without a second mechanism.
