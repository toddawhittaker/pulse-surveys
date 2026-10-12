"""The sentences the leadership roll-ups serve — E9-05, the `leadership_rollup` surface.

E9's README decision 15 registers this surface, and E9-07 and E9-11 file their
strings under the same prefix. It owes no confidentiality line: roll-ups show
figures over sections, attention cards and staff names, never a comment, a
summary or a single response (ruling 2), and the drill-down reuses the
instructor report's surface and its line.

The named-set series route serves one sentence: the refusal for a term that is
not there. The line's legend and its withheld notice are drawn by E9-11 in the
frontend's copy module under this prefix, because the API serves no words for
them.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "COPY",
    "TERM_UNAVAILABLE",
]

# The 404 for a `term_id` no term carries. Term existence is no secret, so the
# sentence says only that there is nothing here to read.
TERM_UNAVAILABLE = CopyEntry(
    key="leadership_rollup.term_unavailable",
    text="There is no term here.",
)

COPY: Mapping[str, CopyEntry] = {entry.key: entry for entry in (TERM_UNAVAILABLE,)}
