# 0108 — The leadership limb binds only what the launcher's own grant reaches

## Context

SPEC §7.3 gives a staff launch two limbs: "a launch by an instructor **or any
leadership role** triggers a roster sync". The first is read from the LTI roles
claim; the second, since E1-12, is read from Pulse's own `role_assignment` rows,
because the administrator of a platform writes what its launches claim.

The E1 boundary review found (M9, verified) that the second limb referred to the
launch's context nowhere at all. Any holder of a live leadership assignment
could launch from any context and Pulse would bind that section, store its
roster address permanently, and hand the scheduled sync — which calls with the
tool's own credentials — a class the launcher has no records over. The review's
own actor is a Lead Faculty enrolled as a Learner in a sibling lead's course,
which §2.1 refuses in as many words: "a Lead Faculty's grant is only the courses
they lead (never sibling leads' courses, at any point in the union)". The
binding also takes the `(course, term, lms_section_code)` name under ADR 0091's
first-writer-wins, which nothing repairs until E11.

The fix needs a design answer before it can be written, and the spec does not
supply one. A dean's legitimate first launch into a **brand-new course** has to
keep working — §7.3 makes that launch the thing that discovers a section at all,
"the first staff launch of a section bootstraps every later sync of it" — and a
brand-new course is in nobody's course set by construction. SPEC §2.1's full
purview would answer, but `transitive_purview` raises by design until E9 (ADR
0003), so the condition has to be built from what exists today: assignment rows,
their scope columns, and the containment tree.

## Decision

**The leadership limb binds a context only where the launcher's own grants reach
it, checked at prefix-or-below; the claim limb is exempt.**

Three parts, and each is a separate choice:

1. `app.services.authz.leadership_grant_covers` unions `_own_grant_of` over the
   person's assignments whose role is in `LEADERSHIP_ROLES` — the same statement
   and the same grant rules `resolve_scope` uses, no new SQL — and answers yes if
   the launch's **section**, its **course**, or the **prefix** above that course
   is in the union. It lives in `authz.py` because `public.assignment_scope` is
   read there and nowhere else.
2. **Prefix-or-below** is what keeps the first launch working. A dean's own grant
   lists every prefix under their college, so a dean launching into a course
   Pulse has never seen still binds it; the same prefix test is what refuses a
   dean launching into another college.
3. **The claim limb is not gated.** The LTI roles claim is context-scoped: an
   Instructor URN states what this person is in the course they launched from, so
   it already carries the fact the gate would establish.

A launch that fails the gate records a `launch_defect` row of the new kind
`context_outside_purview` and binds nothing. **It is the binding that is
refused, never the launch**: the person lands exactly as they would have, which
is E1-10's rule that a provisioning refusal never fails the launch, and the
record is the visibility (`docs/MISTAKES.md` entry 26). Nothing about the person
goes in the row — SPEC §10 — so it carries the same four fields every other kind
does: issuer, deployment, context, kind.

## Alternatives rejected

- **Require the discovered course or the bound section to be inside the grant,
  leaving the prefix out.** It passes every refusal case and breaks the one
  launch the design answer exists for: a course nothing has ever seen is in no
  course set, so a dean's first launch into a new course would bind nothing, and
  every new course of every term would stay never-synced until its instructor
  happened to launch.
- **Use SPEC §2.1's full purview.** It is the right answer and it does not exist:
  `transitive_purview` raises by design until E9 (ADR 0003). Faking the walk here
  would put a second, weaker spelling of §2.1's rule in the module that is
  supposed to hold the only one.
- **Trust the launch's roles claim for the leadership limb too** — accept a
  launch whose claim names an administrative or leadership role. E0-09's tenth
  criterion is the reason not to, and it is the reason `holds_leadership` reads
  assignments at all: the platform's administrator writes what its launches say,
  so this would let them hand themselves a section's whole roster of names and
  email addresses.
- **Gate both limbs with one condition.** It is the cheaper code and it passes
  every refusal test. What it costs is §7.3's ordinary case: a real instructor
  Pulse holds no assignment for stops discovering their own section, so most
  sections in the product would never be synced and the console would report
  them as never-synced with nothing saying why.
- **Refuse the launch rather than the binding.** It would turn a data question
  into an outage for the person holding the browser, on a launch that is
  otherwise entirely valid, and E1-10's rule already settles the direction.

## Consequences

- **A person whose only leadership assignment is `ASSISTANT_DEAN` never passes,
  and that is fail-closed until E9.** §2.1 makes them the worked example of a
  purview that comes from the supervision graph — "a set no single containment
  node holds" — so their own grant is empty by construction (ADR 0046). Their
  launch discovers nothing and the section stays unknown until somebody whose
  records reach it launches; the real instructor's next launch does exactly that
  through the claim limb. It costs a late discovery, in the same direction §7.3's
  own cost argument runs, and E9 is where the graph makes it pass.
- **A VP of Academics passes everywhere**, because §2.1 scopes them to the
  institution and the whole tree is beneath it. That is what the spec says they
  hold, and it is correct rather than a gap.
- **The mock world's dean moved college.** He is the launchable subject §7.3's
  leadership limb is demonstrated with, and `mock-lms` launches him into
  `MATH-140-E1FF`, which sits under the College of Arts and Sciences; his
  deanship was scoped to the College of Business and Technology, where nothing
  checked. Under this decision that launch would bind nothing, so
  `scripts/seed.py` scopes him to the college he actually launches into and
  `tests/e2e/exit-dean-both-doors.spec.ts` is what fails if it moves again.
- **`launch_defect_kind` is a closed Postgres enum and grows a label**, which is
  a migration (`d2f6a913c47e`) and an irreversible one: Postgres cannot remove a
  value from a type, so the downgrade leaves it standing, exactly as
  `b8c41f7d2e05` does for the two kinds it added.
- **Two leadership hats compose, as §2.1 says they do.** The predicate unions
  every leadership assignment the person holds, so a chair who also leads courses
  is covered by either, and a person whose second hat is Care or Admin gains
  nothing from it — those roles are outside `LEADERSHIP_ROLES` and hold no rank
  in the supervision chain.
- An already-squatted binding is untouched. Reconciling or ageing one out is
  E11's, per ADR 0091 and the carried file; this decision stops new ones.
