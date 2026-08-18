# Entry 30. A fixture supplied the value under test, so neither the green nor the red meant anything

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** `scripts/seed.py` refuses to run unless `ENVIRONMENT` is
`development`, reading it after `.env` has filled in whatever the process
environment does not set. A test case named `not-set-at-all` removed the variable
from the child process and expected a refusal; it got a run, because `.env`
supplied the name.

Both sides then reached for the suite, and the suite could not answer.

- **The proposed fix turned everything green and proved nothing.** Reading the
  variable before `.env` made all 29 tests in the module pass. It also made
  `make seed` refuse on a correct stock checkout — measured — and *no test could
  see that*, because `seed_environment` in `tests/conftest.py` lays every
  documented `.env.example` entry into the child environment. The fixture supplies
  `ENVIRONMENT` to every run the suite makes, so the one path the change altered
  is the one path the suite never exercises. Its whole design is to over-supply,
  and that design is right for what it was built for.
- **The failing case proved nothing either.** Its verdict is decided by whether
  an untracked `.env` exists in the working tree: absent, it passes; present, it
  fails. So it measures the machine rather than the script — and since CI's unit
  and integration job never creates `.env` while every developer does, it was
  **green in the gate and red on every workstation**, reporting a guarantee from
  the one environment in which nobody runs the script.

**Root cause.** The subject of the test was not a behaviour but a *resolution* —
which of two sources supplies a value — and the fixture is one of the sources. A
suite cannot measure a change to a value it is itself providing.

**Consequence.** A dispute file, an arbitration, a spec-silence finding, and a
decision that had to go to a human, over a question two lines of code answer. The
seed's configuration reading was restructured afterwards so the question could be
asked directly (`resolved_configuration(environ, dotenv_path)` returns a mapping
instead of mutating `os.environ`), which is the repair, and it arrived after the
argument rather than before it.

**Rule.** **Before treating a suite result as evidence about how a value is
resolved, find out what the fixture supplies.** If the fixture provides the value
under test, both colours are uninformative and the honest instrument is a hand
measurement of the real path, recorded where somebody can re-run it.

Two cheap checks, either of which would have caught this before the argument
started:

- Grep the fixture for the variable the test is about. If it is set there, the
  test is asking the fixture, not the code.
- Ask what the case would do on a machine configured differently — a missing
  untracked file, a different working directory. **A test whose verdict depends
  on something not in the repository is measuring the machine**, and one that
  therefore disagrees between CI and a developer is worse than one that simply
  fails, because each side believes the other is misconfigured.

And the design rule that follows: **a guard worth testing should take what it
reads as an argument.** A guard that reaches for `os.environ` or opens a file by a
hardcoded path can only be interrogated by building a whole environment around it,
which is how a one-line question turns into a subprocess, a fixture and a dispute.

---
