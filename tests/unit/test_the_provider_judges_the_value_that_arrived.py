"""No request value is normalised before the check that judges it — ADR 0062, E0-16.

[ADR 0062](../../docs/adr/0062-a-request-is-parsed-once-at-the-edge.md) records
that five of the six defects found across three review rounds against the mock
OIDC provider were one shape: **a value transformed between the wire and the
check that was supposed to judge it.** A `.strip()` before a PKCE shape check made
every string that trimmed to the verifier acceptable; a bare `str.split()` on the
scope turned a malformed value into a well-formed one *before the refusal written
for it could fire*; `state` and `nonce` came back trimmed, against RFC 6749
§4.1.2 and OIDC Core §3.1.3.7.

The record's own last paragraph says what was missing: "nothing here is enforced
by a gate: it is a convention with a docstring on `submitted()` and this record
behind it, so a future `.strip()` in a new endpoint is caught by review or by
nothing." That is `docs/MISTAKES.md` entry 2 stated in advance, on the rule that
produced five defects — so this module is the gate.

**What it asserts.** Every call to `strip`, `lower`, `upper`, `casefold`, `split`
or `unquote` anywhere under `mock-idp/app/` is one of four permitted shapes, each
with a reason that is not "it was already there":

1. **Configuration read at startup** (`config.py`). Not request data at all — an
   operator's trailing newline in a Compose literal is a different problem from a
   client's trailing newline in a parameter, and the value is never echoed,
   hashed or compared against something a client kept.
2. **A presence test whose result is discarded** — `if not value.strip():`, and
   only that shape. ADR 0062 rule 1 sanctions exactly it: presence is judged on a
   trimmed copy and the untrimmed value is what gets handed on, because "three
   spaces is not a `state`" and "your `state` is these three spaces" are different
   statements. `if value.strip() == expected:` is **not** permitted by this rule
   and is the defect wearing the same clothes.
3. **A split with an explicit delimiter.** The scope fix is
   `scope.split(SCOPE_DELIMITER)` against the grammar written out above it. A bare
   `.split()` — the one that treats a tab, a newline and U+00A0 as separators — is
   never permitted.
4. **Normalising a media type off a request header.** RFC 9110 makes media types
   case-insensitive and permits parameters after a semicolon, so normalising
   there is correct rather than tolerated. Recognised by the call chain being
   rooted in `...headers.get(...)`, which is a header rather than a parameter.

**The permissions are shapes, not line numbers, and that is deliberate.** A line
number ages on the next edit; a count ages faster — the presence tests were three
when the first reviewer counted them and are four now, and a guard permitting
"three presence checks" would have gone red for a correct change. What is written
down here is the property each site has, so the same code passes wherever it
moves and a *new* site passes only by having the same property.

**A permission that matches nothing is an error**, not a silent no-op, or the
allowlist accumulates permissions for code nobody can find. And the sweep asserts
it read something before it asserts it found nothing wrong: a scan pointed at the
wrong directory finds no violations, which is `docs/MISTAKES.md` entry 3's
emptiness passing for evidence.

**What this does not cover, stated so it is not read as covered.**

  - `rstrip`, `lstrip`, `replace`, `casefold` on bytes, `title` and every other
    way to change a value are **not swept**. The six names here are the six that
    were measured against this tree; adding a seventh without measuring it would
    make this gate fail on ground nobody has looked at, and a gate that fails for
    an unmeasured reason teaches people to add exclusions.
  - It is a syntactic check, not dataflow. It cannot see that a value came from a
    request; it sees the shape of the call. A `.strip()` on a request value
    written in one of the four permitted shapes passes — which for shapes 2, 3 and
    4 is the point, and for shape 1 rests on `config.py` staying a configuration
    module.
  - It reads the source tree rather than the running application, so a
    normalisation reached through `getattr` or a library call is invisible to it.
"""

import ast
from pathlib import Path
from typing import Any, NamedTuple

# The six names measured against this tree. Every one of them turns a value into
# a different value, and each has been the mechanism of a defect here or is one
# character away from having been.
SWEPT_NAMES = frozenset({"strip", "lower", "upper", "casefold", "split", "unquote"})

