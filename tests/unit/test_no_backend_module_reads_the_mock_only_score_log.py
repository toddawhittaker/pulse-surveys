"""Nothing the backend runs names the mock-only posted-score log — ticket E3-08, criterion 3.

E3-08's third acceptance criterion, in full: "No backend code calls
`/mock/posted-scores`, asserted rather than reviewed."

**What the rule is and where it comes from.** ADR 0047 puts the posted-score
readback outside the AGS namespace deliberately: a conformant AGS `Result`
carries `userId`, `resultScore`, `resultMaximum` and `scoreOf` and nothing else —
no timestamp, no progress members — so what a tool *sent* cannot be read back
through the protocol at all. The mock platform serves `GET /mock/posted-scores`
so that this repository's tests can check the wire, and the `/mock/` prefix is
the whole of what says no real platform serves it. A backend module that learned
to read it would have learned something no platform outside this repository
offers, and the first real LMS it met would answer 404 to a call the whole test
suite had been green on.

**Why a sweep rather than a reviewer.** The route is one string. A helper added
to `app/services/grading.py` "just to check what we posted" is three lines, reads
as diagnostics, and passes every behavioural test in the repository — because
every one of them runs against the mock that serves it. Criterion 3 says
"asserted rather than reviewed" for exactly that reason.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives about its
own sweep: a correct implementation is very likely to *say* `/mock/posted-scores`
in a docstring, because "this is never read from the backend — ADR 0047" is the
sentence a careful implementer writes next to the AGS client. Searching the file
text would turn that sentence into a failure and teach the next person to delete
the explanation. Comments are absent from an `ast` tree entirely and docstrings
are subtracted by name below, so what remains is the strings a module actually
runs — and a URL a module never assembles is a URL it never fetches.

**The canary, and it is this module's own load-bearing part**
(`docs/MISTAKES.md` entries 3 and 35). A sweep that only ever reports absence
cannot be told from a sweep that has gone blind, and this one reports absence on
every run. So the identical finder is run over `mock-lms/app/config.py` — the
file that declares the route — and required to *find* it. The sample it is
checked against is a **whole line copied out of that file**, the line the
declaration starts on included, because a line retyped from where somebody thinks
it begins is the thing the sample exists to disprove.

**What this cannot see**, said plainly so nothing here is cited as more than it
is (`docs/MISTAKES.md` entry 14): a path assembled at run time from pieces
(`"/mock/" + "posted-scores"`), a path read out of configuration or the
environment, and a call made by something outside `backend/app/`. It is a
tripwire on the only way anybody would actually write it. The structural half of
the same guarantee is that the mock keeps the route under a prefix ADR 0134
excludes from its AGS credential enforcement, which
`tests/integration/test_mock_lms_ags_requires_a_token.py` holds.

**Which failure a red here is.** Every test in this module is expected **green**
on the tree E3-08 starts from: nothing under `backend/app/` names the route
today, and `mock-lms/app/config.py` declares it. A red in the canary tests means
this module is broken — the finder, or the copied line, and not the backend. A
red in the sweep itself means a backend module has learned the route.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The tree the criterion is about. SPEC §13 puts the whole application under
# `backend/app/`, so this is every module that could make the call.
BACKEND_APP = REPO_ROOT / "backend" / "app"

# The file that declares the route, used as the control sample below. Named as a
# path rather than imported: `mock-lms/` and `mock-idp/` both ship a package
# called `app` and neither is importable from a test process (ADR 0039's
# collision), which is why every consumer of a mock-side constant in this suite
# reads it as text or over HTTP.
THE_FILE_THAT_DECLARES_THE_ROUTE = REPO_ROOT / "mock-lms" / "app" / "config.py"

# The route ADR 0047 puts outside the AGS namespace. The fragment rather than the
# whole path, so a module that reached it through a different prefix — a
# development proxy, an absolute URL on the mock's published host port — is caught
# too. `posted-scores` appears nowhere else in this project's vocabulary.
MOCK_ONLY_FRAGMENT = "posted-scores"

# The whole path, for the messages and for the sample checks. `/mock/` is the
# prefix that carries the decision.
MOCK_ONLY_PATH = "/mock/posted-scores"

# **The canary sample: one whole line, copied out of
# `mock-lms/app/config.py`, the line the declaration starts on included**
# (`docs/MISTAKES.md` entry 3's rule for building a sample). It is asserted to be
# present in that file verbatim as well as being fed to the finder, so a sample
# that has gone stale says so in its own test rather than quietly becoming a
# string this module agrees with itself about.
THE_DECLARING_LINE = 'MOCK_POSTED_SCORES_PATH = "/mock/posted-scores"'

# Text the finder must **not** answer to. The near miss is the point: `score` and
# `scores` are ordinary words in this project — `post_scores_for_all_sections`,
# `score_text`, `scores_url` — and a finder matching any of them would be red
# against every correct backend and would be deleted by whoever met it.
SAMPLES_THE_FINDER_MUST_ALLOW = (
    "post_scores_for_all_sections(session, settings=settings, http=http)",
    "SCORES_PATH = f'{LINE_ITEM_PATH}/scores'",
    "return path_appended(self.line_item_id(line_item), 'results')",
    "scores_posted = []",
)

# Text the finder must answer to: the declaration itself, and the two shapes a
# backend call would actually take.
SAMPLES_THE_FINDER_MUST_CATCH = (
    THE_DECLARING_LINE,
    'response = http.get("/mock/posted-scores")',
    'response = http.get("http://mock-lms:8000/mock/posted-scores")',
)


def names_the_mock_only_route(source: str) -> bool:
    """Does any string this source *runs* name the mock-only readback?

    Docstrings are subtracted and comments are never in the tree, so prose about
    the route stays legal — see the module docstring for why that matters more
    than it looks.
    """
    return bool(mock_only_strings_in(ast.parse(source)))


def mock_only_strings_in(tree: ast.AST) -> list[str]:
    """Every non-docstring string constant in `tree` that names the route."""
    return sorted({value for value in executable_strings(tree) if MOCK_ONLY_FRAGMENT in value})


def docstring_constants(tree: ast.AST) -> set[int]:
    """The identity of every string node that is a docstring rather than a value.

    Transcribed from `tests/unit/test_no_service_reads_an_identity_table_directly.py`
    rather than imported, for the reason every module in this suite gives: a test
    module importing its sibling depends on where pytest put `tests/` on
    `sys.path`, and an import error is not a red.
    """
    found: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = list(getattr(node, "body", []))
        if not body or not isinstance(body[0], ast.Expr):
            continue
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(id(first))
    return found


def executable_strings(tree: ast.AST) -> list[str]:
    """Every string constant in a module that is not a docstring."""
    excluded = docstring_constants(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in excluded
    ]


def parsed_backend_modules() -> dict[Path, ast.Module]:
    """Every module under `backend/app/`, parsed.

    A file that does not parse is a failure of the sweep rather than a module to
    skip: it would drop silently out of the walk and the walk's whole job is to
    report what it did *not* find.
    """
    found: dict[Path, ast.Module] = {}
    for path in sorted(BACKEND_APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            found[path] = ast.parse(source, filename=str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
    return found


# ---------------------------------------------------------------------------
# The controls on this module's own finder. **A red in this section means these
# tests are broken, not the backend**, and the sweep below then reports nothing.
# ---------------------------------------------------------------------------


def test_the_finder_catches_the_route_and_allows_the_words_that_look_like_it() -> None:
    """Both directions, before the sweep's silence is believed to mean anything.

    `docs/MISTAKES.md` entry 3's rule for a pattern searched against text: run it
    against the text you claim it catches *and* against the text you claim it
    allows. The allow side costs something real here — `scores` is everywhere in
    E3's own vocabulary, and a finder that fired on `post_scores_for_all_sections`
    would be red against the correct implementation of the very sweep it guards,
    at which point somebody deletes this file.

    **The mutations this kills:** a finder narrowed to the exact path, which a
    call written against the mock's published host port slips past; a finder
    widened to `scores`, which is red on every correct backend; and a finder that
    answers `False` for everything, which is what a sweep reporting nothing looks
    like from the outside.
    """
    for sample in SAMPLES_THE_FINDER_MUST_CATCH:
        assert names_the_mock_only_route(sample), (
            f"The finder read no mention of {MOCK_ONLY_PATH!r} out of {sample!r}, which names it "
            "in a string a module runs. A finder that has gone blind reads exactly like a sweep "
            "that found nothing wrong."
        )
    for sample in SAMPLES_THE_FINDER_MUST_ALLOW:
        assert not names_the_mock_only_route(sample), (
            f"The finder read a mention of {MOCK_ONLY_PATH!r} out of {sample!r}, which names no "
            "such thing. `score` and `scores` are ordinary words in E3's vocabulary — the sweep "
            "itself is called `post_scores_for_all_sections` — so a finder that matches them is "
            "red against every correct backend."
        )


def test_prose_naming_the_route_is_left_alone_and_a_call_beside_it_is_not() -> None:
    """A docstring may explain the rule; the line under it may not break it.

    The exemption is deliberate and it is also the thing that could hollow the
    sweep out, so it is posed in both directions on one source: a module whose
    docstring names the route and whose code does not is clean, and the same
    module with one fetch added is not.

    **The mutation this kills:** a docstring subtraction written as "ignore every
    string constant in a module that has a docstring", or one that walks only the
    module's own docstring and leaves a function's, either of which turns the
    whole sweep into a formality the day somebody writes the explanatory sentence.
    """
    explained = (
        '"""ADR 0047: /mock/posted-scores is the mock platform\'s own inspection\n'
        'surface and this module never reads it."""\n'
        "def post(http):\n"
        '    """The score post. Nothing here reads /mock/posted-scores."""\n'
        '    return http.post("/lti/contexts/c/line_items/1/scores")\n'
    )
    assert not names_the_mock_only_route(explained), (
        "The finder fired on a module that only *explains* the rule in prose. Punishing the "
        "explanation trains the next reader to delete it, and the comment is the only thing that "
        "tells a later maintainer why the route may not be called."
    )

    breached = explained + '    return http.get("/mock/posted-scores")\n'
    assert names_the_mock_only_route(breached), (
        "The finder passed a module that fetches the route, because its docstrings mention it too. "
        "The docstring exemption has to be a subtraction of the docstring nodes and not of the "
        "module, or every breach can be hidden by writing a sentence above it."
    )


