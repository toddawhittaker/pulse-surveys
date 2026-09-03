# 0113 — The mock model provider is development-only, and selects its wrong answers in band

**Status:** Accepted, and **superseded in part by
[0118](0118-the-provider-configuration-splits-in-two.md)** (E2-12, 2026-09-02).
One clause moves and the rest stands: the catalog rule below is unconditional
now, because 0118 gives the mock a configuration triple of its own and the
development exemption existed only so that this record's single base URL could
name `mock-ai`. Everything else here — in-band selection, the argument for the
mock existing at all, and the transport rule's own development exemption, which
was never about the mock — is unchanged and is still the record.
**Date:** 2026-09-01
**Tickets:** E2-07

## Context

SPEC §9.2 makes an end-to-end run self-contained in Compose, and E2-07 adds the
third external dependency's stand-in: `mock-ai`, an OpenAI-compatible endpoint in
the base Compose file that the gateway cannot tell from a provider. Three
questions follow that the spec does not answer.

**How a development stack reaches it.** `Settings.ai_provider_base_url` carried
an unconditional transport rule from E0-37 item 12: off this machine means
`https`, credential or not. `http://mock-ai:8000/v1` is cleartext to a Compose
service name, which is not this machine by any reading — so the rule as it stood
refuses the configuration E2-07's first and fourth acceptance criteria both run
from, and `docker compose up` on a clean checkout would not start the API at all.
SPEC §10 requires the encrypted transport and says nothing about which
environments; §14.3 requires that a clean checkout comes up.

**What stops a deployment reaching it.** ADR 0038 puts a mock in the file every
deployment runs, so this service starts wherever the stack does. ADR 0077 already
found what that means for the identity provider and refused to leave it standing.
E2-07's ticket says the same in one sentence — "nothing may point production at
it" — and settles nothing about the mechanism.

**How a test drives a wrong answer.** E2-07's second criterion needs one
reachable path per row of ADR 0056's taxonomy: a 503, a 500, a malformed shape,
and an answer late past the four-second budget. The mock has to be told which,
and the ticket's own scope forbids the obvious route — "nothing in the backend
changes: the gateway cannot tell this mock from a provider, which is the point."

## Decision

**The transport rule becomes environment-conditioned, and a second rule refuses
the mock by name.** Both are field validators on `ai_provider_base_url` and both
mirror the identity provider's, which ADR 0077 put on its four URLs:

- `an_off_machine_endpoint_is_encrypted` returns early when
  `is_a_deployment(ENVIRONMENT)` is false. The exemption is the *environment*,
  not the host: a developer running a model server elsewhere on their own network
  is the same situation, and a rule that carved out `mock-ai` alone would refuse
  them while being one line longer. The on-this-machine exemption does not move —
  a sidecar is reached at `localhost` in production as readily as on a laptop.
- `no_provider_url_addresses_the_mock_model_outside_development` refuses a base
  URL whose host is `MOCK_AI_PROVIDER_HOST` (`"mock-ai"`) in a deployment. The
  host is compared as a normalised component through `url_host`, so port, scheme,
  path and case are not part of the question and `https://mock-ai.example.edu/v1`
  — an ordinary institutional address — is not refused.
  **This is the clause [0118](0118-the-provider-configuration-splits-in-two.md)
  supersedes.** The validator is `no_real_provider_url_addresses_the_mock_model`
  now, it refuses in every environment including development, and the address
  this exemption was written for moved to `MOCK_AI_PROVIDER_BASE_URL`, which
  carries no such rule because nothing outside development and test reads it.

`environment` moves to the head of its block in `Settings`. pydantic validates in
declaration order and `info.data` holds only fields already validated, so a rule
conditioned on `ENVIRONMENT` reads `None` on any field declared above it and
`is_a_deployment(None)` is `False` — the rule would permit everything, silently.
The identity provider's five settings already sat below `environment` with a
comment saying why; the two AI settings did not, because neither had a rule that
read it.

**The mock's wrong answers are selected in band, by marker phrases in the
comment.** A comment containing `mock-ai:503` gets a 503, `mock-ai:500` a 500,
`mock-ai:malformed` a 200 carrying `{"answer": 42}`, and `mock-ai:stall` the
correct answer six seconds late; `mock-ai:substantive`, `mock-ai:insufficient`
and `mock-ai:nonsense` force a verdict. The selection travels in the one thing
the request already carries that a test controls, which is what keeps the backend
unchanged. The whole vocabulary is served at `GET /mock/rules`.

## Alternatives rejected