# Directories with no source of ours in them.
UNSWEPT_DIRECTORIES = frozenset({"__pycache__", ".mypy_cache", ".ruff_cache"})

# A number low enough that any real provider clears it and high enough that a
# sweep which silently read nothing does not. **This suite's choice**, set well
# below what the tree holds so that ordinary removals do not trip it — what it
# guards against is zero, not one fewer than yesterday. Deliberately not a count
# of the calls that are there: a number that has to be re-measured on every edit
# is a record that will be wrong again (`docs/MISTAKES.md` entry 1).
FEWEST_CREDIBLE_CALLS = 4


class CallSite(NamedTuple):
    """One call to a normalising name, with the shapes that decide whether it is allowed.

    The shapes are computed where the syntax is in hand rather than carried as a
    node, so the permissions below read as statements about the call rather than
    as tree-walking, and so the shape detection is one function with its own
    control test.
    """

    path: Path
    line: int
    name: str
    source: str
    presence_test: bool
    explicit_delimiter: bool
    off_a_header: bool


def called_name(node: ast.Call) -> str | None:
    """The name being called, whether it is a method or a bare function."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def mentions_a_header(node: ast.Call) -> bool:
    """Whether what is being called sits on a chain rooted in a request header.

    Only the *callee* subtree is walked, never the arguments: `request.headers.
    get("content-type", "").split(";")` is a header being normalised, and
    `value.split(request.headers.get("x"))` is a parameter being normalised with a
    header for a delimiter, which is a different thing entirely.
    """
    return any(
        isinstance(inner, ast.Attribute) and inner.attr == "headers"
        for inner in ast.walk(node.func)
    )


def normalising_calls(source: str, path: Path) -> list[CallSite]:
    """Every call to a swept name in `source`, with its shape worked out.

    `path` is carried rather than derived so the control test below can ask what
    this makes of a snippet as if it were any module — the configuration
    permission is about which file the call is in, and a control that got that
    permission for free would be testing nothing.
    """
    tree = ast.parse(source)

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    within_a_condition: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            for inner in ast.walk(node.test):
                within_a_condition.add(id(inner))

    found: list[CallSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = called_name(node)
        if name not in SWEPT_NAMES:
            continue
        parent = parents.get(id(node))
        negated = isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.Not)
        found.append(
            CallSite(
                path=path,
                line=node.lineno,
                name=str(name),
                source=ast.get_source_segment(source, node) or "",
                presence_test=(not node.args and negated and id(node) in within_a_condition),
                explicit_delimiter=(name == "split" and bool(node.args)),
                off_a_header=mentions_a_header(node),
            )
        )
    return found


def swept_modules(app_directory: Path) -> list[Path]:
    """Every Python source file under the provider's package, in a stable order."""
    return sorted(
        path
        for path in app_directory.rglob("*.py")
        if not any(part in UNSWEPT_DIRECTORIES for part in path.parts)
    )


def sweep(app_directory: Path) -> list[CallSite]:
    """Every normalising call in the provider, from every module it has."""
    found: list[CallSite] = []
    for path in swept_modules(app_directory):
        found.extend(normalising_calls(path.read_text(encoding="utf-8"), path))
    return found


