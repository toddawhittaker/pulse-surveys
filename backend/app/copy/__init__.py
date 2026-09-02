"""The words this product says to a person, in one discoverable place — E2-09.

SPEC §4.1 items 4 and 5 are rules about *vocabulary*: aggregate language counts
sections rather than instructors and never ranks; confidentiality copy appears
exactly once per surface, in plain words. Both are checked over an inventory of
the strings this product actually ships, and a string spelled inside a handler is
a string that inventory cannot see. So a user-facing string lives here, and the
module it lives in is found by walking this package.

**Two names and nothing else.** `CopyEntry` is what an entry is — a key and the
text under it — and `copy_modules()` is how every entry is found. There is
deliberately **no central list** of entries: a list is a second place to register
a string, and the string that matters is always the one somebody forgot to add to
it. A module dropped into this package is inventoried the moment it is written.

**The key is a name, not a sentence.** `student.not_a_student` says which surface
and which event; what it *says* to a person is `text`, and the two are separated
so that rewording a refusal is one edit here rather than an edit in a router. Keys
are dotted and grouped by surface, so an inventory can be read by surface.

**Frozen.** Copy is read at import time by whatever renders it and by whatever
audits it, and an entry a caller could mutate is an entry that says one thing to
the reader and another to the audit.
"""

import pkgutil
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType

__all__ = ["CopyEntry", "copy_modules"]


@dataclass(frozen=True)
class CopyEntry:
    """One user-facing string, under the name the product refers to it by.

    `key` is the stable name — `<surface>.<event>` — and `text` is what a person
    reads. Nothing else: a description, a surface, or a "shown where" field would
    each be a fact about the string that has to be kept true, and the inventory
    that reads these entries is looking for the words.
    """

    key: str
    text: str


def copy_modules() -> tuple[ModuleType, ...]:
    """Every module in this package, imported, in a stable order.

    **Discovery rather than registration**, which is the whole design: an
    inventory built from a hand-kept list is short by exactly the module somebody
    forgot to add, and the copy rules of SPEC §4.1 are worth nothing over an
    inventory that quietly misses a surface. A module filed here is found.

    Sorted by name so the order is the same on every machine and in every run —
    `pkgutil.iter_modules` answers in directory order, which is not one.
    """
    return tuple(
        import_module(f"{__name__}.{found.name}")
        for found in sorted(pkgutil.iter_modules(__path__), key=lambda found: found.name)
    )
