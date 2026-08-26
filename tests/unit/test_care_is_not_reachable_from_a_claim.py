"""No claim-to-role mapping may produce a Care assignment — ticket E0-09, criterion 10.

E0-09: "**Care is Pulse-owned and assigned only here.** No LTI claim, no OIDC
claim, and no LMS role may ever produce a `CARE` assignment. The launch or login
establishes who someone is; this table establishes what they may do… a
claim-to-Care mapping would let an LMS administrator grant themselves identity
access, walking past every guarantee in §4. Add a test asserting no claim-mapping
code path can write a `CARE` assignment."

Care is the only role that can re-identify a student (§4, §6.2). Every other
escalation in this product costs an attacker somebody else's data; this one costs
them a name attached to a comment about self-harm. It is marked `invariant`, so
CI runs it in a pass of its own and treats a skip as a failure.

**What this test is today, said plainly.** It is armed. When it was written no
claim-mapping code existed and the sweep was vacuous; E0-18's two doors landed
it — several modules read a claim, several name the role, and one does both and
is the exception below. The canary still carries weight for the same reason it
always did: the sweep is required to find the Care role somewhere in the source
before it is allowed to report anything about which paths name it, because a
search that has gone blind reads exactly like a search that found nothing wrong
(`docs/MISTAKES.md` entry 3).

**Why the syntax tree rather than the file text.** A correct implementation is
very likely to *say* "CARE" in a comment or a docstring in exactly the module
this sweeps — "no claim maps to CARE" is the sentence a careful implementer
writes next to the mapping. Searching the text would turn that sentence into a
failure and teach the next person to delete the comment. So both halves are read
out of the parsed module: comments are not in a syntax tree at all, and a
docstring is a string constant that is not the bare word.

**One module is a named exception, and the exception set is an equality.**
`EXCEPTIONS` below carries the modules this sweep flags on purpose, each with the
reason it is allowed to, and the assertion is that the flagged set *equals* the
exception set. So an exception that has gone stale — the module deleted, or
rewritten so that it no longer reads a claim — fails exactly as loudly as a new
unexcepted claim-reader naming the role. A list of things to ignore that nobody
has to keep true is how a sweep quietly stops sweeping.

**What it cannot see** (`docs/MISTAKES.md` entry 14, which is about not
overclaiming a search): a mapping that reaches the role through a variable, a
lookup table loaded from configuration, or a database row. This is a tripwire on
the obvious way to write the wrong thing, not a proof that the wrong thing is
unwritable. The proof-shaped assertions are in
`tests/integration/test_role_assignment_graph.py`: a Care assignment scoped to
anything a launch context could name is refused by the database, and Care is not
reachable through the supervision graph in either direction.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# The role's spelling. E0-09 writes it in backticks — "no code path… can produce
# a `CARE` assignment" — and SPEC §2.1's canonical chain spells its neighbours
# the same way, so this is the ticket's choice rather than this file's. The
# canary asserts it appears somewhere, which is also what makes a wrong spelling
# here fail loudly rather than quietly.
CARE_ROLE = "CARE"

# What makes a module a claim-mapping path. Read off the syntax tree: an
# identifier that names a claim, or a string constant carrying one of the LTI or
# OIDC vocabularies a role arrives in. **This file's choice** of list, and it is
# meant to be widened by whichever ticket adds a door the list does not describe.
CLAIM_IDENTIFIER_FRAGMENTS = ("claim", "id_token", "userinfo", "lms_role", "launch_role")
CLAIM_STRING_FRAGMENTS = (
    "purl.imsglobal.org",
    "/claim/",
    "membership#",
    "lis/v2/",
    "openid",
)

# The modules this sweep flags **on purpose**, each with the reason it is allowed
# to, keyed by path relative to the repository root. The assertion below is an
# equality against these keys: adding one is a decision somebody has to write down
# here, and leaving a stale one is a failure rather than a silence.
EXCEPTIONS = {
    "backend/app/services/landing.py": (
        "E0-18's landing seam: it maps a verified web-login roles claim to which "
        "empty view the person is sent to. Navigation, not capability — the "
        "criterion this file enforces is that no claim may *produce a Care "
        "assignment*, and this module writes no `role_assignment` row and grants "
        "nothing. That is asserted behaviourally, not argued: "
        "`tests/integration/test_web_login_door.py::"
        "test_the_web_door_writes_no_row_for_the_care_person_it_lands` drives the "
        "whole flow as the Care person and requires the row counts to be "
        "unchanged. The Care queue itself is E10's, and every read on it is gated "
        "on a live `CARE` assignment in the database through the authz chokepoint "
        "(E0-11, `app/services/authz.py`) — never on a claim. **What a forged or "
        "administrator-granted claim buys is a route, and nothing behind it.** "
        "Since E1-09 it buys more than it did: a session token naming the Care "
        "role and a redirect to `/app/care`, because both doors issue a session "
        "now rather than render an empty page. That changes what the claim is "
        "worth only if something answers with data on the strength of the role in "
        "that session, and nothing may — every read is authorized out of "
        "`role_assignment` at the chokepoint, which no claim reaches. The "
        "guarantee is the chokepoint, not the emptiness of a page. The "
        "claim that buys the route can also only arrive at the door SPEC §2 gives "
        "Care: "
        "`tests/integration/test_lti_launch_door.py::"
        "test_a_launch_naming_a_web_door_role_and_no_lis_role_is_refused` and "
        "`::test_a_launch_carrying_both_vocabularies_lands_on_the_view_its_lis_"
        "role_names` require the launch door to refuse a launch stating `CARE` in "
        "the web door's roles claim and to ignore that claim entirely when an LIS "
        "role is present, so an LMS administrator cannot reach even the empty "
        "view by writing one into a launch. E1 "
        "replaces claim-derived landing roles with the assignment model, at which "
        "point this exception should go and this equality will say so. "
        "Arbitrated 2026-08-21 on E0-18 PR 1."
    ),
}


def parsed_modules() -> dict[Path, ast.Module]:
    """Every module under `backend/app`, parsed.

    A file that does not parse is a failure of the sweep rather than a module to
    skip: it would drop silently out of both halves below, and the half that
    matters is the one that reports what it did *not* find.
    """
    found: dict[Path, ast.Module] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            found[path] = ast.parse(text, filename=str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
    return found


def names_the_care_role(tree: ast.Module) -> bool:
    """Does this module name the Care role in code — not in a comment or a docstring?

    Three shapes, which is what an enum member and its uses look like: the bare
    name (`CARE = "CARE"`, or `Role.CARE` read as an attribute), and the string
    constant on its own. A docstring is a string constant too, and does not match,
    because it is a sentence rather than the word.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == CARE_ROLE:
            return True
        if isinstance(node, ast.Attribute) and node.attr == CARE_ROLE:
            return True
        if isinstance(node, ast.Constant) and node.value == CARE_ROLE:
            return True
    return False


