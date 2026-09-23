# 0175 — The student contract refuses an undeclared member rather than being enumerated

**Status:** Accepted — E5-11.

## Context

[SPEC §4.1](../SPEC.md) item 1 says students never see comparables, benchmarks,
university averages, or other sections, and §5.4 repeats it for the
closing-the-loop view. Until E5 there was nothing of that kind in the system to
leak; E5 builds the comparison sets and serves their figures to instructors, so
the exclusion now has a real class of data to hold against, and E5-11 has to make
it provable rather than conventional.

The student contract is the six models in `backend/app/schemas/student.py`, which
`app.services.survey_read` fills and `GET /student/survey` serves. Before this
ticket they carried no `model_config`, and pydantic's default for an unknown
constructor keyword is to drop it in silence — so a service that grew a benchmark
join could hand `StudentSurveyView(benchmark=...)` to the contract and nothing
would fail. Whether the contract refuses such a member, and how that refusal is
asserted, is a construction question the spec does not answer.

## Decision

Every model in `backend/app/schemas/student.py` carries
`model_config = ConfigDict(extra="forbid")`, and the module docstring says why. A
member the student contract did not declare is refused at construction: it raises
instead of being dropped, so a service that grew such a join fails at the
boundary rather than at the student's screen.

What measures it is the ticket's structural module in the unit suite, which
discovers the models rather than listing them, plants a benchmark-shaped member
on each, and reads the complaints for one naming the planted key. It sits in the
isolated invariant pass that CI may never skip.

## Alternatives rejected and why

**An enumeration of the declared member names.** A test that lists the members
each student model may declare and fails when that set changes. It costs nothing
to write and it catches the same first mutation — but it is passed the day
somebody adds the member *and* adds it to the enumeration, which is the same
edit, in the same file, by the same person, and a reviewer reads the two halves
as agreeing with each other. It asserts a convention about a list, not a property
of the type. `docs/MISTAKES.md` entry 2 is the standing answer: assert the
forbidden state. A narrow declared-member sweep is kept as one control among
several, but it is not the mechanism.

**Leaving the refusal to the route and its sweep.** The route sweep this ticket
also ships walks every student-visible response for a benchmark-shaped key at any
depth, which catches a member that is filled. It does not catch a member that
exists and is empty, and an empty member is one route bug away from filled. §4.1
item 1 is about what a student can be shown, so the type is where the answer
belongs.

**`extra="ignore"` with a logged warning.** It keeps the silent drop and adds
noise nobody reads. Failing loudly and early is this repository's default, and a
confidentiality boundary is the last place to make an exception to it.

## Consequences

- Any caller handing a student model a keyword it does not declare now raises.
  Nothing does today: every call site in `app/services/survey_read.py` and
  `app/api/student.py` passes declared members by name, and none of them splats a
  mapping. A future caller wanting to pass something new has to declare it, which
  is the point — a benchmark member cannot arrive by accident.
- A misspelled keyword at a call site becomes an error rather than a silently
  missing value, which is a second gain nobody asked for.
- The refusal is pydantic's own, and its message is a validation error rather
  than one of `app.copy`'s sentences. That is right here: no student ever reads
  it, because it fires on the server's own construction of its own answer.
- `backend/app/schemas/survey.py` already forbids extra members on the submission
  request, so the student wire is now closed in both directions by the same
  mechanism.
