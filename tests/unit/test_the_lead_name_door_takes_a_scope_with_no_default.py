"""`section_lead_name` takes the reader's scope as a required keyword — E9-14 item 4.

The E9 boundary privacy review: `app.services.response_loop.section_lead_name`
defaults `scope` to `None`, so a leadership caller that forgets it reads the
lead's name with no purview check, and nothing at the call site shows the
omission. `section_staff_names`, the door it is built on, already takes `scope`
as a required keyword (E9-03's fix round), which is what lets E9-12's C3 sweep
hold its callers. The settled interface (E9-14): `section_lead_name(..., scope:
ActorScope | None)`, keyword-only, with no default. A student's or an
instructor's own page still writes `scope=None`; it now has to say so.

The call sites are held by the sweep in
`tests/unit/test_every_leadership_caller_of_the_staff_name_door_passes_a_scope.py`,
extended by this ticket to this door. This module pins the signature, which is
what makes "every call writes `scope=`" true at run time as well as in the
syntax tree.

**Marked `invariant`. Which failure a red is, before E9-14 lands:** the
parameter has a default of `None`, so the test FAILS on that assertion.
"""

import inspect
from importlib import import_module

import pytest

pytestmark = pytest.mark.invariant

SERVICE_MODULE = "app.services.response_loop"
THE_DOOR = "section_lead_name"
THE_READER = "scope"


def test_the_lead_name_door_takes_the_scope_as_a_keyword_with_no_default() -> None:
    """`scope` is keyword-only and required.

    **The mutation it kills:** `scope: ActorScope | None = None` (today's
    signature), which lets a leadership caller omit the reader and read a
    lead's name for a section outside their purview; `scope` made positional,
    which a sweep reading `scope=` cannot see. **The near miss it spares:** a
    `scope` typed to accept `None` — the instructor's and the student's pages
    pass `None` deliberately.
    """
    module = import_module(SERVICE_MODULE)
    door = getattr(module, THE_DOOR, None)
    assert callable(door), f"`{SERVICE_MODULE}` has no callable `{THE_DOOR}`."
    parameters = inspect.signature(door).parameters
    assert THE_READER in parameters, (
        f"`{THE_DOOR}{inspect.signature(door)}` takes no `{THE_READER}`; E9-09 added one and "
        "E9-14 makes it required."
    )
    parameter = parameters[THE_READER]
    assert (
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
    ), f"`{THE_READER}` is {parameter.kind.description}; settled: keyword-only."
    assert parameter.default is inspect.Parameter.empty, (
        f"`{THE_READER}` defaults to {parameter.default!r}. Settled (E9-14): a required keyword "
        "with no default, so no caller reads a lead's name without saying whose purview it is."
    )
