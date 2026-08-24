# E0-23 — A spec question for E1: what triggers the first roster pull

**ID:** E0-23
**Branch:** `e0/spec-question-first-roster-pull`
**Depends on:** none

## Status — what is left here

**Answered 2026-08-18, and the spec edit has landed. This ticket is closed.**
PR #20 created this file and deliberately answered nothing; SPEC §7.3 now
carries the answer under *What triggers the first pull*, and §2.1's LMS-owned
bullet points at it.

**Any instructor or leadership launch triggers a roster pull, and the roster
service address is stored from that launch. A student launch does not.** Every
later scheduled sync works from the stored address, which is what gives the
scheduled job the discovery it otherwise lacks. An operator sees "no roster
yet" on a section that has never had one.

That answer is chosen against the failure state this ticket names: a section
whose first launch is a student on a platform that withheld the address, where
Pulse knows the section exists and cannot ask who is in it — no roster, no
survey windows, no participation denominator, and nothing errors. Restricting
the trigger to staff launches does not make that state impossible, because a
platform can withhold the claim from a staff launch too; it makes it rare and
it keeps student traffic from causing outbound calls.

**What is left is E1's**, and it is code rather than a decision: the column that
stores the service address, its migration, and its tests, built with the sync
that reads it. §7.3 also commits to a never-synced state being visible in the
admin console, distinct from a section with no enrollments — that is E1's too.


## Context

This came out of confirming where section data comes from before starting
[E0-06](E0-06-term-calendar-schema.md). It is not an E0 question — nothing in
this epic pulls a roster, and the mock platform side ([E0-15](E0-15-mock-lms-nrps-ags.md))
serves rosters without deciding who may ask for one. It is recorded here for the
same reason as [E0-22](E0-22-spec-questions-from-e0-05.md): so that "open" means
written down with the exposure stated, rather than noticed once in conversation.

The answer is a spec edit. It is cheap to make now and expensive to discover
halfway through building E1's sync.

Read first: SPEC §7.3 (the two sentences on roster sync and the per-platform
adapter), §2.1 under "Data sources — who owns what", §3.4 (what the enrollment
window is used for), and §6.1 and §6.3 for where an operator would see that a
section has no roster.

## Scope

### The exposure

Two sentences in the spec describe how roster data arrives. SPEC §7.3 says the
Names and Role Provisioning Service is "pulled on schedule and on launch
(debounced)". SPEC §2.1 lists the LMS-owned tables as arriving by "hourly roster
sync + launch-time ingestion". Neither says **which** launches trigger a pull,
and neither says how the scheduled job reaches a course it has never seen.

Three mechanics turn that silence into a real decision:

1. **The launching person's role does not authorize the pull.** Pulse calls the
   roster service as itself, with credentials belonging to its own platform
   registration, not with anything derived from the person who clicked. There is
   therefore no protocol reason to require an instructor launch, and a student
   launch triggering a pull is no more privileged than the scheduled job doing it
   overnight. Nothing about the result reaches the student.

2. **The address arrives in the launch.** The URL Pulse has to call is carried as
   a claim inside the launch token. Platforms vary in whether they include that
   claim on a student launch — the standard does not tie it to role, but
   implementations differ, which is exactly the class of variation SPEC §7.3
   confines to the per-platform adapter.

3. **The scheduled job can only sync a course it can address.** It has no
   discovery mechanism of its own; it needs a service URL that some earlier
   launch supplied. So the first launch of a section is the bootstrap for every
   later sync of it, and a section nobody has ever launched from is invisible to
   the schedule.

Together those produce a state the system can sit in: a section whose first-ever
launch is a student, on a platform that withheld the claim. Pulse knows the
section exists, because the launch context told it so, but has no way to ask who
is enrolled. No roster means no enrollments, which means no survey windows and no
participation denominator under §3.4, until somebody whose launch does carry the
claim opens the tool. Nothing errors. The section is simply quiet.

### What to decide

1. **Which launches trigger a roster pull.** The likely answer is that role is the
   wrong test and the presence of a stored service URL is the right one: take the
   URL from whichever launch first supplies it, keep it against the section, and
   let any launch or the schedule trigger a pull from there. If the answer is
   instead that only a teaching-role launch may trigger one, the spec should say
   so and say why, because it is not the protocol that requires it.

2. **Whether the service URL is stored, and where.** This is the difference
   between the schedule working from data it owns and the schedule depending on a
   launch having happened recently. It also decides whether E1 needs a column for
   it, which makes it a schema question as well as a behavioural one.

3. **What a section with no reachable roster looks like to an operator.** This is
   the half with a visible consequence. SPEC §6.3's catalog viewer already shows
   last-sync time per course, which is the natural place for "never", and §6.1 is
   where a count of such sections would belong if one is wanted. The alternative
   — a section that is silently surveyed by nobody — is indistinguishable from a
   section where nobody happened to respond.

### What this is not

There is no confidentiality question here. A roster read brings names and email
addresses into Pulse under the identity separation E0-08 and
[E0-10](E0-10-identity-separated-views.md) build, and which launch triggered the
read does not change what any reader can later see. Worth stating once so the
next person does not re-derive it.

## Out of scope

- The sync implementation, the debounce interval, and the hourly schedule. All
  E1.
- Paging over a multi-page roster. That is the mock platform's side and is
  [E0-15](E0-15-mock-lms-nrps-ags.md)'s acceptance criterion already.
- Anything about what the tool does with enrollments once it has them.

## Acceptance criteria

All four are done as of 2026-08-18. This ticket is closed; what follows from it
is E1's.

- [x] SPEC §7.3 says which launches trigger a roster pull — an instructor or any
      leadership launch, never a student one — and says the trigger is the
      launcher's role while the *request* is made with the tool's own
      credentials, so the two are not confused.
- [x] SPEC says how the scheduled sync addresses a course it did not just receive
      a launch from: the service address is **stored** from the launch that
      triggered the first pull, which is the discovery the scheduled job lacks.
- [x] SPEC says what an operator sees when a section has never had a roster —
      never-synced in the admin console (§6.1, §6.3), stated as distinct from a
      section with no enrollments, because only one of the two is a fault.
- [x] Nothing in the answer is per-platform. What *is* per-platform — whether a
      given platform sends the address on a staff launch at all — is handled by
      §7.3 naming the never-synced state rather than by a rule in domain logic.

## Definition of done

**Docs apply.** The whole ticket is a spec edit.

**Tests apply in E1, not here.** If the answer adds a column for the service URL,
that column and its migration are E1's, built with the sync that reads it.

**AI evals do not apply. Accessibility does not apply.**

**Security review does not meaningfully apply** — no code changes, and the one
question that sounds like a security question is answered under "What this is
not" above.
