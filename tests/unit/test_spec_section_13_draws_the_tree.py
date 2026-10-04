"""SPEC §13 draws the repository as it is (SPEC §13).

§13 calls its tree "the list of module homes rather than a suggestion": a new
piece of code goes in the module whose comment already describes it. That rule
only works while the tree is true. A module the tree does not draw is a home
nobody looking at §13 can find, and a drawn module that does not exist is a home
that sends work to the wrong place.

**The expectation comes from the filesystem, never from a list here**
(`docs/MISTAKES.md` entries 19 and 53). The inventory is a walk of
`backend/app/` and `frontend/src/`, so a module added tomorrow is expected in
§13 tomorrow without anyone editing this file. The drawn side is parsed from
the tree's own indentation into full paths, so a basename drawn under the wrong
parent does not count as drawn.

**A drawn path that does not exist is allowed only with a citation on its
line**: the epic that builds it, the ADR that decided it, or the roadmap phase
when no epic owns it yet. A module that was built somewhere else is not a
planned module, and its line comes out of the tree instead.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "SPEC.md"

# The two trees §13 is held to. Everything else it draws is top-level
# orientation (Compose files, scripts, mock services) and is not walked.
CHECKED_ROOTS = ("backend/app", "frontend/src")

# Each tree level is four columns: "├── ", "└── ", "│   " or four spaces.
_LEVEL_WIDTH = 4
_ENTRY = re.compile(r"^((?:[│ ]   )*)[├└]── (\S+)")
_CITATION = re.compile(r"ADR \d{4}|\bE\d+\b|Phase \d")


def _section_13_tree(spec_text: str) -> str:
    """The fenced block that opens the `## 13.` section."""
    section = spec_text.split("\n## 13.", 1)[1].split("\n## 14.", 1)[0]
    return section.split("```", 2)[1]


def _drawn_paths(tree: str) -> dict[str, str]:
    """Every drawn entry as a full repository path, mapped to its whole line."""
    drawn: dict[str, str] = {}
    stack: list[str] = []
    for line in tree.splitlines():
        match = _ENTRY.match(line)
        if match is None:
            continue
        depth = len(match.group(1)) // _LEVEL_WIDTH
        name = match.group(2).rstrip("/")
        del stack[depth:]
        stack.append(name)
        drawn["/".join(stack)] = line
    return drawn


def _real_paths() -> set[str]:
    """Every backend module and directory, and every frontend directory."""
    real: set[str] = set()
    backend = REPO_ROOT / "backend" / "app"
    for path in backend.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if path.is_dir() or (path.suffix == ".py" and path.name != "__init__.py"):
            real.add(path.relative_to(REPO_ROOT).as_posix())
    frontend = REPO_ROOT / "frontend" / "src"
    for path in frontend.rglob("*"):
        if path.is_dir():
            real.add(path.relative_to(REPO_ROOT).as_posix())
    return real


def test_the_parse_and_the_walk_both_found_the_tree() -> None:
    # Both assertions below compare two sets, and two empty sets agree. A
    # parse that went blind (a changed fence, a wrong indentation width) or a
    # walk from the wrong root would turn every check here green.
    drawn = _drawn_paths(_section_13_tree(SPEC_PATH.read_text(encoding="utf-8")))
    for known in ("backend/app/main.py", "frontend/src/routes/student"):
        assert known in drawn, f"the §13 parse did not find {known}; the parser is blind"
    real = _real_paths()
    assert "backend/app/main.py" in real, "the filesystem walk found nothing; wrong root"
    assert "frontend/src/routes/student" in real, "the frontend walk found nothing"


def test_every_real_module_and_directory_is_drawn_at_its_real_path() -> None:
    drawn = _drawn_paths(_section_13_tree(SPEC_PATH.read_text(encoding="utf-8")))
    missing = sorted(_real_paths() - drawn.keys())
    assert not missing, f"SPEC §13 does not draw these, at these paths: {missing}"


def test_every_drawn_path_that_does_not_exist_cites_who_builds_it() -> None:
    drawn = _drawn_paths(_section_13_tree(SPEC_PATH.read_text(encoding="utf-8")))
    uncited = sorted(
        path
        for path, line in drawn.items()
        if path.startswith(CHECKED_ROOTS)
        and not (REPO_ROOT / path).exists()
        and _CITATION.search(line) is None
    )
    assert not uncited, (
        "SPEC §13 draws these but they do not exist, and their line cites no "
        f"epic, ADR or roadmap phase: {uncited}"
    )
