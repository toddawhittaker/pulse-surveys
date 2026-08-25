# 0077 — The web door's identity provider is named explicitly, and a mock address is refused outside development

**Status:** Accepted
**Date:** 2026-08-22
**Ticket:** [E0-39](../tickets/e0/E0-39-the-configuration-trusts-the-mock-idp.md)
**Supersedes in part:** [ADR 0075](0075-the-two-doors-addresses-are-settings-defaulted-to-the-development-stack.md)
— the five `OIDC_*` fields only. The two launch-door fields, the per-value
horizon rule, and the public client with no secret all stand exactly as written
there. **One of those two launch-door fields is gone as of 2026-08-25**: E1-05
moved the LTI platform's authorization endpoint onto the registration and
deleted the setting, so where this record says "the two launch-door fields" it
now covers `PUBLIC_BASE_URL` alone. Nothing this record decides changes with it,
and the horizon rule reaches further than before — it now governs a database
column as well as a setting.

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

**The five `OIDC_*` settings are required, and outside development a
configuration may not reach the mock's outcome by any of four routes.** All of it
in `backend/app/config.py`:

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
3. **`oidc_authorization_endpoint` may not name a loopback host outside
   development**, refused as a class: `localhost`, or any IP literal that
   `ipaddress` calls loopback — the whole of `127.0.0.0/8`, `::1`, and the
   IPv4-mapped `::ffff:127.0.0.1`.
4. **No `oidc_*` URL may be plain `http` to another host outside development**,
   with the same on-this-machine exemption `ai_provider_base_url` already has.

Rules 3 and 4 are the security review's, and each closes a route to this
ticket's own finding that never spells `mock-idp`.

**Why rule 3 is one field and not five.** The other four URLs are resolved by
this container, where a loopback host is a provider sidecar — an ordinary
deployment that reaches nothing an attacker controls. `oidc_authorization_endpoint`
is never resolved here at all: it is a string handed to a browser and resolved on
the machine that browser runs on. The same host name therefore means "this API
process" in four settings and "whoever's laptop is reading this" in the fifth.
Since the development value is `http://localhost:8081/oidc/authorize` and names
no mock, a deployment that set the other four and forgot this one started
cleanly and answered every web login with a redirect to a port on the browsing
user's own computer — where anything listening receives an institution-issued
link arriving from a Pulse URL and can render a login page of its own.

Refused as a *class* because the review's finding arrived with a fourth spelling
already in it: a catalog of `localhost`, `127.0.0.1` and `::1` is walked past by
`127.0.0.2` and by the IPv4-mapped form. A non-loopback IP literal stays
accepted — an institution reaching its provider at an address rather than a name
is an ordinary deployment.

**Why rule 4 is conditioned on the environment** when the model provider's
version of the same rule is absolute: every address on the development stack is
cleartext to *another container* (`http://mock-idp:8000`), so an unconditional
rule refuses the configuration `.env.example` ships and CI copies to `.env`, and
takes SPEC §14.3's exit criterion with it. What it buys is that
`http://idp.example.edu/…` stops being a legal production configuration: anyone
on the path can answer the key-set fetch with a key set of their own, and every
token signed with the matching private key then verifies correctly. The issuer is
included although nothing fetches it, because OpenID Connect Discovery requires
an Issuer Identifier to use `https`.

**One trailing dot is stripped from the parsed host before every comparison.**
`mock-idp.` reaches the mock and `localhost.` reaches the loopback interface, so
a catalog comparing strings is defeated by a one-character edit. Exactly one dot:
stripping more, or comparing by prefix afterwards, would turn
`mock-idp.example.edu.` into a refusal.

**The mock catalog is two spellings and nothing else** — the name a container on
this stack reaches the mock by, and the name a configuration calls it by without
addressing it. The host is compared as a parsed component, so the port, the
scheme and the path do not excuse it and `https://mock-idp.example.edu` is not
caught; the client id is compared whole.

**`localhost` and the loopback addresses are deliberately outside *that*
catalog**, which is a different question from rule 3. Inside a deployed container
`localhost` is that container, so it cannot reach the mock: reading it as the
mock would refuse a provider running alongside the application while protecting
nothing. Rule 3 refuses it on one field for an unrelated reason — where the
browser is sent — and the two must not be merged into one list.

**The three host tests are three sets, and the code keeps them apart.** The mock
catalog, the loopback *refusal* class, and the on-this-machine *exemption* answer
differently for the same host: `localhost` is not the mock, is refused on the
browser-facing field, and exempts cleartext everywhere else. Merging the refusal
class into the exemption would mean a future widening moved both — one permitting
more cleartext, the other refusing more addresses — so they are separate helpers
with the reason written at each. The rules also compose rather than
short-circuit: `http://localhost:8081/oidc/authorize` in production is exempt
from rule 4 and refused by rule 3, which is the exact configuration the review
found.

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

**Adding `localhost` to the mock catalog.** The shape this record first
considered and rejected, and the rejection stands: on the four container-resolved
settings a loopback host is a provider sidecar, so treating it as the mock
refuses a legitimate deployment while protecting nothing. What the security
review showed is that the *field* mattered and the catalog was the wrong place to
ask. Rule 3 refuses loopback on the browser-facing endpoint only, and for a
different reason — not "this might be the mock" but "this is the reader's own
machine" — which is why it is a second rule rather than a longer list.

**A single host helper serving both the refusal and the exemption.** Fewer moving
parts, and it is the obvious tidy-up a later reader will propose. Rejected
because the two sets differ today — the refusal covers the IPv4-mapped loopback
form and the exemption does not — and because they move in opposite directions of
safety: widening the exemption permits more cleartext, widening the refusal
refuses more addresses. One helper makes every future widening do both at once.

