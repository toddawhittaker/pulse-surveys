# 0144 — The reveal derives its subject from the record Care is acting on

## Context

`docs/tickets/e1/carried-from-e0.md` records a finding as three facts that are
individually correct and jointly are not. `ActorScope` carries `holds_care`
beside the purview, so Care can never be unioned into a reporting scope.
`public.section_roster` hands instructor-scoped code the `user_id` of every
enrolled student, which is that view's whole point — the key is what makes a
de-identified response addressable at all. And
`safety.reveal_identity(actor_person_id=…, subject_user_id=…)` checked only that
the *actor* held a live `CARE` assignment, asking nothing about where the subject
came from.

SPEC §2.1 permits one person to hold a Care assignment and a teaching assignment
at once, and §6.2 spends a paragraph on her. So that person could take a
`user_id` off her own roster, pass it to the reveal, and be handed the student's
name and address — and §4's audit row would be indistinguishable from a
legitimate access, because it records an actor, a timestamp and a subject and
nothing about what the reveal was *for*.

E0 had no surface that renders roster-derived rows to an instructor. E4 builds
the first one, which is why the carried entry names this epic and why E4-11 waits
on this ticket.

One fact constrains the shape. The carried entry's "done when" asks that the
reveal take its subject "from a Care case rather than from any caller-supplied
id, or an equivalent guard", and **there is no case model until E10** — `case_id`
is nullable for exactly that reason. The guard cannot lean on a table that does
not exist, so it has to derive the subject from something that already
legitimately connects Care to a student.

## Decision

**`reveal_identity` names a comment, and the student is derived from it inside
the Care session.** The signature is
`reveal_identity(*, actor_person_id: UUID, answer_id: UUID, case_id: UUID | None
= None)`, and `subject_user_id` is **deleted rather than deprecated**: there is
no parameter a caller can put a roster key into, so the composition above has no
call to make. The derivation is `answer.response_id` to `response.user_id` — a
comment's author — which is exactly the record §6.2's queue acts on.

**The derivation runs through a third `SECURITY DEFINER` function**,
`public.reveal_subject_for_answer(answer_id uuid) RETURNS uuid`, owned by
`pulse_reveal_definer` and executable by `pulse_care` alone. It answers a
`public.user` row id, or NULL where the id names no comment.
`backend/app/services/safety.py` turns that NULL into
`UnknownRevealSubjectError`, a **sibling** of `NotCareStaffError` and not a
subclass, so E10's queue can tell "you may not use this door" from "that is not a
record you can act on" by type rather than by reading a message.

**The order of checks is E0-10's, with one step inserted.** The actor's
assignment is checked first and unchanged; then the subject is derived; then
E0-26 item 1's record, commit and read, untouched. Both edges of that placement
are load-bearing. Below the actor check, because a derivation that ran first
would answer a non-Care caller differently depending on whether the id names a
real comment — an existence oracle over comment identifiers, handed to exactly
the reporting-scoped caller this guard keeps away from the queue. Above the
record, because §4's log is a record of *accesses*: **a refused derivation writes
no audit row**, since a call that reached no student is not an access, and §6.2's
monthly review outside the Care office would otherwise read a fabricated pattern
of one.

**The owner's two new reads are column-scoped**: `SELECT (id, response_id)` on
`public.answer` and `SELECT (id, user_id)` on `public.response` — the four
columns the body reads and no more.

**Three things this deliberately does not do**, each of which a reasonable reader
will look for:

- **It does not require the comment to be classified as a threat or self-harm.**
  E4-01's ticket recommends that predicate, and it waits for E6. `app.models.ai`'s
  `ClassificationTask` has exactly one member today, `COMMENT_VALIDITY`, and that
  enum's own rule is that a member lands with the code that writes it — E4-01
  writes no classifier. A predicate written now would either refuse every comment
  in the system or invent a verdict vocabulary for E6 to inherit. It is a
  narrowing of the function's body when E6 lands, not a change to any signature.
- **It does not touch `public.record_identity_reveal`'s contract.** That function
  still takes an actor, a subject and a case, and still checks the actor itself.
  Narrowing it belongs to E10 with the case model, because what it should take
  *instead* of a subject is a case id, and there are no cases yet.
