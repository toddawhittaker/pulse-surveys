# E0-29 — Review debt from E0-13

**ID:** E0-29
**Branch:** `e0/review-debt-e0-13`
**Depends on:** E0-13

## Status — what is left here

**Mostly decisions and records.** One item is a batch item, one is closed, two
are Todd's, and the rest stay here or leave the epic.

| Item | Now |
|---|---|
| 1a — cleartext to an off-machine endpoint with no credential | **Todd's decision** — deployment policy |
| 1b — HTTP 429 and 500 outside the fail-open set | **Todd's decision** — settle or affirm |
| 2 — three taxonomy rows nothing asserts | **Carried out of E0** — none is producible from a loopback stub |
| 3 — `MISTAKES` entry 26 presents a superseded resolution | **Closed** |
| 4a — `tiktoken` reaches the network at first use | **This ticket**, as a recorded decision — it cannot be dropped without dropping the `[openai]` extra |
| 4b — `regex` and `tiktoken` classify as `unknown` licence | [E0-36](E0-36-ci-gate-fidelity.md), which ships it as **its own pull request** because it is a gate change |
| 4c — `make lock` should constrain the dev lockfile | [E0-36](E0-36-ci-gate-fidelity.md) item 5 |
| 5 — `run_task` from inside a running event loop | **Carried to E2** |

On item 3: `docs/mistakes/26-a-fallback-path-swallowed-the-defect-that-triggered-it.md`
now says plainly that the narrowing the entry prescribes was made and did not
hold, and points at entry 33.

Both decisions land in ADR 0056 when they are made, not in a pull request comment.


## Context

What E0-13's two review passes found and could not close in place, collected the
way E0-21 collects E0-05's, E0-24 collects E0-07's and E0-08's, E0-25 collects
E0-09's, E0-12's and E0-14's, E0-26 collects E0-10's, E0-27 collects E0-11's, and
E0-28 collects E0-15's. What could be closed in E0-13's own pull request was, and
it is indexed at the bottom so this file is a complete record of the round rather
than a list of what was skipped.

**Nothing here blocks the E0 exit.** Two items are decisions rather than defects
and belong to Todd. Three are gaps in what the suite can reach from a loopback
stub. The rest are records and supply-chain hygiene.

Read first: [ADR 0053](../../adr/0053-the-gateway-speaks-openai-through-pydantic-ai.md),
[ADR 0054](../../adr/0054-a-floored-classification-names-the-floor-in-its-audit-pair.md),
[ADR 0056](../../adr/0056-only-a-timeout-fails-open.md), SPEC §3.3 and §7.4, and
`docs/MISTAKES.md` entries 26, 33 and 34.

## Scope

### 1. Two decisions that are Todd's, not an implementer's

**1a. Cleartext to an off-machine endpoint with no credential is permitted.**
E0-13's transport rule refuses `http://` to another host when a credential is
present — in the key variable or in the URL's userinfo, both now covered. It
permits plain `http://` off-machine when there is no credential at all, because
that is the vLLM-in-a-cluster case `README.md` and `.env.example` both document as
supported. Student comment text still crosses that link in the clear. Refusing it
outright is a deployment policy decision, not a build fix.

**1b. HTTP 429 and 500 are deliberately outside the fail-open set.** ADR 0056's
taxonomy floors on a read or write timeout and on 408/502/503/504, and raises on
everything else. The implementer's reasoning: a rate limit is a capacity decision
an operator must see, and a 500 means our request is the problem, so flooring
either hides a condition that never resolves — one comment at a time. It named
this as the row it expected an argument about. Settle it or affirm it.

### 2. Three rows of ADR 0056's taxonomy that nothing asserts

`test_the_taxonomy_this_module_exercises_has_a_case_on_each_side_of_the_floor`
records the gap rather than hiding it, which is why this is debt and not a defect.
DNS failure, TLS handshake failure and pool timeout are all in the no-floor column
and are asserted by nothing, because none can be produced from a loopback stub
without a network the suite refuses to touch.

Separately, `test_a_connect_that_never_completes_raises_rather_than_flooring`
exercises the `ConnectTimeout` subclass edge **only on a platform that drops the
SYN rather than refusing it**. Where the kernel sends RST instead, it exercises
the refused-connection row. Both are in the no-floor column so the verdict is the
same, but the precision degrades and the docstring says so.

Done when: either the three rows are reachable in a test environment that can
produce them, or SPEC/ADR 0056 records that they are asserted by construction and
says what construction means here.

### 3. `docs/MISTAKES.md` entry 26 presents a superseded resolution

Entry 26 closes by citing ADR 0056 as its fix. That ADR has since been rewritten,
because the narrowing it originally described put `httpx.ConnectTimeout` on the
wrong side of the fail-open line — which is entry 33. Entry 33 exists and entry 26
now points forward to it, but entry 26's own closing paragraph still reads as
though the first version resolved it. A reader following entry 26 as written
reproduces the defect. It needs a corrective clause from whoever owns that text.