def test_the_finder_finds_the_route_in_the_file_that_declares_it() -> None:
    """The canary: the identical finder, run over a file that certainly has it.

    `docs/MISTAKES.md` entry 35's rule — a guard that only ever reports absence
    cannot tell you which mechanisms it can still see. `mock-lms/app/config.py`
    declares the route as a module-level constant, which is a non-docstring string
    and therefore exactly the kind of thing the sweep below looks for. If this
    goes quiet, the sweep's silence over `backend/app/` means nothing whatever.

    **The whole declaring line is asserted present in that file as well**, copied
    rather than retyped (entry 3's rule for building a sample). Two failures land
    here and the messages tell them apart: a finder that has stopped working, and
    a sample that has gone stale because the mock respelled its constant — in
    which case the sweep may still be fine and this file needs one line changed.

    **A red here means these tests are broken, not the backend.**
    """
    assert THE_FILE_THAT_DECLARES_THE_ROUTE.is_file(), (
        f"{THE_FILE_THAT_DECLARES_THE_ROUTE} does not exist, so this module has no control sample "
        "and the sweep below is an assertion about absence with nothing saying the finder can find "
        "a presence."
    )
    source = THE_FILE_THAT_DECLARES_THE_ROUTE.read_text(encoding="utf-8")

    assert THE_DECLARING_LINE in source, (
        f"{THE_FILE_THAT_DECLARES_THE_ROUTE.relative_to(REPO_ROOT)} does not carry the line "
        f"{THE_DECLARING_LINE!r} that this module copied out of it. Either the mock has respelled "
        "its constant — in which case re-copy the whole line, the line the declaration starts on "
        "included — or the declaration has moved to another file and this module's canary now "
        "points at nothing."
    )

    found = mock_only_strings_in(ast.parse(source, filename=str(THE_FILE_THAT_DECLARES_THE_ROUTE)))
    assert found, (
        f"The finder read no mention of {MOCK_ONLY_PATH!r} out of "
        f"{THE_FILE_THAT_DECLARES_THE_ROUTE.relative_to(REPO_ROOT)}, which declares it as a "
        "module-level constant. That is this module going blind, and with it blind the sweep below "
        "reports a clean backend whatever the backend contains."
    )
    assert MOCK_ONLY_PATH in found, (
        f"The finder found {found} in the declaring file, and none of them is {MOCK_ONLY_PATH!r}. "
        "The control has to see the actual path, not some other string that happens to carry the "
        "fragment, or the sweep below is calibrated against the wrong thing."
    )