def maps_claims_to_roles(tree: ast.Module) -> bool:
    """Does this module read a claim — again, in code rather than in prose?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute | ast.arg | ast.FunctionDef):
            spelling = getattr(node, "id", None) or getattr(node, "attr", None)
            spelling = spelling or getattr(node, "arg", None) or getattr(node, "name", "")
            if any(fragment in spelling.lower() for fragment in CLAIM_IDENTIFIER_FRAGMENTS):
                return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            if any(fragment in lowered for fragment in CLAIM_STRING_FRAGMENTS):
                return True
    return False


def test_no_module_that_reads_a_claim_names_the_care_role() -> None:
    """Criterion 10: the escalation that would walk past §4 entirely.

    An LMS administrator controls what an `id_token` says. If any code path turns
    what it says into a role, and Care is one of the roles it can produce, then the
    person who administers the LMS can hand themselves the ability to re-identify
    a student who wrote a self-harm comment — and the audit log will record the
    access as legitimate, because by then it is.

    So the two sides are kept apart at the source level: the launch and the login
    establish *who* somebody is, and this table establishes *what they may do*.
    E0-11 says the same rule from the resolver's side ("an actor holds Care
    because they hold a live `CARE` role assignment, never because of anything in
    an LTI or OIDC claim"); this is the version that cannot be satisfied by a
    resolver that reads claims carefully.

    The set flagged is required to **equal** `EXCEPTIONS`, so this fails in both
    directions: a module that starts reading claims beside the role, and an
    exception nobody has re-examined since the module it names changed.
    """
    modules = parsed_modules()
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)}, so this sweep "
        "looked at nothing and would report success. E0-01 ships the backend package."
    )

    naming_care = sorted(path for path, tree in modules.items() if names_the_care_role(tree))
    assert naming_care, (
        f"No module under {APP_ROOT.relative_to(REPO_ROOT)} names {CARE_ROLE!r} in code at all, "
        f"across {len(modules)} modules. This is the canary rather than the assertion: E0-09 adds "
        "the role to the assignment schema, and until the sweep can find it somewhere, 'no claim "
        "path names it' is true of a search that is looking for the wrong string. If the role is "
        "deliberately spelled some other way, change `CARE_ROLE` at the top of this file — and "
        "note that SPEC §2.1's table and E0-09 both write it this way."
    )

    reading_claims = {path for path, tree in modules.items() if maps_claims_to_roles(tree)}
    flagged = {
        path.relative_to(REPO_ROOT).as_posix() for path in reading_claims.intersection(naming_care)
    }
    unexcepted = sorted(flagged - set(EXCEPTIONS))
    stale = sorted(set(EXCEPTIONS) - flagged)
    assert flagged == set(EXCEPTIONS), (
        f"{unexcepted} both read a claim and name the {CARE_ROLE} role without being named in "
        f"`EXCEPTIONS`, and {stale} are excepted here without being flagged any more. E0-09: 'No "
        "LTI claim, no OIDC claim, and no LMS role may ever produce a `CARE` assignment… a "
        "claim-to-Care mapping would let an LMS administrator grant themselves identity access, "
        "walking past every guarantee in §4.' Care is the only role that can re-identify a student "
        "(§6.2), and the administrator of the platform controls what the claim says.\n"
        "A module in the first list is a new claim-to-Care path: if it names the role only to "
        "exclude it, name it out of a shared enumeration in the model layer instead, so the "
        "exclusion is a fact about the role rather than a literal in the door — and if it produces "
        "no assignment at all, that is an exception somebody decides and writes into `EXCEPTIONS` "
        "above with a behavioural test beside it, not something this sweep infers.\n"
        "A module in the second list is an exception that has gone stale: it was deleted or it no "
        "longer reads a claim, and an ignore rule nobody has to keep true is how a sweep stops "
        "sweeping. Remove the entry."
    )
