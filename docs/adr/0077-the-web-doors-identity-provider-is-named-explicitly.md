# 0077 — The web door's identity provider is named explicitly, and a mock address is refused outside development

**Status:** Accepted
**Date:** 2026-08-22
**Ticket:** [E0-39](../tickets/e0/E0-39-the-configuration-trusts-the-mock-idp.md)
**Supersedes in part:** [ADR 0075](0075-the-two-doors-addresses-are-settings-defaulted-to-the-development-stack.md)
— the five `OIDC_*` fields only. The two launch-door fields, the per-value
horizon rule, and the public client with no secret all stand exactly as written
there.

## Context

[ADR 0075](0075-the-two-doors-addresses-are-settings-defaulted-to-the-development-stack.md)
gave seven addresses defaults naming this repository's development stack, on the
argument that none of them can resolve in a deployment: a deployment that forgot
one would fail at its first hop rather than run quietly wrong. It recorded the
alternative it declined — required fields with no default — and said "If a
deployment ever starts with one of these wrong and nobody notices, this is the
record to revisit."

The epic-boundary threat model (2026-08-22, MEDIUM) found that the argument was
false for five of the seven. `docker-compose.yml` starts `mock-idp` in **every**
deployment, per SPEC §7.2 and for the reasons
[ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md) gives about
the platform. So `http://mock-idp:8000` does resolve wherever this stack runs,
and an operator who deploys per §7.2 and sets no `OIDC_*` variable has a provider
on their own network that mints an `id_token` for any identity asked of it —
CARE and ADMIN included — which Pulse then verifies correctly, against the mock's
own key set, and trusts. The only thing blocking that flow in a base-only
deployment was a coincidental redirect-URI disagreement between two files, which
the development override removes.

The mock LMS has a second gate for exactly this shape: ADR 0038's fourth property
rests on there being no `lti_platform` row, and `seed_mock_platform` guards the
row it now writes on `ENVIRONMENT`
([ADR 0068](0068-the-demo-seed-registers-the-mock-platform-behind-its-guard.md)).
The mock IdP's trust is configuration and nothing else, and the configuration
trusted it by default.

## Decision

**The five `OIDC_*` settings are required, and a mock address is refused outside
development.** Two layers, both in `backend/app/config.py`:

1. `oidc_issuer`, `oidc_authorization_endpoint`, `oidc_token_endpoint`,
   `oidc_jwks_url` and `oidc_client_id` lose their defaults and join the required
   group. A process given no identity provider stops at startup with a
   `ConfigurationError` naming the missing variable, exactly as every other piece
   of deployment wiring already does.
2. Where `ENVIRONMENT` is not `development`, any of the four URLs whose parsed
   host is the Compose service `mock-idp` is refused, and an `oidc_client_id`
   equal to the mock's registered `mock-idp-client` is refused. The refusal names
   the field and quotes no value: it reaches the container startup log (SPEC
   §10).

The catalog is those two spellings and nothing else — the name a container on
this stack reaches the mock by, and the name a configuration calls it by without
addressing it. The host is compared as a parsed component, so the port, the
scheme and the path do not excuse it and `https://mock-idp.example.edu` is not
caught; the client id is compared whole.

**`localhost` and the loopback addresses are deliberately outside the catalog.**
Inside a deployed container `localhost` is that container, so it cannot reach the
mock: refusing it would protect nothing while refusing a provider running
alongside the application, which is a supported deployment. It is also the
development stack's own `OIDC_AUTHORIZATION_ENDPOINT`, because a browser on the
host reaches the mock on a published port.

The clean-checkout property ADR 0075 bought is kept without the default.
`docker-compose.yml` gives all three `Settings`-building services the five as
`${OIDC_ISSUER:-http://mock-idp:8000}` and so on, and `.env.example` documents
them, so `docker compose up` from a clean checkout still reaches a system a
person can log in to (SPEC §14.3) while a deployment's own `.env` still wins.

## Alternatives rejected, and what each costs

**Leaving ADR 0075 standing.** Its reasoning is preserved rather than deleted,
and the price is stated in its own words: a developer running `uvicorn` on the
host against a half-written `.env` now gets a startup refusal naming five
variables whose only correct value is one this repository already knows. That is
what this decision pays for closing a signing oracle, and it is a smaller bill
than 0075 estimated, because the values moved into Compose and `.env.example`
rather than disappearing.

**Layer 1 alone — required fields, no refusal.** Stops the deployment that
configures nothing. It does not stop the ordinary way a wrong value arrives: an
operator copying the development stack's `.env` forward. Cheap to add the second
layer, and it is the layer that catches the realistic mistake.

**Layer 2 alone — keep the defaults, refuse the mock outside development.**
Tempting, and it closes the same hole. Rejected because it leaves the module's
own rule broken for these five — deployment wiring with a working default — and
because it makes the refusal load-bearing in a way that a typo in `ENVIRONMENT`
would defeat silently. Two layers means the deployment has to name a provider
*and* the named provider has to not be the mock.

**Keeping the mock out of the base Compose file instead.** The direct fix for the
finding, and out of this ticket's reach: SPEC §7.2 puts the service there, and
ADR 0038 argues a profile would take it out of CI's base-file-only pass — the one
pass that runs what actually ships. Refusing to *trust* the mock is the property
that matters; the container existing on a network buys an attacker nothing while
no configuration names it.

**Refusing `localhost` too.** Would catch an operator who deploys with the
development file's browser-facing authorize URL. Rejected above: it refuses a
legitimate deployment shape and protects nothing, since a container's own
`localhost` is not the mock.

## Consequences

- A deployment that upgrades into this and had relied on the defaults stops at
  startup instead of trusting the mock. That is the point, and the message names
  each variable.
- `ENVIRONMENT` is now load-bearing for the web door, not only for `/docs`
  ([ADR 0074](0074-the-openapi-schema-is-served-only-in-development.md)), the SQL
  echo and the seed's own gate. It is still free-form and still compared exactly
  against `development` — anything else is a deployment, so `staging`,
  `development-blue` and `pre-development` all refuse the mock.
- The five fields are declared after `environment` in `Settings`, and that
  ordering is load-bearing: the validators read the already-validated
  `ENVIRONMENT`, and pydantic validates in declaration order. A comment at the
  block says so.
- The catalog is two written-out strings, so it can go stale silently — a rule
  refusing a name nothing runs under reports every configuration clean
  (`docs/MISTAKES.md` entry 35). Two tests hold it against the Compose service
  and against what `.env.example` configures.
- Tests whose subject is something else and which build a non-development
  `Settings` now have to name a non-mock provider. `tests/conftest.py` gained one
  fixture for it rather than each module inventing placeholders.
- ADR 0075's remaining two fields keep their defaults on an argument that is now
  narrower and true: neither `PUBLIC_BASE_URL` nor
  `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` names a service the base Compose file
  starts.
