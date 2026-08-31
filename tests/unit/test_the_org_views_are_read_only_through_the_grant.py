"""The relations the org views are built on are reached through a grant function and nowhere else.

E0-41 wrote this file about three org views. E1's boundary review (finding M8,
`docs/tickets/e1/boundary-review.md`) found the rule policing a **hand-written
list of three names** while `pulse_app` had since been granted table-grain
`SELECT` on `enrollment`, and view-grain `SELECT` on `section_roster` and
`section_enrollment_count` — the relations where a scoped reader in the
application is the only narrowing there is. A list somebody has to remember to
extend is not a closed set, and the three it omitted are the three E1 added.
**The file keeps its name; the rule it enforces is wider than the name.**

**So the policed inventory is parsed out of the catalog at test time**, in two
parts, from the `.sql` files under `backend/app/views_sql/` **at any depth**:

  - every relation a **`CREATE VIEW`** creates, and
  - every relation those **view bodies read** — the `FROM` and `JOIN` relations
    of each view's definition, base tables included.

The depth is part of the rule rather than an implementation detail. Every `.sql`
file in that directory sits at the top of it today, which is a fact about how
many views E1 shipped; `tests/integration/test_identity_separated_views.py` reads
the same catalog recursively and says in as many words that the SQL is found at
any depth, so a view filed in a subdirectory is a catalog member everywhere else
in this suite. A one-deep read here would take that view *and the relations it is
built on* out of the policed set with nothing saying so — M8's own failure one
directory down, which is what the re-review of 2026-08-31 found and what
`test_the_policed_inventory_reads_a_view_filed_in_a_subdirectory_of_the_catalog`
now holds closed.

That is the structure the guarded set cannot shrink without the guard noticing.
A view is the thing §4.1 is written about, and the table underneath it is the
thing the view exists to keep people off: `section_roster` and
`section_enrollment_count` are read views over `enrollment`, so `enrollment`
enters the set because the catalog says the roster views are built on it, not
because a sentence in this file says so. The closure is transitive for free — a
view built on a view has both bodies parsed — and it needs no judgement call
anywhere, which is what makes it a closed set rather than a longer list.

**The set this builds is broad, and the breadth is the point.** As this is
written the parse yields fourteen relations — the three org views, the two roster
views, `enrollment` and `role_assignment` beneath them, and the org containment
tables the purview views are computed over, `course` and `section` among them.
That is wider than "the relations SPEC §4.1 is about", and it is chosen over a
narrower set deliberately: **no judgement is exercised anywhere in the parse**,
so there is no step at which somebody decides a relation does not matter, and no
step at which they can decide it wrongly. A hand-curated inventory is exactly
what M8 found, and the three names it had left out were the three E1 added.

The count moves with the catalog and is written nowhere in this file — a view
added by a later ticket brings its base tables with it, and a relation no view is
defined over (`nrps_call`, `launch_defect`, `lti_launch_nonce`) stays outside the
rule. Fourteen is what the parse yielded when this paragraph was written, not a
number anything here asserts.

**What to do when a legitimate raw read reds this sweep**, written down because
the wrong answer is the cheap one. A read path may one day name `course` or
`section` in a statement of its own for reasons that have nothing to do with
§4.1. There are then exactly two answers. Move the read to a sanctioned location
— a grant function in `authz.py` is where a read of these relations belongs — or
add a location exemption **in its own reviewed commit**, with a statement pin like
the two the exempt files below carry, so the exemption covers the statement its
reason describes and nothing else.

**The inventory is never narrowed.** Trimming the parse, or lifting one relation
out of it, is the repair that looks smallest under time pressure and silently
reopens every hole the closure was built to close — a guard deleted rather than
fixed, which is how this file came to be policing a hand-written list of three
names in the first place. A red here is a question about one statement; it is
never a question about the inventory.

If parsing the view bodies pulls in an identity table, that is correct and not
over-reach — the overlap with
`tests/unit/test_no_service_reads_an_identity_table_directly.py` costs nothing.

**Why the rule is the same rule for a table as for a view.** Nothing in the
database narrows any of these. `pulse_app` holds an unfiltered `SELECT`, and the
only narrowing anywhere is the `WHERE` inside the grant functions in
`backend/app/services/authz.py`, which is where SPEC §2.1's purview rules live —
"a Lead Faculty assignment never grants sibling leads' courses" (§4.1 item 2)
among them. A module that runs its own `SELECT` against one of these relations
reads the institution, and every rule §2.1 states about scope is a rule that
query does not apply. `enrollment` makes that concrete: it is the row that says
which student sits in which section, and a query written over it applies whatever
scoping its author remembered.

**E0-41's written carve-out is gone, and that is the ruling rather than an
accident.** Its version said the directory "also holds E0-10's identity-separated
read views, which read paths are *supposed* to name" — and M8 is the finding that
the carve-out was where the hole lived. `section_roster` and
`section_enrollment_count` are exactly those read views. Every relation the
catalog creates or is built on is reached through a grant function, and a read
path that needs a new one asks for it in `authz.py`.

**Two halves, and neither implies the other.** The first catches SQL naming a
policed relation, written fresh in a module. The second catches the shorter
route — importing `app.views_sql.queries`, the module holding the statements the
grant functions already run, and running one of them on a session of the
caller's own, which names no relation in the importing module at all.

**Exemptions are locations, never shapes.** Four of them for the SQL half, and
**two of the four are pinned to the statement their reason describes** — the
location is how the exemption is *spelled*, and the pin is how wide it is:

  - `backend/app/services/authz.py`, the chokepoint the rule is written around.
    Unpinned, because reading these relations under §2.1's purview rules is the
    whole of what that module is for;
  - `backend/app/api/dev.py`, ADR 0100's count-only read of the enrolled figure
    off the development console. **Pinned to `section_enrollment_count`**: the
    ADR's own consequence is that "the enrolled figure has to keep coming from
    the view", and a console that grew a second read would otherwise inherit this
    exemption for it;
  - `backend/app/services/safety.py`, the Care service's own revalidation of the
    holds-Care rule. Its `EXISTS` over `role_assignment` is one of the four
    statements of that rule that move together, and it is written there rather
    than called out of `authz.py` because the Care path revalidates on its own
    `pulse_care` credential — a grant function in `authz.py` would answer on the
    `pulse_app` connection, which is the wrong one. This exemption was added by
    the fix round's verifier pass, which is the run that found it. **Pinned to
    `role_assignment`**: when E9 or E10 gives that module a query over
    `assignment_scope`, it is an offender again and this file says so;
  - the `backend/app/views_sql/` package, which is where the SQL lives (ADR 0041:
    "the SQL lives in `backend/app/views_sql/<object>_v<NNN>.sql`, and the
    revision executes it by name"). A rule forbidding the query module from
    naming the relations it queries would forbid the design the ticket describes,
    and what keeps that module honest is the second half below — one importer.

The console is the one that shows why an exemption has to be spelled as a
location rather than as a shape. A count is a *shape*, and "a read that only
counts is fine" is a rule no sweep can grade: `SELECT count(*) FROM enrollment
WHERE section_id = :id` counts one section and `SELECT count(*) FROM enrollment`
counts the institution, and a sweep reading for `count(` cannot tell which of
them the next one is. So the console is exempt for being the console, and a
count-only read written anywhere else is caught — which is asserted below rather
than described.

**The pin is what keeps the location from being wider than its reason.** An
exemption by location excuses a *file*, and the reasons above are about single
statements; without a pin, the exemption a module was granted for one query
silently covers the next one somebody adds to it. So each pinned file's policed
reads are asserted as an **equality** against the relation its reason names —
which is both halves at once: the read must still be there (an exemption that
excuses nothing is dead, and a sweep that cannot see it is blind), and there must
be nothing else.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives: a correct
module is very likely to *say* `assignment_scope` in a docstring, because "this
goes through the grant rather than reading `assignment_scope`" is the sentence a
careful implementer writes next to the call. Searching the text would turn that
sentence into a failure and teach the next person to delete the comment. So
comments are absent from the tree entirely, and docstrings are subtracted by name.

**The mutations this file exists to redden**, named so a reviewer can run them:

  - **Dropping a relation from the parsed inventory** — deleting the view-body
    half of the catalog parse, or reading only the `CREATE VIEW` names. The
    premise test
    `test_the_policed_inventory_comes_from_the_catalog_and_holds_the_six_the_rule_names`
    goes red, because `enrollment` reaches the set by no other route.
  - **Widening an exemption to a shape** — exempting a statement because it only
    counts, or because it carries a `WHERE`.
    `test_the_sql_sweep_exempts_four_locations_and_no_exemption_is_a_shape`
    goes red on the planted count-only read at an unexempt location.
  - **Growing a pinned exemption past the statement its reason names** — a second
    query added to the development console, or the `assignment_scope` read E9 or
    E10 will want in `safety.py`.
    `test_each_pinned_exemption_covers_exactly_the_statement_its_reason_names`
    goes red on the file whose reads have grown, and names what it grew by.
  - **Re-adding the hand-written list** — replacing the parse with a tuple of
    the three org views. The premise test goes red on the other three names,
    which is the failure M8 reported and the reason the list is gone.
  - **Reading the catalog one directory deep** — `VIEWS_SQL_DIR.glob("*.sql")` in
    place of `rglob`, which is one word and changes nothing about today's tree.
    `test_the_policed_inventory_reads_a_view_filed_in_a_subdirectory_of_the_catalog`
    goes red on the nested view and the relation it is built on.
  - **Widening that repair past `.sql`** — a recursive read that takes every
    *file* under the catalog whatever its extension, which polices a `CREATE
    VIEW` written in a note. The same test goes red, printing the two relations
    the note contributed. Its bare cousin, `rglob("*")`, is red too but not here:
    it yields the subdirectory itself and raises `IsADirectoryError` inside
    `policed_relations` before any inventory exists. Both are caught, one as an
    assertion and one as a crash, and the difference is recorded so neither is
    cited as the other.

**What this cannot see**, stated so nothing here is cited as more than it is
(`docs/MISTAKES.md` entry 14):

  - **A relation name assembled at run time**, and a read that reaches a policed
    relation through a helper in a package this sweep does not walk. The concrete
    member of that class, so it is not left abstract: `f"SELECT * FROM {SCHEMA}.
    enrollment"` is missed, because the literal segments an f-string leaves in the
    tree are `"SELECT * FROM "` and `".enrollment"` — and the segment carrying the
    relation's name carries no introducer in front of it. Anything that
    interpolates between the keyword and the name has the same effect.
  - **A name that reaches the planner with no introducer in front of it.** After
    E0-42's security pass the introducers are `FROM`, `JOIN`, `INTO`, `UPDATE`,
    `TABLE`, `USING`, each with an optional `ONLY`, and the bare comma of a
    `FROM`/`USING` list — which covers `DELETE … USING`, `MERGE … USING`,
    `INSERT INTO` and the comma-separated join the first version missed. What is
    left outside is a relation named as a value rather than as a target:
    `'public.enrollment'::regclass` in a lock, or a `TRUNCATE`.
  - **An ORM query.** `select(Enrollment)` carries no SQL text at all. The
    sibling sweep in `test_no_service_reads_an_identity_table_directly.py` reads
    calls rather than strings and covers that route for the identity tables; for
    these relations it is not covered here, and the grant is what remains.
  - **A relation a view reads through a run-time name**, or a view whose body
    carries a semicolon inside a literal — the body is sliced at the first `;`.
    Either drops a name out of the *inventory*, which is the direction the
    premise test exists to catch for the six names the rule is written about.
  - **`from app import views_sql` followed by attribute access**, for the import
    half: reaching the package and walking to it is a route this does not follow.
  - **Migrations.** `backend/alembic.ini`'s revisions live outside
    `backend/app/`, and creating these relations is what they are for.

**And two things it sees that it need not**, recorded so each reads as a decision
rather than a bug. The comma introducer fires on a *string* that lists these
relations after a comma — an exception message reading "reads role_assignment,
enrollment" is the shape that will actually meet it. **Moving it into a docstring
is not the remedy**, because a message a caller has to be handed cannot live in
one. Reword it — "role_assignment and enrollment", or one name per line — or add
the module to a written exemption here with the reason beside it. Either is a
minute's work and leaves the guard closed; the alternative, dropping the comma,
is the hole E0-42's security pass walked through. And a **common table
expression's name** inside a view body is read as a relation the view is built
on, so a `WITH walk AS (…)` puts `walk` in the policed set. That costs nothing
unless a CTE is named after something the application also queries, and the
remedy there is to rename the CTE.
"""

