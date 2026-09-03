# E2-15 — Student-surface headers and copy, and the local gate that spends money

**ID:** E2-15
**Branch:** `e2/student-surface-and-local-gate-repairs`
**Depends on:** E2-13 (the boundary review that found every item here)
**Lane:** heavy
**Security-relevant:** item 1 (a caching header on a path that returns a
student's own free text).

## Context

Three verified findings from the E2 boundary review (the record is
`docs/tickets/e2/boundary-review.md`) that change code rather than records,
none large, none safe to leave: a caching gap on the student read path, a
malformed student-visible sentence nothing pins, and a local gate whose shape
contradicts two README sentences and spends provider money unconditionally.

## Scope

1. **`Cache-Control: no-store` on `GET /student/survey`, and both headers
   pinned.** The GET returns the student's own prior free-text comment
   (`SubmittedAnswer.comment_text`) and sets no caching header (measured:
   200 with no `Cache-Control`), while the POST sets `no-store`
   (`backend/app/api/student.py:216`). The POST's header is itself pinned by
   no test (measured: removing it survives). Add the header to the GET and a
   test asserting both, so neither can silently vanish.
2. **The bounce sentence gets its missing complement, and a pin.**
   `submit.bounce.insufficient` (`backend/app/copy/submit.py:88-95`) ships
   "…a few words on their own are too brief to." — a truncated infinitive on
   the epic's first student-visible surface, and no assertion pins the
   sentence. Repair the sentence and pin the shipped string (or its shape)
   where the copy tests live.
3. **`make ci` stops running the paid eval gate unconditionally.**
   `ci → test-gates → evals` runs `tests.evals.runner --enforce-floors` with
   no condition: red on a fresh clone (no key), roughly a hundred paid
   provider calls on a configured one — while CI itself conditions the live
   steps on AI-touching paths or manual dispatch, and `README.md:697` claims
   the two are the same set of gates ("a green run here should mean a green
   run there") while `README.md:153` claims `make evals` is the only local
   command that spends. Condition the Makefile the way CI is conditioned (or
   split the target out of `ci` with the README saying so) and correct both
   sentences — one decision, recorded, with the two records and the Makefile
   agreeing.

## Acceptance criteria

1. The GET answers with `Cache-Control: no-store`, and removing either
   route's header turns a test red (both directions proven once).
2. The shipped bounce sentence is complete English and a test pins it.
3. `make ci` on a tree with no `AI_PROVIDER_API_KEY` completes green without
   a live provider call, the deliberate spend path is still one command away,
   and the README's two sentences match what the Makefile does.
4. The boundary-review record's disposition lines for these findings are
   updated to point here when this merges.

## Out of scope

- Everything in E2-14.
