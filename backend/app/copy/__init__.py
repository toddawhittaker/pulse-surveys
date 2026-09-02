"""Every sentence this backend shows a person, in one place a guard can enumerate.

SPEC §4.1 items 4 and 5 are rules about *words* — what a surface may say about a
student, and where the confidentiality line appears — and E2-11 ships an inventory
that reads them. An inventory can only read strings it can find, so this package is
the one place a user-facing string lives: a route serves copy by key lookup and
never as an inline sentence, and a refusal whose words are written at its raise
site is a refusal the inventory cannot see.

**Two things live here and nothing else.** `CopyEntry`, which is what one string
is, and `copy_modules()`, which is how the package's contents are found. Each
surface adds one module beside this one defining `COPY: Mapping[str, CopyEntry]`
keyed by dotted keys. E2-08 adds `submit.py`, E2-09 adds `student_read.py`, and
E2-10 adds its own.

**The key is a name, not a sentence.** `student.not_a_student` says which surface
and which event; what it *says* to a person is `text`, and the two are separated
so that rewording a refusal is one edit here rather than an edit in a router. Keys
are dotted and grouped by surface, so an inventory can be read by surface.

**There is deliberately no central list of the modules.** `copy_modules()`
enumerates the package directory, so the inventory's reach cannot be shrunk by an
edit to the thing it inventories — a hand-written tuple is a list a surface can be
dropped from, and the dropped surface then ships with nothing counting its words
(`docs/MISTAKES.md` entry 35). The enumeration is the whole reason the registry is
a package rather than a module.

**Nothing here reads configuration, opens a connection or imports an application
module.** A copy module is constants; one that needed `Settings` to state a
sentence would be a defect, and it would make this package unimportable from
`migrations/env.py`'s environment the way `app.models.ai` warns about.
"""

import pkgutil
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType

__all__ = ["CopyEntry", "copy_modules"]


@dataclass(frozen=True, slots=True)
class CopyEntry:
    """One user-facing string, and the key it is served and inventoried by.

    `key` is the stable name — `<surface>.<event>` — and `text` is what a person
    reads.

    Frozen, because the inventory reads the registry at one moment and the
    application serves it at another: an entry that can be rewritten after import
    is an entry those two can disagree about.

    Two fields and no third. A rule carried on a copy entry — a severity, an
    audience, a flag saying "this one is exempt" — is a rule living where the
    inventory does not look, and the inventory is the whole point of the shape.
    """

    key: str
    text: str


def copy_modules() -> tuple[ModuleType, ...]:
    """Every copy module in this package, found rather than listed, in a stable order.

    The directory is the inventory. `pkgutil.iter_modules` walks this package's
    own `__path__`, so a module added beside `submit.py` is enumerated by existing
    and a module deleted stops being enumerated by not existing — neither needs
    anybody to remember a list.

    Sorted by name so the order is the same on every machine and in every run —
    `pkgutil.iter_modules` answers in directory order, which is not one.
    """
    return tuple(
        import_module(f"{__name__}.{found.name}")
        for found in sorted(pkgutil.iter_modules(__path__), key=lambda found: found.name)
    )