This is entry 1's shape sitting inside the file that records entry 1.

### 4. Supply chain

**4a. `tiktoken` reaches the network at first use.** It arrives transitively under
`pydantic-ai-slim[openai]` and cannot be dropped without dropping the extra. Its
only consumer inside `pydantic-ai` is the embeddings module, which this gateway
never imports. `tiktoken/load.py` performs a `requests.get` to an Azure blob host
on first use, caching to the system temporary directory — a live egress path
outside the locked closure, in the process that ships student comment text. It
also puts a third HTTP stack (`requests`/`urllib3`) in that image beside `httpx`
and `httpx2`.

**4b. `regex` and `tiktoken` classify as `unknown` licence.** Both are permissive
and MIT-distribution compatible: `regex` is `Apache-2.0 AND CNRI-Python`, and
`tiktoken` ships the full MIT text in its `License:` field, which the checker's
`AND` split shatters. The gate is right in outcome and accidental in mechanism.
Widening `scripts/ci/check_licenses.py` is a gate change and belongs in its own
pull request saying what it now accepts.

**4c. `make lock` should compile the dev lockfile against the runtime lockfile**
(`-c requirements.txt`). Two independent resolutions of overlapping requirement
sets skewed `charset-normalizer` to two versions during E0-13; every test passed
and only `pip-audit` saw it (`docs/MISTAKES.md` entry 25). The recipe has to keep
matching `.github/workflows/ci.yml`, so the two move together.

### 5. A shape E2 needs to know about

Calling `run_task` from inside a running event loop raises
`RuntimeError("Cannot run the event loop while another loop is running")`, outside
the `AIGatewayError` taxonomy. Not reachable today — ADR 0013 makes handlers `def`
and FastAPI runs them in its threadpool — so an async endpoint calling
`classify_comment_validity` directly would 500. Recorded in ADR 0053's
consequences rather than defended against. E2 owns whether that stays a
convention.

## Out of scope

- The submit path, its p95 budget, and catching `AIGatewayError` there (E2).
- Eval sets, the eval runner, and the precision/recall floors (E2 onward).
- The four other §7.4 tasks.

## Acceptance criteria

- [ ] Items 1a and 1b are settled by Todd in writing, and the answer lands in
      ADR 0056 rather than only in a pull request comment.
- [ ] Item 2 either gains the three assertions or gains a record saying why they
      cannot exist here and what covers them instead.
- [ ] `docs/MISTAKES.md` entry 26 no longer presents ADR 0056's first version as
      the resolution.
- [ ] 4a, 4b and 4c are each either done or explicitly deferred with a reason.
- [ ] Nothing in this ticket weakens a gate to close an item. Where an item is a
      gate change, it is its own pull request saying what coverage changed.

## Definition of done

**Tests apply**, to whatever part of item 2 becomes reachable.

**Docs apply.** Items 1a, 1b, 3 and 5 are all record work.

**AI evals do not apply** — no eval set ships here.

**Accessibility does not apply.**

**Security review applies but is light.** 1a is the only item with a live
exposure, and it is a decision rather than a finding.

## What E0-13's review did close

Two HIGH findings, four MED and three LOW across two passes, all closed in E0-13's
own pull request and all verified by mutation rather than by the suite passing:

- **HIGH** — one httpx connection pool shared across per-thread event loops, so a
  reused connection raised, was misread as an outage, and fell into §3.3's
  sanctioned fail-open. Measured: every second submission silently skipped the
  classifier while the provider answered, and the stub saw all six requests, so
  the comment went to the third party and the answer was discarded.
- **HIGH** — student comment text reassembling verbatim in an exception message
  and from there into a container log, because the error's `loc` is a
  model-invented key and the count of details was unbounded.
- **MED** — a failed TLS handshake reported as a timeout and floored.
- **MED** — a credential in the URL's userinfo bypassing both the transport rule
  and `SecretStr` masking, rendering in `model_dump()` and §6.3's admin view.
- **MED** — half the audit pair taken from the provider unvalidated, so a provider
  reporting `no-model` forged ADR 0054's floor sentinel.
- **MED** — the fail-open path could stop recording entirely with 654 tests green.
- **MED** — nothing asserted the comment or the versioned prompt reached the
  provider.
- **MED** — `pulse_app` was never asserted to lack `UPDATE`, `DELETE` and
  `TRUNCATE` on `classification`, and the two behavioural tests ran on the
  bootstrap connection, which holds every privilege.
- **LOW** — a 200 whose body is not JSON escaping the `AIGatewayError` taxonomy.
- **LOW** — three documents describing an `Authorization` header the gateway does
  not send.

One dispute was raised and upheld: `docs/disputes/E0-13-01.md`, on a leak
detector whose fixture contained the word `provider`, which every rendering of
`Settings` already holds.
