"""The mock provider's HTTP surface, and the reason it reads no environment.

Four routes and two names. Written here rather than beside the handlers so that a
reader can see the whole surface of this service in one place, exactly as
`mock-idp/app/config.py` does for the identity provider.

**There is no configuration.** The other two mocks each hold a `Settings`-shaped
dataclass because each has addresses to hold — an issuer, a client id, where to
send a browser — and every one of those has a deployment-specific answer. This
service has none. What it would otherwise take from the environment is the
classification vocabulary, and every part of that has exactly one correct value:
the character threshold is SPEC §3.3's, the marker line is the one
`backend/app/ai/prompts/validity.v1.md` ends with, and the stall has to outlast a
timeout that is itself not a knob (`app.ai.tasks.VALIDITY_TIMEOUT_SECONDS`).
`CLAUDE.md`: no configuration knob for something that has one correct answer. So
`app.rules` states them as constants and `GET /mock/rules` publishes them, and
this module reads `os.environ` nowhere.

That is also why `docker-compose.yml` gives this service no `environment:` block
and why it earns no `.env.example` entry. ADR 0037 settled the entry question for
the platform — an entry there is earned by an `app.config.Settings` field or by a
Compose interpolation, and neither is true here — and ADR 0058 recorded E0-16
reaching the same answer. This is the same answer once more, reached with nothing
to configure at all.
"""

# What this service calls itself in its own health response and its model
# listing. The Compose service name it runs as is the same string, and
# `tests/unit/test_mock_ai_service.py` is what holds the two together against the
# Compose file rather than trusting either.
SERVICE_NAME = "mock-ai"

SUMMARY = "A development-only OpenAI-compatible endpoint for the §7.4 tasks (SPEC §9.2)."

# The model this endpoint says it serves, echoed back when a request asks for
# something else. `.env.example` documents
# `MOCK_AI_PROVIDER_MODEL_NAME=mock-validity-v1` — spelled `AI_MODEL_NAME` until
# the configuration split of E2-12, which gave the real provider and this mock a
# triple each (ADR 0118) — and that is the value a development stack actually
# sends. This is the fallback for a client that names no model, and it is the
# same string so that a reader meeting either one recognises it.
#
# **A real-looking name on purpose.** `app.ai.gateway` records the model an
# answer reports as half of every classification's audit pair (ADR 0031) and
# refuses a provider that claims `no-model`, ADR 0054's fail-open marker — so a
# name that read as "nothing answered" would either be refused or, worse, make a
# real answer indistinguishable from a floored one.
DEFAULT_MODEL_NAME = "mock-validity-v1"

# The OpenAI-compatible surface the gateway drives (ADR 0053). Two routes: the
# completion, and the model listing a client library may probe before it asks
# anything else.
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"

# Liveness, for the health check `docker-compose.yml` declares and
# `scripts/ci/wait_for_health.sh` watches.
HEALTH_PATH = "/healthz"

# The mock's own published statement of its rules, under the `/mock/` prefix ADR
# 0047 established for a route no real provider serves. E2-07's third acceptance
# criterion puts the rules here so that a test aiming at one reads the mock's
# statement of it rather than holding a second copy.
RULES_PATH = "/mock/rules"
