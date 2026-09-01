# Entry 18. A deliverable existed in the source tree and not in the built artifact

**Caught: 2**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


*2 instances recorded; newest first.*

*(**A catch**, building E2-07's image, 2026-09-01. `.dockerignore` excluded
everything the backend image does not need, which silently excluded the whole
new `mock-ai/` directory from the build context: the Dockerfile would have
COPYed from an empty context and no test in the suite reads an image's
contents. Acting on this entry — the deliverable must exist in the ARTIFACT,
not the tree — the image was built for real before green was reported, the
miss surfaced as a build failure, and `.dockerignore` gained the `!mock-ai`
re-include in the same commit.)*

**What happened.** E0-12 shipped `backend/app/ai/prompts/validity.v1.md`, the
prompt SPEC §7.4 requires a classification to name. Every gate was green: the
unit tests read the file off disk, ruff and mypy had nothing to say about a
`.md`, and it was committed and visible in the diff. Building the wheel the
Dockerfile installs — `pip wheel . --no-deps --no-build-isolation` — produced
`app/ai/__init__.py` and `app/ai/contracts.py` and no `prompts/` at all.
setuptools includes Python modules in a wheel; a data file inside a package
needs `[tool.setuptools.package-data]` and had none.

**Root cause.** Two different ideas of where the code lives. Every test in this
repository runs against the source tree, where the file is simply there. The
container installs a wheel into `/opt/venv` and has no source tree, so
"the file is in the repository" and "the file is in the running system" are
separate facts, and nothing connected them.

**Consequence.** As caught, none — the packaging entry went in with the ticket.
Unrecognised, E0-13's gateway would have loaded the prompt on a developer's
machine and raised on the first real launch in a container, with a green CI run
and a passing Compose health check behind it, because the health check answers
before any AI task is called. The same trap is waiting for four later epics: E2,
E4, E6 and E7 each add a prompt file here, and each will pass every gate.

**Rule.** When a ticket ships a non-Python file that code will read at runtime,
build the artifact and look inside it — `pip wheel . --no-deps
--no-build-isolation` then `unzip -l`. A green test suite proves the file is in
the repository and says nothing about whether it is in the image. This is entry
9 in a new place: the guard is the packaging configuration, and reading it is
not executing it.

For this directory the check is no longer manual:
`tests/unit/test_prompt_directory_layout.py` builds the wheel and asserts every
prompt in the source tree is inside it, so the four later epics get the failure
without knowing this entry exists. Asserting the `package-data` line instead
would not have worked — the glob first shipped here was `prompts/*.md`, which is
present, correct-looking, and matches neither a prompt in a subdirectory nor one
with another extension.

**And that fix was itself wrong, which is the part worth keeping.**
`prompts/*.md` was written to match ADR 0032's naming scheme exactly, and
matching the scheme was the error: a packaging glob that encodes a naming rule
enforces that rule by making the offending file absent from every container,
which is the worst available way to report a broken convention. It was widened to
`prompts/**/*` — the whole directory, any depth, any extension — so that
packaging decides only what reaches production, while the scheme stays enforced
by review and by the version test. Both narrow cases were measured by planting a
file and building rather than argued: `prompts/v2/moderation.md` and
`draft.v1.jinja` were each dropped in silence.

**Second rule, from that.** A fix to packaging, to an ignore rule, or to any
other glob-shaped configuration is not finished when the case in front of you
passes. Ask what the surrounding tests already *permit* — here, a sibling test
deliberately accepts a version held in a directory — and make the configuration
admit all of it. A glob narrower than the layouts the suite allows is a trap
primed for whoever first uses one of them, and it will look correct in review.

---
