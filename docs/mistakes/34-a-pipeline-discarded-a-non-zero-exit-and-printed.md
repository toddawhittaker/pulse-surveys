# Entry 34. A pipeline discarded a non-zero exit and printed a line that read as success

**Caught: 1**

*2 instances recorded: one occurrence, and one catch.*

*(An occurrence, not a prevention, and it earned no bump: this
entry did **not** stop the mistake here. In E0-33, by the orchestrating session, against this entry's own
command. `make ci 2>&1 | tail -45` printed the tail of a run in which `lint` had
died on `ruff: command not found`, and the harness reported the *pipeline's*
exit code of zero. The failing line `make: *** [Makefile:82: lint] Error 127`
was visible in the output that was read, and was read past, because the exit
status said success. Re-running as `make ci > ci.log 2>&1; echo $?` reported 2.
The entry was written five commits earlier in the same epic and was not recalled
while typing the pipe — which is the point of it having a number.)*

*(The first prevention, in E0-36 item 4, inside a **gate being written** rather
than in a command being run. `scripts/ci/check_image_contents.sh` builds the
runtime image and has to decide whether four planted files reached it. The
obvious line is `docker run --rm "$image" python -c '…' | grep -qF "$name"`, and
it is this entry exactly: `docker run` exits non-zero when the image is missing,
when the interpreter cannot import the package, or when the listing raises, and
in every one of those cases `grep` finds nothing, returns 1, and the check
reports "no stray file reached the image" — a green gate over an image it never
read. The script redirects the listing to a file, checks the status of the
`docker run` separately, and refuses an empty listing before believing an
absence. **The mechanism reaches further than the rule's wording suggests**: the
original instance was a human piping a gate at a terminal, and this one is a pipe
compiled into a gate, where it would have re-reported the same false green on
every run rather than once. Any check whose verdict is "the search found
nothing" has to prove separately that the search ran.)*

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** The orchestrating session ran

```bash
ruff check . 2>&1 | tail -2 && echo "LINT OK"
```

over `e0/ai-gateway-roundtrip`, saw `LINT OK`, and reported the branch clean. In
a pipeline the shell takes the exit status of the *last* command, so `tail`'s
zero replaced ruff's one, `&&` fired, and the line printed. `ruff check .`
exited 1 the whole time, on two `B017` violations in a test module.

The cost was a round. The test author had inferred that `B017` applied only to
`unittest`'s `assertRaises`, removed four `# noqa: B017` directives on that
inference, and — correctly — asked for the inference to be confirmed on a real
run, because it has no shell. The confirmation it got back was a green line from
a pipe. It was told its reasoning held when the measurement said the opposite,
so four directives that were doing their job stayed removed and CI lint stayed
red until the next full run.

**Root cause.** The rule against this exists and was read as being about one
command rather than about a mechanism. `CLAUDE.md` says "never pipe `make ci`"
and gives this exact reason, so it was filed under the command whose failure is
expensive instead of under pipes, which is what discards the status. Every gate
in this project is a command with an exit code — `ruff`, `mypy`, `pytest`,
`pip-audit`, `alembic check`, the CI checker self-test — and piping any of them
into `head`, `tail`, `grep` or `wc` throws the verdict away and keeps the output,
which is the half that looks like evidence.

**Consequence.** A round. An agent with no shell had asked for an inference to be
confirmed on a real run, and was handed a green line from a pipe. It removed four
`# noqa` directives that were doing their job, and CI lint stayed red until the
next full run. The general form is worse than the specific one: when the reader
cannot run the command themselves, a green line that was never earned is
indistinguishable from one that was, and they build on it.

**Why the existing warning did not prevent it.** `CLAUDE.md` says "never pipe
`make ci`" and gives this exact reason. The rule was read as being about `make
ci`, which is the command whose failure is expensive, rather than about pipes,
which is the mechanism. Every gate in this project is a command with an exit
status: `ruff`, `mypy`, `pytest`, `pip-audit`, `alembic check`, the CI checker
self-test. Piping any of them into `head`, `tail`, `grep` or `wc` throws the
verdict away and keeps the output, which is the half that looks like evidence.

**The shape, and why it is not entry 9.** Entry 9 is citing a guard without
executing it. Here the guard *ran* and returned the right answer; the plumbing
between the guard and the reader discarded it. That failure survives every
discipline aimed at "did you actually run it", because the honest answer is yes.

**Rule.** Redirect and capture the exit status; never pipe a gate.

**What to do instead.** Redirect and echo the status:

```bash
ruff check . > /tmp/lint.log 2>&1; echo "exit=$?"
```

Read the file afterwards if the output is long. When a command's exit status is
the thing being reported to somebody who cannot run it themselves, the status has
to be captured from the command rather than inferred from what it printed — and
an agent with no shell is exactly that somebody, which is what made this
expensive rather than merely wrong.