# The four shapes that are allowed, each with the reason it is allowed. Nothing
# here is a line number and nothing here is a count: a permission is a property a
# call has, so the same code passes wherever it moves in the file and a new call
# passes only by having the same property.
PERMISSIONS: dict[str, tuple[Any, str]] = {
    "configuration read at startup": (
        lambda site: site.path.name == "config.py",
        "`config.py` reads the service's own configuration out of the environment. It is not "
        "request data, it is never echoed back to a client, hashed, or compared against a value "
        "a client kept — an operator's trailing newline in a Compose literal is a different "
        "problem from a client's trailing newline in a parameter.",
    ),
    "a presence test whose result is discarded": (
        lambda site: site.presence_test,
        "ADR 0062 rule 1: presence is judged on a trimmed copy and the untrimmed value is handed "
        "on, because 'three spaces is not a `state`' and 'your `state` is these three spaces' are "
        "different statements. Only `if not value.strip():` qualifies — the trimmed value is "
        "tested and thrown away. `if value.strip() == expected:` judges a value nobody sent and is "
        "the defect this record exists to keep out.",
    ),
    "a split with an explicit delimiter": (
        lambda site: site.explicit_delimiter,
        "ADR 0062 rule 2: a grammar check uses the specification's grammar. `scope.split(SP)` "
        "against RFC 6749 Appendix A.4 is that; a bare `.split()` is the defect, because it "
        "treats a tab, a newline and U+00A0 as separators and turns a malformed value into a "
        "well-formed one before anything can refuse it.",
    ),
    "normalising a media type off a request header": (
        lambda site: site.off_a_header,
        "RFC 9110 makes a media type case-insensitive and permits parameters after a semicolon, "
        "so `request.headers.get('content-type', '').split(';')[0].strip().lower()` is reading "
        "the header correctly rather than repairing it. A header is not a parameter: nothing "
        "compares it byte for byte with something a client kept.",
    ),
}

# Snippets the shape rules must classify correctly, as (source, permitted). The
# permitted half and the refused half are both here for `docs/MISTAKES.md` entry
# 3's reason: a matcher is run against the text you claim it catches *and* the
# text you claim it allows, or a rule that permits everything looks exactly like
# a tree with nothing wrong in it. Each pair differs by one property.
SHAPE_CASES = {
    "a presence test": ("if not value.strip():\n    pass\n", True),
    "a comparison against a trimmed value": ('if value.strip() == "x":\n    pass\n', False),
    "a presence test whose value is kept": ("if not (x := value.strip()):\n    pass\n", False),
    "a split with a delimiter": ('parts = scope.split(" ")\n', True),
    "a bare split": ("parts = scope.split()\n", False),
    "a media type off a header": (
        'kind = request.headers.get("content-type", "").split(";")[0].strip().lower()\n',
        True,
    ),
    "a parameter trimmed on its way to a check": ("stored = verifier.strip()\n", False),
    "a parameter lowercased": ("client = client_id.lower()\n", False),
}

# Where the control snippets are pretended to live. **Not `config.py`**: that
# permission is granted by file name, so a control parsed as configuration would
# be permitted whatever its shape and every refused case above would pass.
CONTROL_MODULE = Path("flow.py")


def permissions_for(site: CallSite) -> list[str]:
    """Every permission that covers `site`, by name."""
    return sorted(name for name, (allows, _) in PERMISSIONS.items() if allows(site))


def test_the_shape_rules_allow_the_sanctioned_calls_and_refuse_their_near_misses() -> None:
    """The control on the sweep, run before its silence counts as evidence.

    Every case differs from its neighbour by one property: a presence test
    against a comparison on the same trimmed value, a split with a delimiter
    against the bare one, a header chain against a bare parameter. Without the
    refused half, a rule that returned `True` for everything would make the sweep
    below pass over any tree at all — and it would pass quietly, which is the
    shape `docs/MISTAKES.md` entry 3 is about.

    The walrus case is the sharpest: `if not (x := value.strip()):` is a presence
    test by every syntactic measure except the one that matters, which is that the
    trimmed value is kept and used afterwards.
    """
    for case, (source, permitted) in sorted(SHAPE_CASES.items()):
        sites = normalising_calls(source, CONTROL_MODULE)
        assert sites, (
            f"The sweep found no normalising call in {case} ({source!r}), so this case asserts "
            "nothing. Either the snippet is wrong or `SWEPT_NAMES` no longer covers it."
        )
        allowed = [permissions_for(site) for site in sites]
        if permitted:
            assert all(allowed), (
                f"{case} ({source!r}) is a shape this guard is supposed to allow, and no "
                f"permission covers it: {allowed}. A rule that refuses correct code is a rule "
                "people work around."
            )
        else:
            assert not any(allowed), (
                f"{case} ({source!r}) is a shape this guard is supposed to refuse, and "
                f"{allowed} permits it. Every assertion in this module rests on these rules "
                "saying no to something."
            )


