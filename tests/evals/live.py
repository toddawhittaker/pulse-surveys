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

**It calls the gateway, not the submit path's task, and dispute E2-12-06 is
why.** An earlier draft went through `app.ai.tasks.verdict_for_comment`, which
takes a supplied gateway, writes no row and needs no session — everything an eval
run wants, plus one thing it must not have. That function is §3.3's submit path,
and §3.3 says "on provider timeout, the heuristic floor applies and the
submission is accepted" — so a merely slow answer is replaced by a
twenty-five-character count and stamped with `character-floor` as its prompt
version.

Two full runs over the 98-case set were voided that way, at two and then five
floored cases; both were slow answers rather than outages, and both answered when
the same calls were made again at a longer timeout. The bias is what makes it
unsound rather than lossy: the floor answers on the character rule, and this set
is built out of the cases that rule gets wrong, so a floored case is scored as
the heuristic's error reported as the model's — worst in the two families that
carry the whole point of the set.

**So the timeout is a measurement's and not a student's.** `EVAL_TIMEOUT_SECONDS`
is sixty seconds against §3.3's four, and `VALIDITY_TIMEOUT_SECONDS` does not
move: nobody is waiting on this call, and a real outage now raises out of the
gateway and fails the run loudly naming the provider, which is what E2-12's scope
asks for.

**The prompt-version pin in `tests/evals/runner.py` stays exactly as it is.** It
is what turned a silently wrong measurement into a refusal, twice; without it
both of those runs would have produced plausible numbers.

`render_prompt`, `VALIDITY_PROMPT_VERSION` and `CommentValidityOutput` are
imported names, so a rename of any of them stops this module type-checking rather
than stopping a live eval run a fortnight later — which is what SPEC §9.3's
"breaks its evals at type-check time" means here.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from app.ai.contracts import CommentValidityOutput
from app.ai.tasks import VALIDITY_PROMPT_VERSION, render_prompt
from tests.evals.declarations import EvalRefusalError

if TYPE_CHECKING:
    # For the annotations below and for nothing else. `AIGateway` is imported
    # under `TYPE_CHECKING` rather than plainly so that this module binds no
    # reference to the class at run time: `build_live_gateway` reaches it through
    # the module object on purpose, and a second binding here would read as
    # defeating that. `TaskUsage` rides the same import because it is what
    # `run_task_with_usage` returns and it lives beside the class that returns it.
    from app.ai.gateway import AIGateway, TaskUsage

# SPEC §13 places the module: "`ai/gateway.py` — provider-agnostic client
# (OpenAI-compatible base_url)".
GATEWAY_MODULE = "app.ai.gateway"

# The gateway class SPEC §7.4 names in prose: "All model calls go through one
# internal `AIGateway`".
GATEWAY_CLASS = "AIGateway"

# The construction flag that decides which provider triple is read.
LIVE_FLAG = "live"

# **Not §3.3's 4.0 seconds, and the difference is the whole of dispute E2-12-06.**
# That budget is a student's: it exists so a submission is never held on a slow
# provider, and when it expires the submit path accepts the answer and falls back
# to the twenty-five-character rule (SPEC §3.3, "fail open, never block a student
# on an outage"). Nobody is waiting on an eval call, and this set is built out of
# the cases that character rule gets wrong — so a floored case here is the
# heuristic's error scored as the model's, in exactly the families the set exists
# to measure. Two full runs were voided that way.
#
# Sixty seconds is chosen to be far past the provider's tail rather than close to
# it: the median observed is around two seconds and the tail reaches past five, so
# a limit anywhere near the budget would go on selecting the slow answers out. A
# real outage still raises out of the gateway and fails the run, which is what a
# measurement should do with a provider it could not reach.
EVAL_TIMEOUT_SECONDS = 60.0


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


def build_validity_classifier() -> Callable[[str], tuple[CommentValidityOutput, TaskUsage]]:
    """A callable answering one comment through a gateway built `live=True`.

    **It answers with what the call cost as well as what it decided.**
    `run_task_with_usage` takes the same arguments as `run_task`, fails the same
    ways and raises the same exceptions, and hands back the validated output
    beside the run's `TaskUsage`. The runner sums those across the set so the
    report says what the run spent — which is what turns the README's cost
    expectations from an estimate into a measurement.

    **The `cast` is the price of the substitution above, and it is deliberate**
    (dispute E2-12-04). `build_live_gateway` returns `object` because it reaches
    the class through the module object so that a test can put a recorder there,
    and a recorder is not an `AIGateway` — so an `isinstance` narrowing would
    refuse exactly the double
    `tests/unit/test_the_eval_runner_builds_a_live_gateway.py` installs to see
    which flag was passed. The cast asserts what is true of every run that is not
    that test, and it leaves the call below checked: the prompt, the version, the
    output model and the timeout all have to line up with what the gateway
    declares, which is where SPEC §9.3's "breaks at type-check time" bites for
    this module.
    """
    gateway = cast("AIGateway", build_live_gateway())

    def classify(comment: str) -> tuple[CommentValidityOutput, TaskUsage]:
        return gateway.run_task_with_usage(
            prompt=render_prompt(VALIDITY_PROMPT_VERSION, comment),
            prompt_version=VALIDITY_PROMPT_VERSION,
            output_model=CommentValidityOutput,
            timeout=EVAL_TIMEOUT_SECONDS,
        )

    return classify
