"""What the role switch says to a person when it does not switch — E9-04.

One string: the refusal `POST /session/switch` answers when the role asked for is
not one the person holds at the door their session came through, or was held
and has since been taken away. It lives in the `landing` surface, beside the
landing views' own words in `frontend/src/copy/landings.ts` (the E9 breakdown's
decision 15), so SPEC §4.1 items 4 and 5 are checked over it.

**One sentence for every reason**, because the person's next step is the same
in each, and a refusal that named which role exists where would describe the
person's assignments to whoever holds the session. It says the current view is
unchanged, which is true: a refused switch issues nothing and ends nothing.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY", "SWITCH_REFUSED"]

SWITCH_REFUSED = CopyEntry(
    key="landing.switch_refused",
    text=(
        "That view is not open to you with the way you signed in, or it is no longer yours. "
        "Your current view is unchanged."
    ),
)

COPY: Mapping[str, CopyEntry] = {entry.key: entry for entry in (SWITCH_REFUSED,)}