def test_every_normalising_call_in_the_provider_is_one_the_record_permits(
    mock_idp_dir: Path, repo_root: Path
) -> None:
    """ADR 0062's rule, enforced rather than recorded.

    The record's own consequence section says a future `.strip()` in a new
    endpoint is "caught by review or by nothing". Three rounds is the measurement
    of how well review catches this particular shape: each round found it in a
    place the previous round had not looked, and the second round's fix sat
    downstream of the repair that made it unable to fire.

    The count assertion first is not ceremony. This test asserts that a set is
    empty, and an empty set is what a sweep that read nothing produces — a
    renamed directory, a package moved one level down, an exclusion list that grew
    until it covered the tree. The sweep has to be seen to have read something
    before its silence counts.
    """
    app_directory = mock_idp_dir / "app"
    assert app_directory.is_dir(), (
        f"{app_directory} does not exist, so this guard has nothing to read. SPEC §13 puts the "
        "provider's package there."
    )

    modules = swept_modules(app_directory)
    assert modules, f"There are no Python modules under {app_directory}."

    sites = sweep(app_directory)
    assert len(sites) >= FEWEST_CREDIBLE_CALLS, (
        f"The sweep found {len(sites)} normalising calls across {len(modules)} modules under "
        f"{app_directory}, which is too few for this provider — so the emptiness it is about to "
        "assert would be a fact about the sweep rather than about the code. `SWEPT_NAMES` and "
        "`swept_modules` above are where to look."
    )

    unpermitted = [site for site in sites if not permissions_for(site)]
    reported = [
        f"  {site.path.relative_to(repo_root)}:{site.line}  {site.source}" for site in unpermitted
    ]
    permitted_shapes = [f"  {name} — {reason}" for name, (_, reason) in sorted(PERMISSIONS.items())]

    assert not unpermitted, "\n".join(
        [
            "A value is normalised somewhere the record does not permit:",
            *reported,
            "",
            "ADR 0062: one parse, at the edge, into typed values; every check and every echo "
            "reads what that parse produced or what actually arrived. Five of the six defects "
            "found in this provider were a value transformed between the wire and the check that "
            "was supposed to judge it — a PKCE verifier that only had to trim to the right value, "
            "a scope made well-formed before the refusal for it could fire, a `state` and a "
            "`nonce` handed back to the client altered.",
            "",
            "The shapes this guard permits, and why:",
            *permitted_shapes,
            "",
            "If the new call is one of those shapes, write it that way. If it is a fifth thing "
            "that is genuinely safe, add it to `PERMISSIONS` above with the reason — and the "
            "reason has to be a property of the value, not that the call was already there.",
        ]
    )


def test_no_permission_in_this_guard_is_for_code_that_no_longer_exists(
    mock_idp_dir: Path,
) -> None:
    """A permission nothing uses is a hole waiting for something to fall into it.

    The failure this prevents is quiet and cumulative: a sanctioned site is
    deleted or rewritten, its permission stays, and the next call that happens to
    have that shape is allowed by a rule nobody would have written for it. It is
    the reason this guard is a small set of shapes rather than a growing list —
    and the reason the set has to shrink when the code does.

    `tests/unit/test_care_session_is_bound_to_the_care_service.py` holds the same
    property for the Care credential's allowlist, for the same reason.
    """
    app_directory = mock_idp_dir / "app"
    assert app_directory.is_dir(), f"{app_directory} does not exist."

    sites = sweep(app_directory)
    assert sites, "The sweep found no normalising calls at all, so every permission looks stale."

    used = {name for site in sites for name in permissions_for(site)}
    stale = sorted(set(PERMISSIONS) - used)

    assert not stale, "\n".join(
        [
            f"These permissions cover nothing in {app_directory}: {stale}.",
            "",
            "Either the code they were written for is gone — in which case delete them, because "
            "a permission for code nobody can find is a hole the next call with that shape falls "
            "into — or the sweep has stopped recognising it, which is worse and is what the "
            "control test above exists to catch first.",
        ]
    )