import ast
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
VIEWS_SQL_DIR = APP_ROOT / "views_sql"
AUTHZ_MODULE = APP_ROOT / "services" / "authz.py"
DEV_CONSOLE_MODULE = APP_ROOT / "api" / "dev.py"

# The Care service's own revalidation of the holds-Care rule. **This exemption was
# added by the fix round's verifier pass**, which ran the closed sweep over the
# tree and found this module's `_HOLDS_A_LIVE_CARE_ASSIGNMENT` — an `EXISTS` over
# `public.role_assignment` — as its one offender. It is the deliberate design the
# module documents above that constant: the rule "holds a live CARE assignment" is
# written in four statements that move together (`docs/MISTAKES.md` entry 13 is
# the reason they are named in one comment rather than left to be found), and this
# copy exists because the Care service revalidates on its own `pulse_care`
# credential rather than through `authz.py`'s `pulse_app` path. A grant function in
# `authz.py` would answer the question on the wrong connection.
#
# The judgment is recorded here as a location rather than by narrowing the
# inventory: `role_assignment` stays policed, so the next module to name it is
# still reported.
CARE_REVALIDATION_MODULE = APP_ROOT / "services" / "safety.py"

# The three exempt *files*, and the exempt *package* beside them. Files are
# compared whole: a prefix or a substring test would exempt
# `services/authz_helpers.py` and `api/dev_tools.py` along with them, which is how
# a closed set is defeated one level out. The package is compared by containment,
# which is what a package exemption means, and `app/api/views_sql/` — the same
# name one directory over — is not it.
SQL_SWEEP_EXEMPT_FILES = (AUTHZ_MODULE, DEV_CONSOLE_MODULE, CARE_REVALIDATION_MODULE)
SQL_SWEEP_EXEMPT_PACKAGE = VIEWS_SQL_DIR

# The module that holds the statements the grant functions run, spelled as the
# ticket spells it and as an import would.
QUERY_MODULE = "app.views_sql.queries"

# **A premise, not the inventory.** The inventory is parsed from `views_sql/` at
# test time; these six are asserted to be *in* it, so a rename, a view body
# rewritten, or a return to a hand-written list fails loudly here instead of
# quietly emptying the sweep. Three are E0-41's org views — SPEC §2.1's
# supervision graph and purview are computed over them — and three are what E1
# added and M8 found missing: `pulse_app` holds table-grain `SELECT` on
# `enrollment` and view-grain `SELECT` on the other two, and a scoped reader in
# the application is the only narrowing between any of them and the institution.
#
# `enrollment` is in this list for a second reason: it is the one name of the six
# that can only arrive by the **view-body** half of the parse, so a premise
# holding just the view names would go on passing with that half deleted.
ORG_VIEWS = ("lead_faculty_course", "assignment_scope", "containment_path")
ROSTER_RELATIONS = ("enrollment", "section_roster", "section_enrollment_count")
REQUIRED_IN_INVENTORY = ORG_VIEWS + ROSTER_RELATIONS

# A name no view in the catalog creates or reads, used as the control that the
# sweep is a sweep and not a match-everything. It is asserted absent from the
# inventory before it is relied on, so this cannot pass by the name having quietly
# become real.
UNPOLICED_RELATION = "widget_ledger"

