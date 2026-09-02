# 0118 — The provider configuration splits in two, and one construction flag chooses between them

**Status:** Accepted
**Date:** 2026-09-02
**Tickets:** E2-12
**Supersedes in part:** [0113](0113-the-mock-model-provider-is-development-only-and-selects-in-band.md) — its transport and catalog decisions are restated by this shape; see *Consequences*.

## Context

E2-07 put an OpenAI-compatible mock in the base Compose file and ADR 0113 made
`.env.example` point the application at it, so that `docker compose up` on a
clean checkout classifies a comment without calling a model anybody pays for and
CI's e2e job — which copies that file verbatim — does the same. Three variables
described one endpoint, and the endpoint they described was the mock.

E2-12 turns SPEC §9.3's eval floors enforcing. The eval runner is the one thing
in this repository that has to reach a *real* provider, and the trouble is where
it runs: `make evals` runs on a developer's machine, where `ENVIRONMENT` is
`development` and where everything else has to keep reaching `mock-ai`. So with
one triple, reaching a real provider meant overwriting the values the development
stack needs, and keeping the development stack working meant having no real
provider configured at all. Both cannot be true of one set of three variables at
one moment.

That is not merely inconvenient. An eval run against `mock-ai` succeeds, and it
measures SPEC §3.3's twenty-five-character rule wearing a model's clothes: the
mock answers `substantive` to any comment over the threshold, in milliseconds,
and the runner writes the resulting precision and recall down as §9.3's floor —
a floor a character counter clears forever. The numbers look plausible and
nothing anywhere says the model was never asked.

The spec is silent on all of it. §6.3 lists the configuration surface as "AI
provider (base URL, model, masked key)" and names no variable and no second
endpoint; §7.4 says the gateway speaks to an OpenAI-compatible base URL and says
nothing about there being two.

## Decision

**Two triples, both configured at once.** `AI_PROVIDER_API_KEY`,
`AI_PROVIDER_BASE_URL` and `AI_PROVIDER_MODEL_NAME` describe the real provider —
the last renaming `AI_MODEL_NAME`, which said which model without saying whose
and is ambiguous the moment two are configured. `MOCK_AI_PROVIDER_API_KEY`,
`MOCK_AI_PROVIDER_BASE_URL` and `MOCK_AI_PROVIDER_MODEL_NAME` describe the mock.
`.env.example` documents all six.

**One construction flag chooses.** `AIGateway(live: bool = False)`:

- `live=True` reads the real triple **in every environment**. That is the eval
  runner's, and "every environment" is the whole of it — a run on a laptop and a
  run in CI measure the same thing or they measure nothing comparable.
- `live=False` reads the mock triple in development and test, and the real triple
  in a deployment. That is every other caller's: §3.3's submit path classifies
  through `mock-ai` on a development machine and through the institution's own
  provider in production.

The default is `False` because every caller except one wants it, and because the
other default fails silently and expensively: a `live=True` default would send a
clean `docker compose up`, and every test that forgot the flag, to a paid
endpoint with a student's comment in the body, with nothing going red.

**The real triple may never name the mock, in any environment.** ADR 0113's
catalog rule loses its development exemption. That exemption existed for one
reason — `.env.example` had a single base URL and it pointed at `mock-ai` — and
the split moved that address to a variable of its own, so the exemption protects
nothing and costs the eval gate.

**The mock triple carries no rule at all, and is unread outside development and
test.** It is *meant* to name `mock-ai`, so refusing that would refuse the
configuration a clean checkout ships. A deployment that copies `.env.example`
forward without editing those three lines is not misconfigured, because nothing
there consults them. Its two non-credential settings are therefore defaulted —
the one place in `Settings` where a working literal default is correct rather
than the silent misconfiguration that class's docstring refuses.

**The mock's key is a `SecretStr` like the real one.** The mock authenticates
nobody, so the variable exists for the developer who points that base URL at
something else — a colleague's model server, a proxy — and the moment such a
value is real it is a credential. Which of the two is real is not something this
repository can know, and a masked key beside an unmasked one is still a
credential in the log aggregator.

## Alternatives rejected, and why

**One triple plus an `EVAL_AI_PROVIDER_*` override read only by the runner.**
The same six variables with one of them named after a job rather than after what
it describes. It makes the eval runner special in the configuration surface,
where what is actually special is the *mock* — and it leaves the submit path and
the eval runner reading the same three names in a deployment, which is the one
case where they genuinely agree and the one place a reader would want to see
that they do.

**Selection from the environment alone: development means the mock.** This is
the natural reading of ADR 0113 as it stood, and it is correct for every caller
but the one this ticket exists for. It points `make evals` at the character
counter, which is the failure the whole split is written to prevent.

**Selection from the flag alone: `live=False` means the mock, everywhere.**
Cheaper to write, correct on both development rows, and it points production at
`mock-ai`. The rule has to read both inputs, which is why the tests hold all four
combinations rather than the three that disagree.

**Leaving the catalog rule conditioned on the environment.** It passes every
other row in the suite, because every other row exercising that rule is already
in a deployment. It also leaves a developer free to point the real triple at the
mock and measure a §9.3 floor against it, which is the whole hazard restated.

**Requiring the mock's three variables.** It would make a deployment refuse to
start over a variable it will never consult, including every deployment whose
`.env` predates this split. A startup refusal that protects nothing is worse than
a default that resolves only where it is read.

**Keeping `AI_MODEL_NAME` and adding `AI_PROVIDER_MODEL_NAME` beside it.** Two
names for one value is the state where a reader picks one and a writer sets the
other, and the symptom is a gateway asking for a model nobody configured —
recorded, under ADR 0031, as the `model_id` of a real classification.

## Consequences

**ADR 0113 is superseded in part and stays in place.** Its in-band selection
decision, its argument for the mock existing at all, and its transport-rule
reasoning are untouched and are still the record. What moves is one clause: the
catalog rule it made environment-conditioned is unconditional now, and the
address that exemption existed for lives on another variable. 0113 carries a
pointer to this record at that clause.

**The transport rule keeps its development exemption, and that asymmetry is
deliberate.** It was never about the mock: it is about a developer with a model
server on another machine on their own network, which the split does not touch.
Removing both conditions together would have refused that developer for a reason
belonging to a different rule.

**`make evals` is the one local command that spends money**, about a hundred
provider calls a run. It loads `.env`, because the real credential lives there
and the runner always builds a live gateway. README.md says what it costs and
when CI fires it.

**Nine test modules and four fixtures were repaired for the rename**, and four
committed integration modules moved with them, because a fixture that configures
a test-process gateway is configuring the mock side by this decision's own rule.
That is `docs/MISTAKES.md` entry 22, and it was swept for before the code was
written rather than met in a runner.

**Two settings now have a working default that resolves only in development**,
and the module docstring's blanket sentence about deployment wiring needed a
carve-out saying so. That is a small crack in a rule that has held cleanly since
E0-01, and it is stated at the fields rather than summarised, because the reason
is specific: a service this repository itself ships, read in two environments,
addressed by a name only the Compose network resolves.
