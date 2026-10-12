"""The role switcher's wire contracts — E9-04.

Three shapes: the views a session may switch to, the switch request, and the new
session a switch answers with. A view is named on the wire by its `LandingRole`
member name, lowercased, which is also its route segment under `/app/`
(`app.services.session.fragment_redirect`), so the SPA can navigate to the name
it was given.

**The names are a closed `Literal`**, so a request naming anything else is
FastAPI's 422 before a handler runs, and the generated frontend types carry the
same five names. The `Literal` is a second spelling of `LandingRole`'s members,
so the module refuses to import if the two ever differ.
"""

from typing import Literal, cast, get_args

from pydantic import BaseModel, ConfigDict

from app.services.authz import LandingRole

__all__ = [
    "LandingName",
    "SessionLandings",
    "SessionSwitch",
    "SessionSwitched",
    "landing_name",
    "landing_role",
]

LandingName = Literal["student", "instructor", "leadership", "care", "admin"]

if set(get_args(LandingName)) != {role.name.lower() for role in LandingRole}:
    raise RuntimeError(
        "`LandingName` no longer names exactly the `LandingRole` members, lowercased. "
        "Change both together."
    )


def landing_name(role: LandingRole) -> LandingName:
    """The wire name of one view: its member name, lowercased."""
    return cast(LandingName, role.name.lower())


def landing_role(name: LandingName) -> LandingRole:
    """The view one wire name names."""
    return LandingRole[name.upper()]


class SessionLandings(BaseModel):
    """`GET /session/landings`: the session's own view, and every view held at its door.

    `landings` is in `LANDING_PRECEDENCE` order with the student view last, and
    includes `current`.
    """

    model_config = ConfigDict(extra="forbid")

    current: LandingName
    landings: list[LandingName]


class SessionSwitch(BaseModel):
    """`POST /session/switch`: the one view to switch to."""

    model_config = ConfigDict(extra="forbid")

    role: LandingName


class SessionSwitched(BaseModel):
    """What a switch answers with: the role of the new session, and the session itself.

    The token is also set as the session cookie, beside a fresh CSRF token. It is
    in the body for the SPA's Bearer carrier, which is how the session travels
    inside the LMS's iframe (ADR 0089).
    """

    model_config = ConfigDict(extra="forbid")

    role: LandingName
    session: str