# **Every modifier Postgres allows between `CREATE` and `VIEW`.** Measured during
# E0-34's review against every spelling the server accepts:
# `tests/integration/test_identity_separated_views.py::CREATES_A_VIEW` is the same
# pattern, and it is here rather than imported because a test module importing its
# sibling depends on where pytest put `tests/` on `sys.path` and an import error
# is not a red. A file this misses is a view whose name *and whose base tables*
# drop out of the inventory, which is the failure the premise test exists to catch.
CREATES_A_VIEW = re.compile(
    r"\bcreate\s+(?:or\s+replace\s+)?"
    r"(?:(?:temp(?:orary)?|materialized|recursive)\s+)*view\s+"
    r"(?:if\s+not\s+exists\s+)?"
    r'(?:"?\w+"?\s*\.\s*)?"?(?P<name>\w+)"?',
    re.IGNORECASE,
)

# The words that end a `FROM` list. Everything between `FROM` and the first of
# these is the list of relations the view is reading, and the first token of each
# comma-separated piece is the relation — `FROM public.enrollment e,
# public.section s WHERE …` is two relations and two aliases. Bounded this way
# rather than by matching one relation per `FROM`, because the second relation of
# a comma list is exactly what E0-42's pass found slipping through the other
# sweep, and a name missing from the *inventory* is a relation nothing polices.
CLAUSE_AFTER_A_FROM_LIST = (
    "where",
    "group",
    "having",
    "order",
    "limit",
    "offset",
    "fetch",
    "window",
    "union",
    "intersect",
    "except",
    "join",
    "inner",
    "left",
    "right",
    "full",
    "cross",
    "natural",
    "on",
    "using",
    "returning",
    "as",
)

FROM_LIST = re.compile(
    r"\bfrom\b\s+(?P<relations>[^;()]*?)"
    r"(?=\b(?:" + "|".join(CLAUSE_AFTER_A_FROM_LIST) + r")\b|[;()]|$)",
    re.IGNORECASE,
)

JOINS_A_RELATION = re.compile(
    r"\bjoin\b\s+(?:only\s+)?(?P<name>(?:\"?\w+\"?\.)?\"?\w+\"?)",
    re.IGNORECASE,
)

# Tokens that stand in front of a relation without being one.
NOT_THE_RELATION = frozenset({"only", "lateral"})

# `PUBLIC . enrollment` and `public.enrollment` are the same reference, and the
# tokeniser below splits on whitespace — so the spacing is normalised away first.
QUALIFIER_SPACING = re.compile(r"\s*\.\s*")

# What can introduce a relation in SQL, for the sweep over application modules.
# **The first version enumerated join syntaxes and missed the oldest one there
# is** — the comma-separated `FROM` list, `FROM public.role_assignment ra,
# public.assignment_scope s` — which E0-42's security pass ran through
# `reference_to` and watched pass both halves of this sweep. The repair closes the
# class rather than that instance, which is this repository's recorded lesson
# about widening a guard a second time:
#
#   - `from`, `join`, `into`, `update` and `table` — the keyword forms, with
#     `DELETE FROM` and `INSERT INTO` falling out of the first two;
#   - `using`, which is how `DELETE … USING` and `MERGE … USING` name a second
#     relation, and which the keyword list had no member for at all;
#   - `only` after any of them: `FROM ONLY public.enrollment`;
#   - a bare comma, which is the list form — every relation after the first in a
#     `FROM` or `USING` list is introduced by nothing else.
#
# What the comma costs is in this module's docstring, along with the two remedies
# that leave the guard closed.
RELATION_INTRODUCERS = r"(?:\b(?:from|join|into|update|table|using)\b(?:\s+only\b)?\s+|,\s*)"

# An optional schema in front of the name, quoted on either part or neither:
# `public.x`, `"public".x`, `public."x"`, `PUBLIC . X`. The first version spelled
# `public` literally and unquoted, so `"public".assignment_scope` — which is what
# a generated statement writes — went unseen.
SCHEMA_QUALIFIER = r"(?:\"?\w+\"?\s*\.\s*)?"