- **It does not add the E0-26 sweep rule** — that only the Care queue imports the
  reveal. That stays E10's, where there is a queue to be the one importer.

## Alternatives rejected

**Keep `subject_user_id` and validate it against a record.** The shape the
carried entry warns about by name: the bare key stays in the signature, every
caller still supplies one, and the guard is a condition somebody can weaken,
invert or route around in a later ticket. Deleting the parameter moves the
guarantee from a check into the type system — the old call is unwritable, which
is what `tests/unit/test_no_caller_names_a_student_to_the_reveal.py` sweeps the
whole of `backend/` for.

**Grant `pulse_care` a read of `answer` and `response`, at table or column
grain, and derive the subject in Python.** Simpler, one fewer object, no
migration to the door. Rejected because `pulse_care` today holds `SELECT` on
exactly one base table — `public.role_assignment` — and on no view at all, and
that zero is the architecture rather than an accident: ADR 0001 gives the Care
role one `SECURITY DEFINER` door and no read path, and every refusal in
`tests/integration/test_identity_grants.py` is written against it. A grant would
hand that connection a standing walk from any comment id to any student key that
works **outside** the door, with no record written and nothing in the service in
the way — which is a smaller version of the capability this ticket exists to
remove. A definer keeps the Care connection's own read surface at zero, and it is
the mechanism ADR 0094 established and ADR 0139 used most recently.

**Give the new function an owner of its own.** Rejected on ADR 0139's ground and
on a sharper one. A fifth NOLOGIN role holding a subset of an existing owner's
grants is a role to audit rather than a boundary; and every rule in the grants
suite about "what the definer may reach" measures **one** privilege set, so two
owners of one door would be two surfaces of which only one is ever read.

**Table-level `SELECT` on `answer` and `response` for the owner.** It works, and
it is the grain `has_table_privilege` can see, so it is the grain a pinned
equality can hold. Rejected for the narrower one because table grain hands the
Care door's owner every comment's text: §6.2 gives Care the comment content
through the queue E10 builds, not through the function that turns a comment id
into a key, and the narrowest privilege that does the job is the standing test
for a legitimate grant here. The price is stated below.

**A `pg_temp`-free or `plpgsql` body.** Not contestable, and named only so the
next reader does not re-derive it: ADR 0027 measured the `search_path` variants,
and a `LANGUAGE sql` body is what makes "no dynamic statement" structural rather
than a rule.

## Consequences

- **The Care door is three functions**, and E0-10's rule behind the number — "every
  additional door is a way to obtain a name without leaving a record" — is not
  violated, because this one cannot obtain a name. It returns a `user` row id or
  NULL, reads no column of `public.user_identity` or `public.person`, and has no
  path that answers a name. `tests/integration/test_identity_grants.py` holds the
  door's three names as an equality, so a fourth is a failure rather than a
  widening nobody sees.
- **The owner's privilege equality is no longer exact.** A column-scoped grant
  lives in `pg_attribute.attacl`, where `has_table_privilege` cannot see it, so
  the two derivation reads are *permitted* by that test rather than *required*.
  What the equality still buys is intact — a seventh relation, or any verb but
  `SELECT` on those two, still fails — but a door that never received the grant
  fails behaviourally rather than there. That is the cost of the narrower grain,
  and it is the reason the behavioural tests drive the real `pulse_care`
  connection.
- **E10's case model wraps this without another signature change.** `case_id` is
  already a parameter and already nullable; when a case exists, the queue passes
  one, and a later narrowing derives the subject from the case rather than from
  the comment behind the same call. Nothing E4 builds has to be revisited to get
  there.
- **A caller can still name any comment in the system.** This guard says the
  subject must be somebody who wrote a comment, not that the comment is one Care
  has business with — that is the E6 predicate above, and until it lands a Care
  officer with a comment id can reveal its author. What the guard removes is the
  reporting-scope route: a `user_id` is not an `answer_id`, and the ids a
  roster hands out match no comment.
- **A downgrade past this revision is a downgrade past the application.**
  `app.services.safety` names the function, so a database walked back to
  `c4a8e51db9f3` has E0-26's two-function door and a service that cannot complete
  a reveal against it.
