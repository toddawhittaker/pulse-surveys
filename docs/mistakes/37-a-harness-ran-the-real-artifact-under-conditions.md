# Entry 37. A harness ran the real artifact under conditions the runtime does not use

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*3 instances recorded, oldest first; the newest is a catch.*

*(E0-38, and it was found by an audit written after the build was green. The
`changed` job's classification step was extracted from the parsed workflow and
executed, which is the right instinct and is what this repository does instead of
reading YAML. It was executed with `bash script.sh`. GitHub runs a `run:` block
that declares no `shell:` as **`bash -e {0}`**, and the step's own
`set -uo pipefail` adds two options without clearing an inherited `-e`.

The step's classifier exits 1 to mean "this diff is not inert", which is the
answer every code-touching pull request produces. Under `-e` a bare command
exiting non-zero ends the script, so `status=$?` was never reached. Measured
against the real step: exit 1, nothing emitted, the classifier's correct answer
sitting in the log above it. The `changed` job would have failed, every job
needing it would have reported `skipped`, and E0-36 had just made the aggregate
check treat `skipped` as a failure — so **every code-touching pull request would
have failed the required check**, starting with the one introducing it.

Two details make this worth an entry rather than a footnote. The harness was
correct in extraction and wrong only in invocation, so everything it reported was
real behaviour of the real artifact under a shell the runtime never uses. And the
correct pattern was already in the repository: `test_the_detect_probes_see_the_files_their_jobs_run.py`
invokes probes with `bash -e`, in the same workflow, written the round before.)*

*(E0-28 item 9, and this one runs the other way: the harness did not hide a
defect, it **manufactured one**, and the harness was the repository's own. The
mock platform hands out a per-user result URL with the identifier percent-encoded
whole, so a `sub` of `a/b` becomes `…/results/a%2Fb` and a `sub` of `a%2Fb` — an
ordinary identifier that happens to look like an encoding — becomes
`…/results/a%252Fb`. Two students, one decode each, distinct. The route was given
Starlette's `:path` converter and the second URL came back with the *first*
student's grade, at 200. Measured both ways on one throwaway route with one
`:path` parameter: **uvicorn** decodes the path once and hands the route `a%2Fb`,
which is right; **`fastapi.testclient.TestClient`** (starlette 1.6.0, httpx
0.28.1) decodes it twice and hands the route `a/b`, because its transport builds
the ASGI scope with `"path": unquote(path)` where `path` is httpx's `URL.path`,
already decoded. So the platform was correct in deployment and wrong in the suite
— and, worse in the other direction, a platform that added a decode of its own
would have passed in-process and served one student's grade to a request about
another in production. The fix was to stop trusting the router's count: read
`scope["raw_path"]` and decode it once. The entry-37 shape is exact — a real
artifact measured under conditions the runtime does not use — with one addition
worth the words: the offending harness was not one anybody wrote for the
occasion, it was the standard client every test in the repository drives these
mocks through.)*

**What happened.** Twice, a harness executed the genuine artifact and reported
measured results, and the results were about a configuration that does not occur.
The first hid a defect and the second invented one, which are the two directions
of the same error. Neither was subtle once seen — one was the difference between
`bash` and `bash -e` on one line, the other one `unquote` too many inside a test
client.

**Why it is not entry 12 or entry 20.** Entry 12 is a stale build of the thing
under test: the harness ran something other than the current artifact. Entry 20 is
a mutation the fixture undid. Here the artifact was current and nothing undid
anything — the *environment* was wrong, and the artifact behaved differently in it
than in production. That is a third way for a measurement to be true and useless.

**Rule.** When you extract something to run it, copy the invocation and not just
the body: the shell and its flags, the interpreter, the environment, the working
directory. Prefer a harness that already exists in the repository to one you
write, and when you write one, state which properties of the runtime it
reproduces and which it does not. **A harness the repository already uses is not
exempt** — it diverges from the runtime too, and because everything is measured
through it the divergence reads as a fact about the artifact. When a result
surprises you, reproduce it once against the real runtime before believing
either the green or the red. A measured result is only as good as the
conditions it was measured under, and those conditions are part of the artifact.

*(**A catch**, building E2-07's comment extraction, 2026-09-01. The obvious
marker to extract on was the prompt file's own `[[STUDENT_COMMENT]]` line — but
`render_prompt` replaces that placeholder before anything reaches a provider,
so a mock extracting on it would have passed every unit test (the fixtures
build their own prompts) and returned 500 for every real rendered prompt.
Acting on this entry's rule — reproduce the runtime's conditions, not the
harness's — the marker was taken from the rendered prompt the gateway actually
sends, and the choice was proved against the real render path in the
gateway-taxonomy tests before green was reported. The rejected placeholder is
recorded in ADR 0113.)*