LINE_COMMENT = re.compile(r"--[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def without_comments(sql: str) -> str:
    """`sql` with its comments blanked, so a commented-out view defines nothing.

    A `CREATE VIEW` left behind in a comment by a revision that stopped applying
    it would otherwise put its name and its base tables in the policed set, and
    the sweep would report offenders against a view the database does not have.
    The limitation, stated rather than discovered: a `--` inside a string literal
    is treated as a comment, which no file in this catalog has and which would
    only ever *shrink* the inventory — a shrink the premise test below catches.
    """
    return LINE_COMMENT.sub(" ", BLOCK_COMMENT.sub(" ", sql))


def relation_name_of(reference: str) -> str | None:
    """The relation a `FROM`/`JOIN` reference names, alias and schema removed.

    `public.enrollment e` is `enrollment`; `ONLY "public"."enrollment"` is
    `enrollment`. The alias is dropped by taking the first token that is not a
    word standing in front of a relation, which is what keeps `e`, `s` and `ra`
    out of an inventory the whole sweep is built from.
    """
    for token in reference.split():
        candidate = token.split(".")[-1].strip('"').lower()
        if candidate in NOT_THE_RELATION:
            continue
        return candidate if re.fullmatch(r"\w+", candidate) else None
    return None


def relations_read_by(body: str) -> set[str]:
    """Every relation a view body reads, by name.

    Only after `FROM` and `JOIN`, and never out of a select list: a comma in
    `SELECT person_id, course_id` introduces a **column**, and a parse that read
    one as a relation would put `course_id` in the policed set and make the sweep
    fire on every statement in the tree that selects it.
    """
    normalised = QUALIFIER_SPACING.sub(".", body)
    found: set[str] = set()
    for match in FROM_LIST.finditer(normalised):
        for piece in match.group("relations").split(","):
            name = relation_name_of(piece)
            if name:
                found.add(name)
    for match in JOINS_A_RELATION.finditer(normalised):
        name = relation_name_of(match.group("name"))
        if name:
            found.add(name)
    return found


def view_definitions(sql: str) -> list[tuple[str, str]]:
    """Every `CREATE VIEW` in `sql`, as the name it creates and the body it selects.

    The body runs from the end of the name to the statement's semicolon, so the
    view's own name is not read back as a relation it is built on, and the next
    statement in the file is not read as part of this one.
    """
    found: list[tuple[str, str]] = []
    for match in CREATES_A_VIEW.finditer(sql):
        end = sql.find(";", match.end())
        body = sql[match.end() : end if end != -1 else len(sql)]
        found.append((match.group("name").lower(), body))
    return found


def policed_relations() -> tuple[str, ...]:
    """The inventory: every view the catalog creates and every relation those views read.

    Read from `backend/app/views_sql/` at test time rather than written here. A
    view lands there with its own `.sql` file under ADR 0041's rule, so it appears
    in this set — with whatever it is built on — without this file being edited.
    That is the difference between an inventory and a list somebody has to
    remember to update, and M8 is what the list cost.

    **`rglob`, so the catalog is read at any depth.** Every `.sql` file happens to
    sit at the top of that directory today, which is a fact about how many views
    E1 shipped rather than a rule; the sibling guard
    `tests/integration/test_identity_separated_views.py` already reads the same
    catalog recursively and documents the SQL as found at any depth. A one-deep
    read here would drop a view somebody files in a subdirectory *and its base
    tables* out of the policed set, silently — which is M8's own failure one
    directory down, and what the re-review of 2026-08-31 found.
    """
    files = sorted(VIEWS_SQL_DIR.rglob("*.sql"))
    assert files, (
        f"There are no `.sql` files under {VIEWS_SQL_DIR.relative_to(REPO_ROOT)}, so the policed "
        "inventory this file sweeps for is empty and every assertion below is vacuous. ADR 0041 "
        "puts every view's SQL there and E0-10 shipped the first of them."
    )
    found: set[str] = set()
    for path in files:
        for name, body in view_definitions(without_comments(path.read_text(encoding="utf-8"))):
            found.add(name)
            found |= relations_read_by(body)
    return tuple(sorted(found))


def reference_to(names: tuple[str, ...]) -> re.Pattern[str]:
    """A pattern matching any of `names` in a position that reads or writes it."""
    return re.compile(
        RELATION_INTRODUCERS + SCHEMA_QUALIFIER + r"\"?(" + "|".join(names) + r")\"?\b",
        re.IGNORECASE,
    )


def sql_sweep_is_exempt(path: Path) -> bool:
    """Whether `path` is one of the four locations a policed relation may be named in.

    Whole-path equality for the three files, and directory containment for the
    package. A `startswith`, a file-name test or a directory-name test would
    exempt a sibling module that merely reads like one of these, and the exemption
    is the whole of what stands between a module and the institution.
    """
    return path in SQL_SWEEP_EXEMPT_FILES or SQL_SWEEP_EXEMPT_PACKAGE in path.parents


def import_sweep_is_exempt(path: Path) -> bool:
    """Whether `path` may import the module holding the grant functions' statements.

    E0-41's set, unchanged: the chokepoint, and the package where the SQL lives. A
    rule that forbade the query module's own package from reaching it would forbid
    ADR 0041's design. It is not the same set as `sql_sweep_is_exempt` — the
    development console names a relation and imports nothing — and the two are
    written separately so that widening one does not silently widen the other.
    """
    return path == AUTHZ_MODULE or VIEWS_SQL_DIR in path.parents


def parsed_modules(is_exempt: Callable[[Path], bool]) -> dict[Path, ast.Module]:
    """Every module under `backend/app/` that `is_exempt` does not excuse, parsed.

    A file that does not parse is a failure of the sweep rather than a module to
    skip: it would drop silently out of the sweep, and the half that matters is
    the one reporting what it did *not* find.
    """
    found: dict[Path, ast.Module] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if is_exempt(path):
            continue
        source = path.read_text(encoding="utf-8")
        try:
            found[path] = ast.parse(source, filename=str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
    return found


def docstring_constants(tree: ast.AST) -> set[int]:
    """The identity of every string node that is a docstring rather than a value."""
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


def relations_named_by(tree: ast.AST, pattern: re.Pattern[str]) -> list[str]:
    """Which policed relations a module's executable strings read or write."""
    return sorted(
        {
            match.group(1).lower()
            for statement in executable_strings(tree)
            for match in pattern.finditer(statement)
        }
    )


def package_of(path: Path) -> str:
    """The dotted package a module sits in, as an import inside `backend/` sees it.

    `backend/app/services/safety.py` sits in `app.services`; so does
    `backend/app/services/__init__.py`, whose own module name *is* that package.
    Needed because a relative import resolves against the package rather than
    against the file, and a sweep that read only absolute imports is defeated by
    `from ..views_sql import queries` — one level out, which is where a closed-set
    guard is usually defeated.
    """
    parts = path.relative_to(BACKEND_ROOT).with_suffix("").parts
    return ".".join(parts[:-1])


def imported_targets(tree: ast.AST, path: Path) -> set[str]:
    """Every dotted module name a module imports, relative imports resolved."""
    package = package_of(path)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".") if package else []
                climbed = anchor[: len(anchor) - (node.level - 1)]
                if not climbed:
                    # More dots than there are packages to climb. Python refuses
                    # such an import outright, so there is nothing to resolve and
                    # nothing this sweep could attribute it to.
                    continue
                prefix = ".".join(climbed)
                base = f"{prefix}.{base}" if base else prefix
            if base:
                found.add(base)
                found |= {f"{base}.{alias.name}" for alias in node.names}
    return found


# ---------------------------------------------------------------------------
# The catalog parse, run against both directions before the inventory it builds
# is believed. A pattern searched against text is a test that can go blind and
# report success (`docs/MISTAKES.md` entry 3); a catalog parse that has gone blind
# builds an empty policed set, and an empty policed set makes every sweep below
# green over any tree at all.
#
# Each sample is a view definition, the name it must yield, and the relations its
# body must be read as building on.
# ---------------------------------------------------------------------------

VIEW_DEFINITIONS_MUST_READ = (
    (
        "CREATE VIEW section_enrollment_count AS\n"
        "  SELECT s.id AS section_id, count(*) AS enrolled\n"
        "  FROM public.enrollment e\n"
        "  JOIN public.section s ON s.id = e.section_id\n"
        "  WHERE e.ended_on IS NULL\n"
        "  GROUP BY s.id;",
        "section_enrollment_count",
        {"enrollment", "section"},
    ),
    (
        # The comma-separated list, with aliases: two relations, not one.
        "CREATE OR REPLACE VIEW assignment_scope AS\n"
        "  SELECT ra.person_id, c.id AS course_id\n"
        "  FROM role_assignment ra, public.course c\n"
        "  WHERE ra.scope_id = c.id;",
        "assignment_scope",
        {"role_assignment", "course"},
    ),
    (
        # `ONLY`, quoted identifiers on both parts, and an outer join.
        "CREATE VIEW section_roster AS\n"
        '  SELECT u.id FROM ONLY "public"."enrollment" e\n'
        '  LEFT JOIN "user" u ON u.id = e.user_id;',
        "section_roster",
        {"enrollment", "user"},
    ),
    (
        # A subquery, whose own `FROM` is a relation the view is built on.
        "CREATE VIEW lead_faculty_course AS\n"
        "  SELECT id FROM course\n"
        "  WHERE id IN (SELECT course_id FROM lead_faculty_mapping);",
        "lead_faculty_course",
        {"course", "lead_faculty_mapping"},
    ),
    (
        # A spaced qualifier and a materialised view, which is still a view.
        "CREATE MATERIALIZED VIEW containment_path AS\n"
        "  SELECT id, parent_id FROM PUBLIC . department;",
        "containment_path",
        {"department"},
    ),
)

# Names that appear in the sample bodies above and are **not** relations the views
# are built on. A parse that read a select-list column or a table alias as a
# relation would put these in the policed set, and the sweep would then fire on
# every statement in the tree that selects one.
NOT_RELATIONS_IN_THOSE_BODIES = frozenset(
    {
        "id",
        "person_id",
        "course_id",
        "section_id",
        "user_id",
        "parent_id",
        "enrolled",
        "count",
        "e",
        "s",
        "u",
        "c",
        "ra",
        "null",
        "only",
        "as",
        "where",
        "select",
    }
)

# Statements a catalog file carries that define no view. None of them may
# contribute a name: the inventory comes from what the views are built on, and a
# grant is not a view. This is the ruling that replaced "every relation a
# `GRANT … TO pulse_app` names", which would have policed ordinary product tables
# that no view is defined over.
NOT_A_VIEW_DEFINITION = (
    "GRANT SELECT ON public.tool_signing_key TO pulse_app;",
    "GRANT SELECT, INSERT ON public.launch_defect TO pulse_app;",
    "GRANT EXECUTE ON FUNCTION public.record_roster_email(uuid, text) TO pulse_app;",
    "REVOKE ALL ON public.widget_ledger FROM pulse_app;",
    "CREATE INDEX ON public.nrps_call (section_id, called_at DESC);",
    "INSERT INTO public.start_letter_map (letter) VALUES ('A');",
    "-- CREATE VIEW commented_out_view AS SELECT id FROM secret_table;",
)


def test_the_catalog_parse_reads_a_view_and_what_it_is_built_on_and_nothing_else() -> None:
    """The catalog parse, both directions, before the inventory it builds is used.

    The catch side is what closes the set: a `JOIN`, a comma-separated list with
    aliases, `ONLY`, quoted identifiers on both parts of a qualifier, a spaced
    qualifier, a materialised view and a subquery's own `FROM` all name a relation
    the view is built on, and a parse that missed any of them would leave that
    relation unpoliced with every test in this file green. `enrollment` is in two
    of these samples because it is the relation M8 is about and the one that
    reaches the inventory by no other route.

    The allow side is where the weight is, and it is two rules. A **column or an
    alias is not a relation**: a parse that read `course_id` out of a select list
    would police it, and the sweep would then fire on every statement in the tree
    that selects it — red against correct code, and deleted rather than fixed. And
    a **statement that defines no view contributes nothing**, which is the ruling
    that replaced the grant-driven inventory: a `GRANT` on an ordinary product
    table says nothing about §4.1, and policing it would assert a rule nobody
    agreed to.

    **The mutation this exists to survive**: reading only the `CREATE VIEW` names
    and not the bodies, which drops every base table — `enrollment` first — out of
    the policed set while leaving this file looking like it polices six things.
    """
    for definition, name, built_on in VIEW_DEFINITIONS_MUST_READ:
        parsed = view_definitions(without_comments(definition))
        assert [entry[0] for entry in parsed] == [name], (
            f"The catalog parse read {[entry[0] for entry in parsed]} out of a definition of "
            f"{name!r}. A view missed here takes its base tables with it."
        )
        read = relations_read_by(parsed[0][1])
        assert built_on <= read, (
            f"The catalog parse read {sorted(read)} as what {name!r} is built on, and it is built "
            f"on {sorted(built_on)}. A base table missed here is a relation nothing polices, and "
            "the silence about it reads exactly like a clean tree."
        )
        mistaken = sorted(read & NOT_RELATIONS_IN_THOSE_BODIES)
        assert not mistaken, (
            f"The catalog parse read {mistaken} as relations {name!r} is built on. They are "
            "columns and aliases. A column in the policed set makes the sweep fire on every "
            "statement in the tree that selects it, which is red against every correct "
            "implementation."
        )

    for statement in NOT_A_VIEW_DEFINITION:
        parsed = view_definitions(without_comments(statement))
        assert not parsed, (
            f"The catalog parse read {parsed} out of {statement!r}, which defines no view. The "
            "inventory is the views and what they are built on; a grant, an index, an insert and "
            "a commented-out definition each put a name in the policed set that no view is "
            "defined over, and policing an ordinary product table asserts a rule nobody agreed to."
        )


def test_the_policed_inventory_comes_from_the_catalog_and_holds_the_six_the_rule_names() -> None:
    """The premise every sweep below rests on, asserted rather than assumed.

    The names this file polices have to be names the catalog really carries, or
    the sweep is a search for a string that appears nowhere and its silence means
    nothing — `docs/MISTAKES.md` entry 3 in the shape that is hardest to see,
    because a sweep looking for the wrong word passes every run.

    **This is the anti-vacuity canary for the whole file.** An empty inventory, or
    one that has quietly lost a name, makes every assertion below true of any tree.

    **The three mutations it reddens**, which is why it is one test and not three:

      - **the hand-written list, re-added.** M8's finding was a rule policing
        `lead_faculty_course`, `assignment_scope` and `containment_path` while
        `pulse_app` could read `enrollment`, `section_roster` and
        `section_enrollment_count`. Replace the parse with those three names and
        the other three are missing here.
      - **the view-body half of the parse, dropped.** `enrollment` is a base
        table; no `CREATE VIEW` names it, so the roster views' bodies are its only
        route into the set. This is why all six are the premise and not just the
        three the file used to hold.
      - **a relation renamed, or a view body rewritten** to reach `enrollment`
        through something this parse cannot follow. Either fails here, where the
        message says which name went missing, rather than reducing a sweep to
        nothing.
    """
    inventory = policed_relations()
    assert inventory, (
        f"The catalog under {VIEWS_SQL_DIR.relative_to(REPO_ROOT)} yielded no policed relation at "
        "all, so every sweep in this file is vacuous."
    )

    missing = sorted(name for name in REQUIRED_IN_INVENTORY if name not in inventory)
    assert not missing, (
        f"{missing} are neither created by nor read by any view in "
        f"{VIEWS_SQL_DIR.relative_to(REPO_ROOT)}, which yields {sorted(inventory)}.\n\n"
        "Each of the six is a relation `pulse_app` holds an unfiltered read on, with no narrowing "
        "anywhere but the `WHERE` clauses in `backend/app/services/authz.py` — SPEC §2.1's purview "
        "and §4.1 item 2's sibling isolation. If one has been renamed, rename it here in the same "
        "change; if a roster view stopped being defined over `enrollment`, this inventory can no "
        "longer see that table and the sweep below has stopped policing it. A sweep for a name "
        "nothing defines is green forever, which is the finding (M8) this test keeps closed."
    )


# ---------------------------------------------------------------------------
# A catalog planted at a depth the real one does not use yet, so that "the
# inventory is read from the catalog" is asserted about the *whole* catalog
# rather than about its top directory. The names are ones nothing in this
# repository defines, so a hit is this test's own file rather than a coincidence.
# ---------------------------------------------------------------------------

DEPTH_TOP_VIEW = "e1_depth_top_view"
DEPTH_TOP_BASE = "e1_depth_top_base"
DEPTH_NESTED_VIEW = "e1_depth_nested_view"
DEPTH_NESTED_BASE = "e1_depth_nested_base"
DEPTH_TEXT_VIEW = "e1_depth_text_view"
DEPTH_TEXT_BASE = "e1_depth_text_base"

DEPTH_SUBDIRECTORY = "reporting"

PLANTED_CATALOG = {
    f"{DEPTH_TOP_VIEW}_v001.sql": (
        f"CREATE VIEW {DEPTH_TOP_VIEW} AS\n  SELECT id FROM public.{DEPTH_TOP_BASE};\n"  # noqa: S608
    ),
    f"{DEPTH_SUBDIRECTORY}/{DEPTH_NESTED_VIEW}_v001.sql": (
        f"CREATE VIEW {DEPTH_NESTED_VIEW} AS\n  SELECT id FROM public.{DEPTH_NESTED_BASE};\n"  # noqa: S608
    ),
    # The near miss: a file in the same subdirectory that is not `.sql`. A view
    # definition sitting in a note contributes no relation, because ADR 0041 puts
    # the catalog in `.sql` files and nothing else in that tree is executed.
    f"{DEPTH_SUBDIRECTORY}/{DEPTH_TEXT_VIEW}.txt": (
        f"CREATE VIEW {DEPTH_TEXT_VIEW} AS\n  SELECT id FROM public.{DEPTH_TEXT_BASE};\n"  # noqa: S608
    ),
}


def test_the_policed_inventory_reads_a_view_filed_in_a_subdirectory_of_the_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The inventory is the catalog at any depth, not the catalog's top directory.

    `tests/integration/test_identity_separated_views.py` reads the same catalog
    with `rglob` and says in as many words that a view's SQL is found "at any
    depth". A view filed in a subdirectory is therefore a legitimate catalog
    member everywhere else in this suite — and it contributes nothing to the
    policed inventory here, which is the gap the re-review of 2026-08-31 found in
    M8's own closure. The relation such a view is built on is then a relation
    `pulse_app` reads unfiltered with no sweep over it and no sentence anywhere
    saying so: the silence reads exactly like a clean tree, which is the whole
    failure M8 was about, one directory down.

    Nothing exercises this today because every `.sql` file in the catalog happens
    to sit at the top. That is a fact about how many views E1 shipped, not a rule
    — the first ticket that groups its views into a subdirectory reopens the hole,
    and it reopens it silently.

    **The mutation this kills:** reading the catalog with `glob("*.sql")` instead
    of `rglob("*.sql")` — one word, which is the state `policed_relations` was in
    when this test was written. The nested view's name and its base relation are
    both absent from the inventory under it, and the equality below names them.

    **The near miss it tolerates:** a file in that same subdirectory that is not
    `.sql`. A `CREATE VIEW` written in a note or a README contributes nothing, and
    that is what stops the repair being a recursive read of *everything* — a
    catalog read that took any file would police `e1_depth_text_view` and
    `e1_depth_text_base`, and the equality below prints both.

    **The widening comes in two shapes and they die differently**, which is worth
    the sentence because only one of them dies here (`docs/MISTAKES.md` entry 9:
    do not cite a guard for a case it was never run against). A bare `rglob("*")`
    never reaches an inventory at all — it yields the `reporting/` directory
    itself, and reading it raises `IsADirectoryError` inside `policed_relations`.
    That is a red, and a loud one, but it is a crash rather than this assertion.
    The shape this test actually kills is the *file-filtered* recursive read —
    every file under the catalog, directories skipped, extension ignored — which
    builds an inventory perfectly well and puts the two text relations in it.
    That is also the shape somebody writes on purpose, reaching for "read the
    whole catalog", so it is the one worth a test.

    **The control is the top-level file**, asserted before the nested one. Without
    it a `policed_relations` that read nothing at all — a monkeypatch that did not
    land, a directory that was never written — would leave both halves of the
    equality failing for a reason that has nothing to do with depth.
    """
    catalog = tmp_path / "views_sql"
    for name, sql in PLANTED_CATALOG.items():
        path = catalog / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sql, encoding="utf-8")

    monkeypatch.setattr(sys.modules[__name__], "VIEWS_SQL_DIR", catalog)
    inventory = policed_relations()

    assert {DEPTH_TOP_VIEW, DEPTH_TOP_BASE} <= set(inventory), (
        f"The parse read {sorted(inventory)} from a planted catalog whose top directory holds a "
        f"view named {DEPTH_TOP_VIEW!r} built on {DEPTH_TOP_BASE!r}.\n\n"
        "This is the control, not the criterion: with the top-level file missing too, the failure "
        "below is about the catalog not being read at all — a monkeypatch that did not land, or a "
        "directory nothing was written into — rather than about depth."
    )

    assert set(inventory) == {
        DEPTH_TOP_VIEW,
        DEPTH_TOP_BASE,
        DEPTH_NESTED_VIEW,
        DEPTH_NESTED_BASE,
    }, (
        f"The policed inventory over the planted catalog is {sorted(inventory)}.\n\n"
        f"It holds a view at the top ({DEPTH_TOP_VIEW}, built on {DEPTH_TOP_BASE}) and one in the "
        f"`{DEPTH_SUBDIRECTORY}/` subdirectory ({DEPTH_NESTED_VIEW}, built on "
        f"{DEPTH_NESTED_BASE}), and both are catalog members: "
        "`tests/integration/test_identity_separated_views.py` reads this same directory with "
        "`rglob` and documents the SQL as found at any depth.\n\n"
        f"If {DEPTH_NESTED_VIEW!r} and {DEPTH_NESTED_BASE!r} are the ones missing, the derivation "
        "is reading one directory deep — and a view somebody files in a subdirectory brings its "
        "base tables out of the policed set with it, leaving relations `pulse_app` reads "
        "unfiltered with nothing sweeping for them and every test in this file green.\n\n"
        f"If {DEPTH_TEXT_VIEW!r} or {DEPTH_TEXT_BASE!r} are present instead, the widening went too "
        "far: they are written in a `.txt` file, and ADR 0041 puts the executed catalog in `.sql` "
        "files. A parse that reads prose polices relations no view is defined over."
    )


def reads_of(relation: str) -> tuple[str, ...]:
    """A read of `relation`, in every spelling that names a relation to the planner.

    The first four are M8's own list — named columns, `SELECT *`, schema-qualified
    and quoted. The rest arrived from E0-42's security pass, which measured an
    earlier version against the syntaxes Postgres accepts; the comma-separated
    list is the one it found passing this whole sweep.
    """
    return (
        f"SELECT section_id, person_id FROM {relation} WHERE section_id = :section_id",  # noqa: S608
        f"SELECT * FROM {relation}",  # noqa: S608
        f"SELECT 1 FROM public.{relation}",  # noqa: S608
        f'SELECT 1 FROM "{relation}"',  # noqa: S608
        f'SELECT 1 FROM "public"."{relation}"',  # noqa: S608
        f"select 1 from PUBLIC . {relation.upper()}",  # noqa: S608
        f"SELECT 1 FROM {UNPOLICED_RELATION} JOIN {relation} ON true",  # noqa: S608
        f"SELECT 1 FROM {UNPOLICED_RELATION} w, public.{relation} s WHERE w.id = s.id",  # noqa: S608
        f"SELECT 1 FROM {UNPOLICED_RELATION},{relation}",  # noqa: S608
        f"SELECT 1 FROM ONLY public.{relation}",  # noqa: S608
        f"DELETE FROM {UNPOLICED_RELATION} USING {relation} WHERE true",  # noqa: S608
        f"MERGE INTO {UNPOLICED_RELATION} w USING public.{relation} s ON true",
        f"UPDATE {relation} SET ended_on = :ended_on",  # noqa: S608
    )


def near_misses_of(relation: str) -> tuple[str, ...]:
    """Text naming `relation` without reading it, and text reading nothing policed.

    The `_totals` near miss is the load-bearing one: widening what may *introduce*
    a relation must not widen the **name**, or every relation sharing a prefix with
    a policed one becomes a false positive. The two lists are the comma form
    asserted from the other side — a comma before a column, and a comma between two
    relations nobody polices, both still have to pass.
    """
    return (
        f"SELECT * FROM {relation}_totals",  # noqa: S608
        f"SELECT {relation}_id FROM {UNPOLICED_RELATION} WHERE person_id = :person_id",  # noqa: S608
        f"GRANT SELECT ON public.{relation} TO pulse_app",
        f"-- {relation} is reached through the grant functions in `services/authz.py`",
        f"SELECT id FROM {UNPOLICED_RELATION} WHERE person_id = :person_id",  # noqa: S608
        f"SELECT a.id, b.id FROM {UNPOLICED_RELATION} a, {UNPOLICED_RELATION} b",  # noqa: S608
    )


def test_the_relation_sweep_catches_every_spelling_of_a_read_of_a_policed_relation() -> None:
    """Each policed relation, planted in each spelling, asserted caught.

    Built from the parsed inventory rather than from names written here, so this
    cannot pass by matching a string nothing defines. Each of the six is planted
    in turn — the three E1 added are the point of M8, and the three org views are
    here so that closing the set cannot quietly open the old one.

    **The mutation this exists to survive**: a spelling dropped from
    `RELATION_INTRODUCERS`, which is how E0-42's security pass got a
    comma-separated `FROM` list past an earlier version of this file with every
    test green.
    """
    inventory = policed_relations()
    pattern = reference_to(inventory)
    planted = sorted(name for name in REQUIRED_IN_INVENTORY if name in inventory)
    assert planted == sorted(REQUIRED_IN_INVENTORY), (
        f"Only {planted} of {sorted(REQUIRED_IN_INVENTORY)} are in the parsed inventory, so this "
        "test would plant fewer relations than the rule names; "
        "`test_the_policed_inventory_comes_from_the_catalog_and_holds_the_six_the_rule_names` "
        "diagnoses that."
    )

    for relation in planted:
        for sample in reads_of(relation):
            found = {match.group(1).lower() for match in pattern.finditer(sample)}
            assert relation in found, (
                f"The relation sweep did not read {relation!r} out of {sample!r}, which names it "
                f"in the position a statement reads it from (it read {sorted(found)}). A sweep "
                "that has gone blind reads exactly like a sweep that found nothing wrong."
            )


def test_the_relation_sweep_allows_a_near_miss_and_a_relation_no_view_is_built_on() -> None:
    """The other direction: what the sweep must not fire on.

    A purview query is written over columns — `person_id`, `section_id` — and a
    sweep that fired on a column named after a relation, or on the `GRANT` that
    lets the connection reach it at all, would be red against a correct
    implementation and would be deleted rather than fixed.

    **The control that keeps this from being vacuous**: `UNPOLICED_RELATION` is
    asserted absent from the inventory before any sample built from it is
    believed. A sweep that matched nothing at all would pass this test and fail
    the one above, which is why the pair is the unit.
    """
    inventory = policed_relations()
    pattern = reference_to(inventory)
    assert UNPOLICED_RELATION not in inventory, (
        f"{UNPOLICED_RELATION!r} is in the parsed inventory, so the samples below that use it as "
        "a relation nobody polices are not the control they claim to be. Pick another name."
    )
    assert not pattern.search(f"SELECT * FROM {UNPOLICED_RELATION}"), (  # noqa: S608
        f"The relation sweep fired on a read of {UNPOLICED_RELATION!r}, which no view in the "
        "catalog creates or is built on. A sweep that matches a relation outside its inventory is "
        "matching on something other than the inventory."
    )

    for relation in sorted(name for name in REQUIRED_IN_INVENTORY if name in inventory):
        for sample in near_misses_of(relation):
            found = pattern.search(sample)
            read = found.group(0) if found else ""
            assert not found, (
                f"The relation sweep read {read!r} out of {sample!r}, which reads no policed "
                "relation. A grant, a column named after a relation, a relation sharing its "
                "prefix, a comment and a differently-named relation all have to pass, or this "
                "sweep is red against the code it is meant to allow."
            )


IMPORTS_MUST_CATCH = (
    ("app/api/reports.py", f"import {QUERY_MODULE}"),
    ("app/api/reports.py", f"from {QUERY_MODULE} import LEAD_FACULTY_COURSES"),
    ("app/api/reports.py", "from app.views_sql import queries"),
    ("app/services/reporting.py", "from ..views_sql import queries"),
    ("app/services/reporting.py", "from ..views_sql.queries import LEAD_FACULTY_COURSES"),
    ("app/api/v1/reports.py", "from ...views_sql import queries"),
)

IMPORTS_MUST_ALLOW = (
    ("app/api/reports.py", "from app.services import authz"),
    ("app/api/reports.py", "from app.services.authz import resolve_scope"),
    ("app/services/reporting.py", "from . import authz"),
    ("app/services/reporting.py", "from ..models import Course"),
    ("app/api/reports.py", "import app.views_sql.loader"),
)


def test_the_import_matcher_resolves_every_route_to_the_query_module() -> None:
    """The import half's matcher, run against both directions before it is believed.

    **The relative forms are where a closed-set guard gets defeated one level
    out.** `from ..views_sql import queries` names no module this file could match
    literally, and a sweep that read `ast.ImportFrom.module` alone would report a
    clean tree over a module that imports the statements and runs them itself.

    The allow side keeps the ordinary import legal: `from app.services import
    authz` is the sanctioned route to exactly these rows, and a sweep that flagged
    it is one somebody deletes rather than fixes.
    """
    for where, sample in IMPORTS_MUST_CATCH:
        targets = imported_targets(ast.parse(sample), BACKEND_ROOT / where)
        assert QUERY_MODULE in targets, (
            f"`{sample}` in `{where}` resolved to {sorted(targets)}, which does not include "
            f"`{QUERY_MODULE}`. That import reaches the statements the grant functions run, and "
            "the sweep below would report the module clean."
        )
    for where, sample in IMPORTS_MUST_ALLOW:
        targets = imported_targets(ast.parse(sample), BACKEND_ROOT / where)
        assert QUERY_MODULE not in targets, (
            f"`{sample}` in `{where}` resolved to {sorted(targets)}, which includes "
            f"`{QUERY_MODULE}` and should not. A sweep that flags an ordinary import is one "
            "somebody deletes rather than fixes."
        )


# Paths that read like an exemption and are not one. Each is the shape a location
# test gets defeated by: a name that starts with an exempt module's name, a
# package that replaces one, the same file name one directory over, and — for the
# package exemption — the same directory name somewhere else in the tree.
NOT_EXEMPT_LOOKALIKES = (
    APP_ROOT / "services" / "authz_helpers.py",
    APP_ROOT / "services" / "authz" / "__init__.py",
    APP_ROOT / "services" / "dev.py",
    APP_ROOT / "api" / "dev_tools.py",
    APP_ROOT / "api" / "v1" / "dev.py",
    APP_ROOT / "api" / "views_sql" / "queries.py",
    APP_ROOT / "views_sql_helpers" / "queries.py",
    APP_ROOT / "api" / "safety.py",
    APP_ROOT / "services" / "safety_helpers.py",
    APP_ROOT / "services" / "roster_sync.py",
)


def test_the_sql_sweep_exempts_four_locations_and_no_exemption_is_a_shape() -> None:
    """The exemption list is exact, is a list of places, and is not a list of shapes.

    M8's ruling, as settled: `services/authz.py` because it is the chokepoint
    SPEC §2.1's purview rules are written in, `api/dev.py` because ADR 0100 put a
    count-only read of the enrolled figure on the development console,
    `services/safety.py` because the Care path revalidates the holds-Care rule on
    its own `pulse_care` credential and a grant function would answer on the
    wrong connection, and the `views_sql/` package because ADR 0041 puts the
    statements there and the import half below is what keeps that module to one
    importer. All four are excused for *being those locations*.

    **Why a shape cannot be the rule, asserted rather than argued.** `SELECT
    count(*) FROM enrollment WHERE section_id = :id` counts one section and
    `SELECT count(*) FROM enrollment` counts the institution, and no sweep reading
    for `count(` can tell which the next one is. So the count-only read is planted
    here at a location that is *not* exempt and asserted caught.

    **The mutations this exists to survive**: widening an exemption to a shape —
    "a statement that only counts is fine", "a statement with a `WHERE` is fine" —
    and widening it to a neighbourhood, by testing the path with `startswith`, by
    file name, or by directory name. `services/authz_helpers.py`,
    `api/v1/dev.py`, `api/safety.py` and `api/views_sql/queries.py` are in the
    lookalike list because each is what one of those loosenings would let through.
    """
    for path in SQL_SWEEP_EXEMPT_FILES:
        assert path.is_file(), (
            f"{path.relative_to(REPO_ROOT)} is exempt from this sweep and does not exist. An "
            "exemption pointing at nothing is an exemption nobody can review, and the module that "
            "took over its job is being swept under another name — or, worse, was renamed to a "
            "path this list still excuses."
        )
    assert SQL_SWEEP_EXEMPT_PACKAGE.is_dir(), (
        f"{SQL_SWEEP_EXEMPT_PACKAGE.relative_to(REPO_ROOT)} is exempt from this sweep and is not a "
        "directory. ADR 0041 puts the view SQL there, and the inventory above is read from it."
    )

    excused = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if sql_sweep_is_exempt(path)
    )
    expected = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in {*SQL_SWEEP_EXEMPT_FILES, *SQL_SWEEP_EXEMPT_PACKAGE.rglob("*.py")}
    )
    assert excused == expected, (
        f"The SQL sweep excuses {excused} under `backend/app/`, and the four locations M8 settles "
        f"on hold {expected}. Every other module in the tree runs its reads through a grant "
        "function in `services/authz.py`; a fifth excused location is a fifth place SPEC §2.1's "
        "purview can be computed by whoever wrote the query, and it belongs in the pull request "
        "that adds it with the reason beside it — the three that are not the chokepoint each "
        "carry theirs at the top of this file."
    )

    swept = parsed_modules(sql_sweep_is_exempt)
    assert swept, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)} outside the exempt "
        "locations, so this sweep looks at nothing and would report success. SPEC §13 puts the "
        "real application there."
    )

    for path in NOT_EXEMPT_LOOKALIKES:
        assert not sql_sweep_is_exempt(path), (
            f"{path.relative_to(REPO_ROOT)} is treated as exempt. It is not one of the four "
            "locations M8 names; it merely reads like one. A prefix, a file name or a directory "
            "name is how a closed set gets defeated one level out."
        )

    inventory = policed_relations()
    pattern = reference_to(inventory)
    for relation in sorted(name for name in ROSTER_RELATIONS if name in inventory):
        counting = f"SELECT count(*) FROM {relation} WHERE section_id = :section_id"  # noqa: S608
        assert pattern.search(counting), (
            f"The relation sweep did not read {relation!r} out of {counting!r}. A count is a "
            "shape, not a location: ADR 0100's console counts one section and the same statement "
            "without its `WHERE` counts the institution. Exempting the shape exempts both."
        )


# The statement each pinned exemption exists for, as the relations that file's
# own statements may name — an equality, not a floor. The reason is carried with
# the pin so a failure message can say what the exemption was granted for without
# anybody opening the module.
#
# `services/authz.py` and the `views_sql/` package carry no pin, and that is not
# an oversight. The grant functions may hold their statements in
# `app.views_sql.queries` rather than in their own text, so which of the two
# carries the SQL is a construction choice this file does not settle — and the
# chokepoint's whole job is reading these relations under §2.1's rules, so there
# is no single statement to pin it to. The import half below is what keeps that
# route to one module.
STATEMENT_PINS = (
    (
        DEV_CONSOLE_MODULE,
        ["section_enrollment_count"],
        "ADR 0100's count-only read of the enrolled figure, which that ADR requires to keep "
        "coming from the view rather than from `public.enrollment`",
    ),
    (
        CARE_REVALIDATION_MODULE,
        ["role_assignment"],
        "the Care service's own revalidation of the holds-Care rule, on the `pulse_care` "
        "credential, which is one of the four statements of that rule that move together",
    ),
)


@pytest.mark.parametrize(
    ("module", "pinned", "reason"),
    STATEMENT_PINS,
    ids=[path.stem for path, _, _ in STATEMENT_PINS],
)
def test_each_pinned_exemption_covers_exactly_the_statement_its_reason_names(
    module: Path, pinned: list[str], reason: str
) -> None:
    """An exemption excuses a file; its reason is about one statement. This is the gap.

    **The floor half** is `docs/MISTAKES.md` entry 35: a guard that only ever
    reports absence cannot tell you which mechanisms it can see. Each pinned file
    is required to be a module the sweep *would* have flagged, so a sweep that had
    gone blind to reads in real application code cannot pass this file green.

    **The ceiling half** is the finding this shape answers. An exemption granted
    for one query covers every query the module later grows, silently: a second
    read added to the development console, or the `assignment_scope` query E9 or
    E10 will want in the Care service, would each inherit an exemption written for
    something else. With the pin, both are offenders again and the failure message
    names what the file grew by.

    **The mutations this exists to survive**, in both directions: the pinned read
    disappearing from the module (the exemption excuses nothing and should go, or
    the read moved somewhere this sweep cannot see it — the same defect wearing
    the ADR's name), and the module gaining a policed read the exemption was never
    granted for.
    """
    assert module.is_file(), (
        f"{module.relative_to(REPO_ROOT)} is exempt from this sweep and does not exist, so the "
        f"exemption granted for {reason} excuses a file nobody has."
    )
    inventory = policed_relations()
    pattern = reference_to(inventory)
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))

    found = relations_named_by(tree, pattern)
    assert found == pinned, (
        f"{module.relative_to(REPO_ROOT)} runs statements naming {found}, and its exemption is "
        f"pinned to {pinned}.\n\n"
        f"The exemption exists for {reason} — one statement, not a standing licence for the "
        "module.\n\n"
        f"If {found} is the shorter list, that read is gone: the exemption now excuses nothing "
        "and should go with it, or the read has moved somewhere this sweep cannot see, which is "
        "the same defect wearing the reason's name. If it is the longer list, the module has "
        "grown a read of a relation nobody exempted it for — `pulse_app` holds an unfiltered "
        "`SELECT` on every name in the inventory, so that statement computes SPEC §2.1's purview "
        "itself. Move it to a grant function in `services/authz.py`, or widen this pin in its own "
        f"reviewed commit with the reason beside it. The inventory is {sorted(inventory)}."
    )


def test_no_module_outside_the_sanctioned_locations_runs_sql_naming_a_policed_relation() -> None:
    """The criterion, over the SQL every other module under `backend/app/` carries.

    SPEC §2.1 puts the purview rules — the supervision graph, the own grant, and
    §4.1 item 2's "a Lead Faculty assignment never grants sibling leads' courses"
    — in the `WHERE` clauses of the grant functions. The relations themselves are
    unfiltered and `pulse_app` may read all of them, so a second query written
    anywhere else is a purview computed by whoever wrote it.

    **The mutation this exists to survive:** a module gaining a direct `SELECT …
    FROM enrollment` or `… FROM lead_faculty_course` — which is not a careless
    thing to write. It is the shortest way to answer "who is in this section" or
    "which courses does this lead have", the relation is right there, and the
    query works perfectly for the person who tests it with their own id.

    **The near miss that must stay green:** naming a relation in a docstring or a
    comment, which is what a module that deliberately goes through the grant is
    expected to do.
    """
    inventory = policed_relations()
    assert inventory, (
        "The catalog yields no policed relation, so this sweep is vacuous; "
        "`test_the_policed_inventory_comes_from_the_catalog_and_holds_the_six_the_rule_names` "
        "diagnoses it."
    )
    pattern = reference_to(inventory)

    modules = parsed_modules(sql_sweep_is_exempt)
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)} outside the exempt "
        "locations, so this sweep looked at nothing and would report success. SPEC §13 puts the "
        "real application there."
    )
    assert AUTHZ_MODULE.is_file(), (
        f"{AUTHZ_MODULE.relative_to(REPO_ROOT)} does not exist, so the chokepoint this rule is "
        "written around is not there and 'every module except that one' is every module. E0-11 "
        "ships it and SPEC §2.1's purview rules live in it."
    )

    offenders = {
        str(path.relative_to(REPO_ROOT)): found
        for path, tree in modules.items()
        if (found := relations_named_by(tree, pattern))
    }
    assert not offenders, (
        f"{offenders} run SQL naming a relation the org views are built on.\n\n"
        f"The catalog under {VIEWS_SQL_DIR.relative_to(REPO_ROOT)} defines its views over "
        f"{sorted(inventory)} — `pulse_app` reads all of them unfiltered, no grant narrows them "
        "and no view filters itself — so the only thing between a caller and the whole "
        "institution is the `WHERE` clause inside `backend/app/services/authz.py`'s grant "
        "functions, where SPEC §2.1's purview rules and §4.1 item 2's sibling-isolation rule are "
        "written.\n\n"
        "A query written anywhere else applies whichever of those rules its author remembered. If "
        "a read path genuinely needs one of these relations, it goes through the grant function "
        "that already narrows it; if a new grant function is needed, it belongs in `authz.py` "
        "beside the others, which is what makes this rule one file to review. The only other "
        "answer is a fifth exempt location, which is a decision to make in the open with the "
        "reason beside it — never a shape added to what this sweep tolerates. "
        "`services/safety.py` is the one that has been made: the Care path revalidates the "
        "holds-Care rule on its own `pulse_care` credential, so a grant function in `authz.py` "
        "would answer it on the wrong connection."
    )


def test_no_module_outside_the_grant_chokepoint_imports_the_view_query_module() -> None:
    """The other route to the same rows, which names no relation in the importing module.

    `backend/app/services/authz.py` calls this property a control. It was one only
    as long as somebody grepped for it: importing `app.views_sql.queries` and
    running one of its statements on a session of your own reaches exactly the
    unfiltered relations the test above is about, and the module doing it contains
    no SQL for that sweep to read.

    **The mutation this exists to survive:** a module outside `authz.py` importing
    `queries` — by any of the forms `imported_targets` resolves, including the
    relative ones, since `from ..views_sql import queries` is what somebody inside
    `services/` would naturally write.

    **The near miss that must stay green:** importing `app.services.authz` itself,
    which is the sanctioned way to reach these rows and must not be flagged.
    """
    modules = parsed_modules(import_sweep_is_exempt)
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)} outside the exempt "
        "ones, so this sweep looked at nothing and would report success."
    )

    importers = sorted(
        str(path.relative_to(REPO_ROOT))
        for path, tree in modules.items()
        if QUERY_MODULE in imported_targets(tree, path)
    )
    assert not importers, (
        f"{importers} import `{QUERY_MODULE}`, which holds the statements the grant functions run "
        "against relations `pulse_app` may read in full. `backend/app/services/authz.py` is the "
        "one module that may: it is where the `WHERE` clauses implementing SPEC §2.1's purview "
        "live, and one importer is what makes 'read the scoping rules in one file' true.\n"
        "An importer here has the statements and supplies its own session and its own parameters, "
        "so whatever scoping it applies is its own. The sanctioned route is to call the grant "
        "function in `authz.py`; if the function it needs does not exist yet, it belongs there."
    )
