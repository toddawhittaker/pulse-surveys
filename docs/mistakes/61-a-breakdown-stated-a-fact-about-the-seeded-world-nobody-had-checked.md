# Entry 61. A breakdown stated a fact about the seeded world that nobody had checked

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** The E9 breakdown (PR #332) wrote, in the README's facts and
in E9-13's ticket, that "the mock IdP already seeds" the assistant dean, so the
exit drive only had to add a launch-side subject. It did seed an
`assistant-dean` persona, but `scripts/seed.py` linked that subject to a
separate mock-world person holding ASSISTANT_DEAN over the College of Business
and Technology, with no supervision edges. The person SPEC §2.1's worked example
is about, the demo assistant dean, was reachable by neither door. E9-13's
builder found it by reading `seed_the_mock_world` before writing the drive
(attempt 1 in `docs/tickets/e9/.attempts/E9-13.md`), and the fix became ADR 0208.

**Root cause.** The sentence was true of a name and false of a person. "Seeds an
assistant dean" was checked against the provider's persona list, where the word
appears, and not against what the persona's subject resolves to in Pulse, which
is the only thing the exit is about.

**Consequence.** Caught before anything shipped. Built as written, the drive
would have signed in as a person whose roll-up is Business and Technology, and
either failed against the worked example's roots or been "fixed" by asserting
the wrong tree, and the epic's exit verdict would have rested on a person the
worked example does not describe.

**Rule.** A ticket's statement about the existing tree or the seeded world is a
claim to check, not a premise to build on: resolve it the way the feature will
(the subject through the door's own function, the row through the reader), and
when it is false, say so in the pull request and the record before building
around it. A breakdown that writes such a statement checks it the same way.