# ---------------------------------------------------------------------------
# Criterion 3 itself.
# ---------------------------------------------------------------------------


def test_no_module_under_backend_app_names_the_mock_only_posted_score_route() -> None:
    """Criterion 3: no backend module runs a string naming `GET /mock/posted-scores`.

    ADR 0047 makes the readback a mock-only surface, and this is the assertion the
    criterion asks for in place of a reviewer. Every readback of a posted body in
    this repository goes through `tests/fixtures/lti_services.py::posted_scores`
    and through nothing else.

    **The mutation this exists to kill** is a diagnostic helper on the passback
    path — a `_what_did_we_post()` in `app/services/grading.py`, or a `/dev`
    console panel showing the gradebook as the platform holds it, both of which
    are things somebody adds on purpose while debugging a passback and neither of
    which any behavioural test in this repository would notice, because every one
    of them runs against the mock that serves the route. Against a real LMS the
    call 404s and whatever depends on it fails in production only.

    **The near miss it must survive** is the AGS Result container: reading a
    posted score back through `…/line_items/{id}/results` is the *conformant* way
    to do it and is exactly what E3-08's criterion 2 drives. Nothing about that
    path carries this fragment, so a backend that grows a Result reader stays
    green here — which is the difference this test has to keep straight.

    The non-emptiness guard comes first and is not ceremony: an empty walk
    satisfies "no module names the route" perfectly, and a `BACKEND_APP` that had
    moved would report a clean sweep forever.
    """
    modules = parsed_backend_modules()
    assert modules, (
        f"There are no Python modules under {BACKEND_APP.relative_to(REPO_ROOT)}, so this sweep "
        "looked at nothing and would report success. SPEC §13 puts the whole application there, "
        "and a walk that reaches none of it is this file pointing at the wrong tree rather than a "
        "backend that keeps the rule."
    )

    naming = {
        str(path.relative_to(REPO_ROOT)): found
        for path, tree in modules.items()
        if (found := mock_only_strings_in(tree))
    }
    assert not naming, (
        f"{naming} run a string naming the mock platform's own posted-score log. ADR 0047 puts "
        f"`GET {MOCK_ONLY_PATH}` outside the AGS namespace as an inspection surface no real "
        "platform serves — a conformant `Result` carries no timestamp and no progress members, "
        "which is the whole reason the mock offers it — so a backend module that reads it works "
        "against this repository's mock and 404s against every LMS in the world. E3-08's third "
        "criterion: 'No backend code calls `/mock/posted-scores`, asserted rather than reviewed.' "
        "The conformant readback is the AGS Result container at `…/line_items/{id}/results`."
    )
