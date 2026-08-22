# E0-39 — The default configuration trusts the mock IdP (Batch I)

**ID:** E0-39
**Branch:** `e0/mock-idp-default-trust`
**Depends on:** E0-16, E0-18 (both merged)

## The finding (epic-boundary threat model, 2026-08-22, MEDIUM)

The base Compose file starts `mock-idp` in every deployment, and the
application's own defaults name it as the trusted issuer, token endpoint, key
set, and client id: `backend/app/config.py` defaults `oidc_issuer` to
`http://mock-idp:8000`, `oidc_token_endpoint` and `oidc_jwks_url` to addresses
on the same service, and `oidc_client_id` to `mock-idp-client`. An operator who
deploys per §7.2 and does not set those variables has deployed a signing oracle
for fake CARE and ADMIN identities that Pulse verifies correctly and trusts.
The only thing blocking the flow in a base-only deployment is a coincidental
redirect-URI disagreement between two files, and the override file removes it.

The mock LMS has a second gate for exactly this: ADR 0038's fourth property is
backed by `seed_mock_platform`'s environment check at the registration row.
The mock IdP's trust is configuration only, and ADR 0075 made the
configuration trust it by default. Three records assert the opposite and are
false at HEAD: `.env.example` ("None of them can resolve in a deployment"),
ADR 0075's Decision section, and the mock-idp comment in `docker-compose.yml`.

## The decision, settled

Two layers, both landing in this ticket:

1. **The five `oidc_*` settings lose their defaults and become required**:
   `oidc_issuer`, `oidc_authorization_endpoint`, `oidc_token_endpoint`,
   `oidc_jwks_url`, `oidc_client_id` in `backend/app/config.py`. A deployment
   that supplies no identity provider fails at startup with a
   `ConfigurationError` naming the missing field, exactly as the existing
   required group does. The development values move to where every other
   deployment-specific value lives: `docker-compose.yml`'s api-service
   environment (visible to the ADR 0076 closed-set test) and `.env.example`
   (names plus the dev-stack values, which are addresses, not credentials).
   Every service that constructs `Settings` must still start — if worker or
   beat construct it, they get the same variables the same way api does.

2. **A mock address is refused outside development.** A `Settings` validator:
   when `environment` is not the development environment, any `oidc_*` URL
   whose host is `mock-idp` is refused, and `oidc_client_id ==
   "mock-idp-client"` is refused, with `ConfigurationError`. The refusal names
   the field, never echoes a value beyond the offending host. The catalog is
   the Compose service name and the mock's registered client id — the two
   spellings by which this process can reach or name the mock; document in the
   ADR why `localhost` variants are not in the set (inside a deployed
   container they cannot resolve to the mock).

`lti_platform_authorization_endpoint` is out of scope — its removal is E1's,
recorded in `docs/tickets/e1/carried-from-e0.md`.

## Scope

1. `backend/app/config.py`: the five fields required; the validator; both per
   the decision above.
2. `docker-compose.yml`: the five variables on the api, worker, and beat
   services (`Settings` is constructed identically in all three — ADR 0042),
   in the interpolated form `${OIDC_ISSUER:-http://mock-idp:8000}` so a
   deployment's `.env` still wins and only the un-set case falls back to the
   dev value — where the layer-2 refusal then catches it outside
   development. A plain `environment:` literal would beat `env_file:` and
   make the base file undeployable; that is why the interpolated form is the
   decision, not a style choice. The mock-idp service comment corrected: it
   is trusted wherever configuration names it, and the configuration now
   refuses to name it outside development.
3. `.env.example`: the five entries already exist (lines ~209–218) under the
   "Defaulted — optional" heading. Move them to the required section — do
   not duplicate them — and replace the false "None of them can resolve in a
   deployment" sentence (line ~183) with what is now true.
4. **ADR 0077** (number reserved): supersedes ADR 0075 **in part** — the
   defaulted-address decision is reversed for the web door; keep 0075's
   rejected-alternatives reasoning visible as the price paid, per the
   ADR-reversal convention. Amend ADR 0075's body with a pointer line to 0077.
   Do **not** edit `docs/adr/README.md` — E0-42 owns the index and adds 0077's
   row.
5. **Repair round (test-author, partitioned before implementation per the
   MISTAKES entry 22 pattern):** the new rule reddens merged test modules
   whose fixtures construct non-development `Settings` against the mock's
   addresses or client id — `tests/integration/test_web_login_door.py`,
   `test_lti_launch_door.py`, `test_demo_seed_script.py`,
   `tests/unit/test_docs_exposure.py`, `test_dev_console_exposure.py`,
   `test_care_engine_configuration.py`, `test_db_engine_configuration.py`,
   `tests/unit/test_healthz.py` (its environment-echo test builds under a
   deliberately non-development environment — same collision, found and
   repaired in the round, ratified 2026-08-22), and `tests/conftest.py` if
   the fixture is shared. `test_demo_seed_script.py` was examined and needs
   nothing: the seed deliberately builds no `Settings`. The repair: where a
   test's subject is something other than the OIDC refusal (a cookie flag, a
   404, an engine rule, the seed's own refusal), its non-development
   configuration uses non-mock placeholder values
   (`https://idp.example.edu/...`, client id `example-client`) so the guard
   under test is the one that fires. No test's assertion weakens; only
   fixture configuration moves. Known safe overlap: E0-41 adds one-line
   markers to `test_docs_exposure.py` and `test_dev_console_exposure.py` in
   a sibling worktree — different hunks, semantically independent; the
   second PR to merge re-runs CI over the combination.
6. Tests (test-author): startup refusal and acceptance **in pairs** —
   development + mock values accepted; non-development + mock issuer refused;
   non-development + mock client id refused; non-development + non-mock values
   accepted; missing field refused in any environment. Compose coverage: the
   five keys present on the api service in the merged configuration. Existing
   `tests/unit/test_compose_stack.py` and `tests/unit/test_env_example_resolves.py`
   updated only as far as the new variables require.

## Acceptance

- `Settings()` with no `oidc_*` values raises; the dev stack (`docker compose
  config` merged) supplies all five and comes up.
- The refusal pairs above are green, each docstring naming its mutation.
- The three false records are corrected in the same PR.
- Full suite green; `alembic check` untouched (no schema change).

## File ownership (parallel-build boundary — do not cross)

This ticket may touch only: `backend/app/config.py`, `docker-compose.yml`,
`docker-compose.override.yml` (only if the merged config requires it),
`.env.example`, `docs/adr/0075-*.md`, new `docs/adr/0077-*.md`, this ticket
file, and under `tests/` only `tests/unit/test_compose_stack.py`,
`tests/unit/test_env_example_resolves.py`, a **new**
`tests/unit/test_oidc_provider_configuration.py`, and — for the scope-item-5
repair round only, fixture configuration never assertions — the modules that
item names plus `tests/conftest.py`. Never `docs/adr/README.md`,
never `docs/tickets/e0/README.md`, never CI files, never any other test file —
sibling tickets own those in parallel worktrees.
