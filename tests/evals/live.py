"""Building the live classifier the eval run measures — E2-12.

**This is the only code in the repository that deliberately builds a gateway
pointed at a paid provider.** Every other test run in this project reaches the
loopback stub (`tests/integration/test_ai_gateway_validity_roundtrip.py`) or
E2-07's `mock-ai` service, and neither costs anything or leaves the machine.

**`live=True`, always.** The construction flag settles which of the two
documented provider triples a gateway reads: `live=True` takes `AI_PROVIDER_*` in
every environment, while `live=False` takes `MOCK_AI_PROVIDER_*` in development
and test. An eval run against the mock would measure a character count wearing a
model's clothes and report it as SPEC §9.3's floor, so the flag is passed here
rather than inferred from the environment the runner happens to start in. That
each flag reaches the triple it claims to is asserted in
`tests/unit/test_the_gateway_reads_the_provider_triple_the_flag_selects.py`.

**The task takes the gateway, and that is what makes this module short.**
`app.ai.tasks.verdict_for_comment(comment, gateway=...)` accepts a supplied
gateway, writes no row and needs no session — so the eval job installs the
backend, starts no database, and calls it directly. An earlier draft of this file
discovered the callable by name and bound its parameters, on the assumption that
neither the name nor the signature was settled; both are, so the import is
direct and the refusal that used to name an unfillable `session` parameter is
gone with the assumption behind it.

The direct import is also what gives SPEC §9.3's "breaks its evals at type-check
time" something to break: `verdict_for_comment` and `CommentValidityOutput` are
imported names, so a rename of either stops this module type-checking instead of
stopping a live eval run a fortnight later.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from app.ai.contracts import CommentValidityOutput
from app.ai.tasks import verdict_for_comment
from tests.evals.declarations import EvalRefusalError

# SPEC §13 places the module: "`ai/gateway.py` — provider-agnostic client
# (OpenAI-compatible base_url)".
GATEWAY_MODULE = "app.ai.gateway"

# The gateway class SPEC §7.4 names in prose: "All model calls go through one
# internal `AIGateway`".
GATEWAY_CLASS = "AIGateway"

# The construction flag that decides which provider triple is read.
LIVE_FLAG = "live"


def build_live_gateway() -> object:
    """One `AIGateway` constructed with `live=True`.

    Reached through the module object rather than through a `from ... import`
    bound at import time, so that a test can substitute the class and read what
    this passed it. Which flag reaches the constructor is the whole of what makes
    an eval run a live run, and a constructed gateway carries no evidence of it.
    """
    module = importlib.import_module(GATEWAY_MODULE)

    gateway_class = getattr(module, GATEWAY_CLASS, None)
    if gateway_class is None:
        raise EvalRefusalError(
            f"`{GATEWAY_MODULE}` exposes no `{GATEWAY_CLASS}`. SPEC §7.4: 'All model calls "
            f"go through one internal `{GATEWAY_CLASS}`'."
        )

    try:
        return gateway_class(**{LIVE_FLAG: True})
    except TypeError as failure:
        raise EvalRefusalError(
            f"`{GATEWAY_CLASS}` does not accept a `{LIVE_FLAG}` construction flag "
            f"({failure}). The eval runner is the one caller that must always reach the "
            "real provider, and `live=False` reads the mock triple in development and "
            "test — so a run built without the flag would measure SPEC §9.3's floor "
            "against a service that is not a model."
        ) from failure


def build_validity_classifier() -> Callable[[str], CommentValidityOutput]:
    """A callable answering one comment through a gateway built `live=True`."""
    gateway = build_live_gateway()

    def classify(comment: str) -> CommentValidityOutput:
        return verdict_for_comment(comment, gateway=gateway)

    return classify
