# 0123 — The survey screen formats two instants two different ways, and the sentence decides which

**Status:** Accepted — FIX-01 (2026-09-03).

## Context

The student weekly survey screen now renders two absolute instants, and they
arrive on the same read answer.

The first is the open window's `closes_at`, in the mono eyebrow above every
section — "closes Sun 11:59 PM", `frontend/src/components/WeekEyebrow.tsx`. It
has been rendered in the reader's own locale and timezone since E2-10, on the
argument that the instant is absolute and the person reading it is the one who
has to submit before it.

The second is FIX-01 item 4's: the next window's `opens_at`, inside a closed
section's placeholder. The wording is ruled word for word — "When the next
survey for this course opens at 6:00PM EDT on Friday, September 4, it appears
here." — with the zone abbreviation derived from the date rather than written
down anywhere.

SPEC §3.1 puts every window at a wall-clock time "in the institution timezone",
and §8 makes that timezone a deployment-level setting. Neither says how a
browser is to render either instant, and nothing in the spec says the two have
to be rendered the same way. A reasonable engineer would make them consistent —
which is exactly the choice this record is about, because consistency here
points two ways and picking either one for both makes one of the sentences
wrong.

## Decision

The formatter follows the sentence, not the surface. Two formatters, one per
instant, and the difference is deliberate.

**The eyebrow's closing instant stays the reader's**: locale `undefined` and no
`timeZone`, so `Intl` uses the browser's. It is a bare time inside the reader's
own day, and what it answers is "how long have I got".

**The placeholder's opening instant is the institution's**, locale pinned to
`en-US` and `timeZone` taken from the read answer's new `institution_timezone`
member. It is formatted with `formatToParts` rather than `format`, so the
sentence's ruled shape survives — "6:00PM EDT", with no space before the meridiem
— and the zone abbreviation comes out of the format for that date rather than
out of a literal. The two halves fill `{time}` and `{day}` in a governed copy
entry. Any throw or unparseable instant answers null, and the section falls back
to the undated sentence.

## Alternatives rejected

- **Both instants in the institution's zone.** The eyebrow would tell a student
  in another zone when the window closes somewhere they are not, and a deadline
  is the one instant a reader has to convert correctly. It also re-renders a
  sentence E2-10 settled, inside a ticket that was not asked to reopen it.
- **Both instants in the reader's zone.** The ruled sentence names an
  abbreviation, and on a CI box or a travelling laptop that abbreviation would be
  `UTC` — a survey announced at an hour no institution keeps. §3.1 puts the
  window at six o'clock where the institution is, so six o'clock is the fact.
- **Both in the reader's locale.** English governed copy with a date formatted
  to another locale's conventions inside it reads as neither, and the shape the
  ruling fixes ("6:00PM EDT on Friday, September 4") is a locale's output as much
  as it is a sentence.
- **`format()` with a template, instead of `formatToParts`.** `en-US` renders
  "6:00 PM EDT" with a space the ruled shape does not have, and stripping it back
  out with a regular expression is a second, silent formatter.
- **Sending the rendered string from the server.** Python knows the zone and the
  date, so this is buildable; it puts a user-facing sentence outside
  `frontend/src/copy/studentSurvey.ts`, where E2-11's inventory — and therefore
  the §4.1 items 4 and 5 sweeps — cannot read it (ADR 0121).
- **Writing the abbreviation down, or resolving one offset and reusing it.** US
  daylight time ends inside every autumn term. A page saying EDT in November
  tells a student six o'clock for a survey that opens at five.

## Consequences

- A reader in another timezone sees one instant in their zone and one in the
  institution's, on the same screen, with only the abbreviation to tell them
  apart. That is the cost, and it is accepted because each instant answers a
  different question.
- The wire carries `institution_timezone` on every student read, including the
  answer for a session with no enrollments. It is deployment configuration and
  says nothing about the reader, so it adds no person data to a §4.1 surface.
- The pair holds only while both sentences keep their present job. An eyebrow
  that started naming a date, or a placeholder that stopped quoting a
  wall-clock hour, would move the line and this record would need revisiting.
- Nothing but an end-to-end run can see the difference: the abbreviation is
  produced by `Intl` inside the browser against a zone the server sent.
  `tests/e2e/student-survey-heading-and-next-window.spec.ts` reads the same
  section on an October date and a November one for that reason, and the pair
  is the only thing that tells a derived abbreviation from a written one.
- `Intl.DateTimeFormat` throws on an unknown zone, so a mistyped
  `INSTITUTION_TIMEZONE` degrades to the undated sentence rather than to
  "Invalid Date". `app.config`'s validator refuses such a value at startup, so
  the fallback is defence in depth rather than the expected path.