**A `RESTRICT_LOOPBACK` or `ALLOW_HTTP` escape hatch** for an operator whose
deployment needs one. Rejected: neither has a correct value other than "no"
outside development, and a knob with one correct answer is a knob that gets set
wrong once and never audited. The development environment is the escape hatch,
and it is already named in every refusal message.

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
- **A provider running beside the application is still deployable, and that is
  the shape most likely to be broken by a later tightening.** Its token endpoint
  and key set may be `https://localhost:8443/…` in production, and may be plain
  `http` there too. Only the browser-facing endpoint is closed to it — a sidecar
  still has to publish an address a browser can reach.
- **Rule 4 makes a cleartext deployment impossible except on this machine**, so
  an institution terminating TLS at a proxy in front of its provider has to name
  the proxy rather than the backend. That is the same bill
  `ai_provider_base_url` already presents, and the same answer.
- **The named deployability cost, and it is a real one: an `http` provider
  sidecar addressed by service name is refused.** `http://idp-sidecar:8000/token`
  in production fails rule 4, because a container on a bridge network is not on
  this machine — `_is_on_this_machine` answers on the host in the URL, not on
  whether the packet leaves the physical box, and a service name on a shared
  network is reachable by every other container on it. Measured, not assumed. The
  exemption above covers the same sidecar addressed as `http://localhost:8000` or
  `http://127.0.0.1:8000`, which is the shape a same-pod sidecar actually takes.
  So the operator's answer is one of two: terminate TLS at the sidecar, or address
  it by a loopback address rather than by name. This is the cost that will be
  reported as a bug, so it is written down here as a decision.
- `is_loopback` on an IPv4-mapped IPv6 address answers `True` on Python 3.13 and
  did not on every earlier version, so the loopback check unwraps `ipv4_mapped`
  itself rather than resting on that. Measured on the pinned interpreter; the
  test that would catch a regression is the `::ffff:127.0.0.1` row.
- **These four rules guard against a mistake, not against whoever writes the
  configuration**, and the distinction is worth stating because the rules read
  like an attacker boundary and are not one. Someone who can set `OIDC_ISSUER`
  can also set `ENVIRONMENT=development`, which switches all four off by design —
  and can set `DATABASE_URL`, which is the whole system. So the threat these
  close is the operator who copies the development stack forward, or who sets
  four values and forgets the fifth. That is the finding, and it is worth closing
  on its own terms.

  Read that way, the residue below is a limit rather than a hole. All of it was
  measured rather than assumed, and it divides in two.

  **Spellings that need a crafted value.** `ipaddress` rejects the legacy
  `0x7f.0.0.1` and `2130706433` forms of `127.0.0.1` that some resolvers still
  accept. And **the backslash family, which has two members and not one**:
  `urlsplit` reads `https:/\localhost:8081/…` as having no host at all, and reads
  `https://localhost\.evil.example/a` as the ordinary non-loopback host
  `localhost\.evil.example` — so all four rules pass it — while a browser
  following WHATWG turns the backslash into a slash in both, resolving `localhost`
  and treating the rest as a path. The second is the more interesting one, because
  nothing about it looks malformed to this process. Neither is a mistake anybody
  makes, and against someone willing to write one `ENVIRONMENT=development` is the
  easier door, so a second URL parser fighting the first would buy nothing.

  **Spellings a mistaken operator could plausibly write**, which is the same
  threat rule 3 exists for, and this is the honest cost of a class defined by
  `ipaddress`: `https://0.0.0.0:8081/…` — the bind address, which several browsers
  resolve to the local machine — and `https://127.1:8081/…`, a shortened dotted
  quad that `inet_aton` expands to `127.0.0.1`. Both are accepted today, because
  `ipaddress` calls the first not-loopback and refuses to parse the second at all.
  They are recorded as accepted residue rather than repaired here: closing them
  means modelling what a resolver accepts rather than what a library parses, and
  that is a wider decision than this record should make on its own. A later
  tightening is a reviewed change with its own pairs, not a quiet widening of the
  class.
- **A malformed URL is refused, by accident of the same code path.** `urlsplit`
  raises `ValueError` on a bracketed host it cannot parse (`https://[::1].:8081`),
  pydantic turns that into the ordinary field error, and the operator gets the
  usual refusal naming the field with no value in it. Only outside development,
  because that is where these validators run at all; a malformed value in
  development still fails at first use, as it did before this record.
- Tests whose subject is something else and which build a non-development
  `Settings` now have to name a non-mock provider. `tests/conftest.py` gained one
  fixture for it rather than each module inventing placeholders.
- ADR 0075's remaining two fields keep their defaults on an argument that is now
  narrower and true: neither `PUBLIC_BASE_URL` nor
  `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` names a service the base Compose file
  starts. **Of those two, only `PUBLIC_BASE_URL` is still a setting**: E1-05
  moved the LTI platform's authorization endpoint onto the registration and
  deleted the field, so this sentence now covers one value rather than two.
- **The four host helpers this record introduced have a second caller as of
  E1-05.** `app.models.lti` imports `_url_host`, `_is_on_this_machine`,
  `_is_a_loopback_host` and `_is_a_deployment` rather than re-deriving the
  one-trailing-dot strip or the IPv4-mapped unwrap, which is
  `docs/MISTAKES.md` entry 13's rule applied at the second place facing the same
  question. What E1-05 does **not** inherit is this record's conclusions:
  [ADR 0081](0081-a-registrations-addresses-are-refused-at-one-write-time-chokepoint.md)
  re-derives them for database columns written through a console, adds a
  link-local rule these settings do not carry, and says where the two records
  differ and why.
