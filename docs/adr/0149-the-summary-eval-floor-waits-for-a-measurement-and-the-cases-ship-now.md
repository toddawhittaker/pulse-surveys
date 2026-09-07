# 0149 — The summary eval floor waits for a measurement, and the cases ship now

## Context

SPEC §9.3 gates prompt and model changes on "per-task precision/recall floors",
and E4-05's fifth acceptance criterion refuses to let the question be dodged:
either this ticket sets an enforcing floor for the weekly-summary task, or it
records why the floor waits and for what measurement. Silence is not an option,
and `prompt-eval` checks for exactly this on the pull request.

The spec fixes neither the numbers nor what a summary metric even is. Precision
and recall are natural for a classifier — the validity task's floors are 0.92 and
0.90 against a closed set of three verdicts — and a summary has no closed set at
all. What §5.1 asks of one is that clearly critical themes are preserved, never
sanded off; that is checkable, but what fraction of a real provider's answers
clear it on a real week is a distribution nobody in this project has measured.

E2 met the same question for the validity task and answered it in two steps: the
cases first, the numbers after a run against the live provider. That is the prior
art this record follows.

## Decision

**The cases ship now with their capability to fail proven offline; the numbers
are set by the first real-provider measurement run.** The registry's summary slot
is `DEFERRED` — carrying no cases, no classifier and no number — so the runner
reports the task as ungraded on every run and never fails on it, and the live
eval job in CI spends nothing on the summary task.

What ships in place of a number:

- **Four typed cases** for the families §5.1 and E4-05 name: criticism preserved
  through paraphrase, a small-N week of two comments still summarized, an empty
  week producing the stated empty shape, and a mixed week where both the praise
  and the specific complaint survive.
- **Checks that survive paraphrase and are not a keyword match.** A signal is a
  pair — what was talked about, and what was said about it — and it counts as
  preserved only when one span of the answer, a sentence or a theme label,
  carries both halves. A summary naming every topic and passing judgement on none
  fails, which is the failure a keyword check reports as success.
- **The proof that the cases can fail, executed rather than asserted.** The
  sycophantic prompt variant's answers — fluent, warm, shape-valid, criticism
  removed — are run through the real checks on every ordinary test run, and each
  must fail the case whose criticism it sanded, naming that signal. **That proof
  is offline**: it grades built answers rather than asking a provider for them.
  The live re-proof, running the variant against a real model, rides the
  measurement run below.

**The measurement that lifts the deferral**, stated so that "waiting" has an end:
the first run of the four cases against the real provider, dated from 2026-09-06
and owned by that run. It sets precision and recall — or whichever metric pair it
concludes is the right one for a task with no closed answer set — and the floors
land in the summary set's own floors module with the measurement and headroom
sentences the validity floors already carry.

## Alternatives rejected

- **Set a number now.** It would be a floor nobody measured, and the direction of
  the error is not knowable in advance: too low and the gate certifies whatever
  the model does, too high and the next AI-touching pull request is red for a
  reason nobody can act on. The eval declarations have a state for exactly this,
  and the runner refuses a number written into it.
- **`AWAITING_MEASUREMENT` instead of `DEFERRED`.** It is the louder state, which
  is usually the right instinct here. It is also a refusal: the runner exits
  non-zero on it, and this pull request's diff touches `backend/app/ai/`, so the
  eval job runs live on it and would go red over a task nobody has measured — a
  gate failing for the absence of a measurement it cannot itself take.
- **Attach the cases to the registry's summary slot without a floor.** Then a
  live run grades them and prints a number that gates nothing, at one provider
  call per case on every AI-touching merge from now until the floor is set. The
  slot carries no cases for that reason, and the suite asserts that no
  *registered* task carries them either — the set arriving one case at a time
  under another task's name is the same leak.
- **Prove the sycophantic breach live in CI.** It is the stronger proof and the
  one the criterion's wording invites. It also spends a provider call per case
  per merge to re-establish a fact about the checks rather than about the model,
  forever. Proving it offline costs nothing and proves the thing that would
  otherwise be assumed: that the checks can fail at all.

## Consequences

- The summary task is visible as ungraded on every eval run rather than absent,
  which is the difference between a staged floor and a forgotten one.
- Until the measurement, nothing in CI stops a summary prompt change that makes
  answers worse. The offline demonstration is not a substitute for that and does
  not claim to be: it says the cases can fail, not that the model passes.
- The measurement run inherits a decision as well as a task: whether precision
  and recall are the right pair for a task with no closed answer set, or whether
  the floor is better stated as a pass rate over the contract checks. That choice
  belongs with the data rather than ahead of it.
- The cases are pinned to `summary.v1`. A prompt bump reds the pin until somebody
  says the set has been re-measured, which is the conversation the pin exists to
  force — ADR 0032 makes the two versions different texts, so a measurement over
  one says nothing about the other.