**Leave the transport rule unconditional and reach the mock some other way.**
Three shapes were considered. TLS in front of the mock is a certificate to
generate, distribute and trust in four containers, for a service that terminates
nothing today. Pointing the stack at `localhost:8082` — the published debugging
port — is exempt from the rule, and wrong: it is the *host's* port, so `api`,
`worker` and `beat` inside the network cannot reach it, and the value would work
on a laptop and fail in CI. Naming `mock-ai` as a permitted exception to the
transport rule inverts the two rules — the mock would be the one address allowed
to be cleartext, in every environment, which is precisely backwards.

**Condition the transport rule as "in a deployment, require https", with no
loopback exemption.** Shorter, and it refuses the model-alongside-the-application
deployment §7.4 names as supported and E0-37 item 12 explicitly left standing.

**Refuse the mock by matching the development stack's exact URL.** One line, and
defeated by an operator who copies the address and changes the port, or who puts
a proxy in front of it. The four spellings in
`tests/unit/test_ai_provider_configuration.py` are what a host comparison
survives and a string comparison does not.

**Refuse any URL containing the string `mock-ai`.** The obvious way to write the
rule, and it turns away `https://mock-ai.example.edu/v1`,
`https://mock-ai-2.example.edu/v1` and `https://staging-mock-ai/v1` — every one
an address a real institution could hold. This is ADR 0077's argument transferred
unchanged.

**A catalog entry for the mock's client id, as the identity provider has.** There
is nothing to hold: this endpoint authenticates nobody, so a configuration cannot
name it except by addressing it. One entry rather than two.

**Select the wrong answer out of band** — a `?defect=` query parameter (ADR
0088's mechanism for the mock platform), a header, or a control route that arms
the next answer. The query parameter and the header both require the gateway to
put something there, which is the backend change E2-07's scope forbids and which
would mean the gateway *could* tell the mock from a provider. An arming route
makes the service stateful, and a stateful mock cannot produce the malformed
path at all: ADR 0053 gives the gateway one bounded re-ask, so the second request
has to get the same wrong answer for §7.4's "then the error" to be reachable.

**Extract the comment on `[[STUDENT_COMMENT]]`.** The marker the prompt file ends
with, and the obvious thing to look for. `app.ai.tasks.render_prompt` replaces it
with the comment, so it is not in the message a provider is sent: a mock reading
it would answer the extraction-failure 500 to every real classification while
passing any test that built its own prompt. The boundary is the last line of the
prompt's own instructions, which is what survives rendering.

**An unreachable selector**, to mint ADR 0056's fourth row. E2-07's scope rules it
out and the reasoning is sound: a mock that answers cannot fail to connect, so no
response this service returns can produce that row. E2-08 drives it with the
provider address pointed at a closed port.

## Consequences

**A student's comment can choose what the provider does, in development.**
Anybody who can type into a feedback box on a development stack can write
`mock-ai:substantive` and award themselves participation credit under §3.3, or
`mock-ai:500` and make the submit path raise. That is the price of in-band
selection and it is why the two configuration rules above exist: the exposure is
bounded to environments where `ENVIRONMENT` is `development`, and every other
environment refuses to address the service at all.

**The marker vocabulary is a namespace a real comment could contain.** Nothing
stops a student writing `mock-ai:503` into a production survey; it would reach a
real provider as ordinary text and mean nothing. The prefix exists so that the
reverse — an ordinary phrase read as a selector — cannot happen by accident.

**Two copies of one string, guarded.** `mock-ai/app/rules.py` holds the prompt's
marker line, because this package cannot import `backend/app/` (ADR 0039 — both
are called `app`). A unit test holds the copy against
`backend/app/ai/prompts/validity.v1.md`, so an edit to the prompt's last
instruction line goes red rather than turning every development classification
into a 500. That test is the whole of what makes the copy acceptable.

**The transport rule is now weaker on a developer's machine than it was.** A
laptop configured with `http://someone-elses-box/v1` is accepted where it used to
be refused, and a student's comment would cross that network in the clear. The
comments on a development stack are seeded or typed by the developer, so §4's
subject matter is not at risk; what is given up is the guard against a developer
who points a real `.env` at a real provider over plain HTTP and never sets
`ENVIRONMENT`. `.env.example` ships `ENVIRONMENT=development`, so that is a
plausible mistake rather than a contrived one, and this record is where it is
written down.

**Field declaration order in `Settings` is now load-bearing in two places rather
than one.** A future field carrying an environment-conditioned rule has to sit
below `environment`, and nothing enforces it — a rule declared above reads `None`
and permits everything, with every test that only exercises development still
green. The comment at `environment` says so; a rule that could be checked
mechanically is the thing to build if a third case appears.

**A record this falsified, corrected in the same change.** The docstring of
`a_provider_url_is_encrypted_off_this_machine_outside_development` said the model
provider's copy of the rule was unconditional and that the difference "is not an
oversight to tidy up later". It was true when written; it is now false, and the
paragraph says so rather than being deleted (`docs/MISTAKES.md` entry 1).
