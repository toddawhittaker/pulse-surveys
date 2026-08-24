# QUALITY-REVIEW-CLEANUPS-01 — `db.py` cannot be moved onto the shared `is_development` predicate without failing the E0-37 sweep

**Ticket:** the quality-review cleanups batch, item 3 ("One is-development
predicate"). There is no ticket file; the dispatch brief is the ticket, and the
relevant sentence of it is quoted under "What I tried" below.

**Test:**
`tests/unit/test_development_environment_has_one_definition.py::test_the_engine_and_the_seed_read_the_development_environment_name_rather_than_spelling_it`

## The test

The failing assertion, and the detector it calls:

```python
def reads_the_constant(tree: ast.Module) -> bool:
    """Whether the module gets the name from somewhere rather than declaring it.

    Both spellings, because the ticket asks for one definition and not for one
    import style: the name imported directly, or read as an attribute of the
    configuration module. A module doing neither either has its own copy or does
    not care about the environment at all, and the caller says which.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == CONSTANT for alias in node.names):
            return True
        if isinstance(node, ast.Attribute) and node.attr == CONSTANT:
            return True
    return False
```

```python
def test_the_engine_and_the_seed_read_the_development_environment_name_rather_than_spelling_it() -> (
    None
):
    """The criterion's second half, for the two modules that carried a copy.

    A module can satisfy the sweep above by holding the value without binding a
    name to it — `if settings.environment == "development":` is a copy with no
    assignment. So both files are required to hold no bare `"development"` at
    all, and to read the name from somewhere.

    Both halves, because either alone is satisfiable the wrong way. A module that
    imports the constant *and* keeps its old literal comparison has two answers
    and uses the older one; a module that holds no literal because it stopped
    caring about the environment has lost a behaviour rather than fixed a
    duplication, and the tests that own those behaviours —
    `test_db_engine_configuration.py` for the engine, `test_seed_target_is_enforcing.py`
    and `test_demo_seed_script.py` for the seed — are what would go red for that.

    **The mutation this survives:** restore either literal, in either file.
    **The near miss that must stay green:** a docstring or an error message that
    contains the word development inside a longer sentence, which is not a
    spelling of the value and is not matched.
    """
    for relative in (ENGINE, SEED):
        tree = parsed(relative)

        literals = literals_of_the_development_name(tree)
        assert not literals, (
            ...
        )

        assert reads_the_constant(tree), (
            f"`{relative}` holds no {DEVELOPMENT!r} literal and never reads `{CONSTANT}` either, "
            "so it has stopped asking which environment it is running in rather than started "
            f"asking `{CONFIGURATION}`.\n"
            "\n"
            "Both readers have a rule that depends on the answer: the engine hides bound "
            "parameters outside development (E0-37 item 1) and the seed refuses to run against a "
            "deployment (ADR 0063). A module that no longer consults the environment has dropped "
            "one of those, and this assertion is here so that dropping it cannot be how the "
            "duplication above gets resolved."
        )
```

`CONSTANT` is `"DEVELOPMENT_ENVIRONMENT"`, `ENGINE` is `"backend/app/db.py"`,
`SEED` is `"scripts/seed.py"`, `CONFIGURATION` is `"backend/app/config.py"`.

The measured failure, with `backend/app/db.py` converted exactly as the brief
directs — `_is_development` deleted, `from app.config import Settings,
is_development`, and the three call sites calling `is_development(settings)`:

```
FAILED tests/unit/test_development_environment_has_one_definition.py::test_the_engine_and_the_seed_read_the_development_environment_name_rather_than_spelling_it
AssertionError: `backend/app/db.py` holds no 'development' literal and never reads
`DEVELOPMENT_ENVIRONMENT` either, so it has stopped asking which environment it is
running in rather than started asking `backend/app/config.py`.
1 failed, 2 passed in 0.13s
```

## What I believe it asserts incorrectly

`reads_the_constant` treats "reads the one definition of the development
environment" as "mentions the identifier `DEVELOPMENT_ENVIRONMENT`". Those were
the same thing on the day E0-37 item 2 was written, because the only way to get
the answer out of `app.config` was to import the string and compare it yourself.
They are no longer the same thing if `app.config` also exports the comparison.

A module that calls `app.config.is_development(settings)` has not "stopped asking
which environment it is running in", which is the state the assertion's own
message describes. It is asking `backend/app/config.py`, through a function
`backend/app/config.py` owns, which reads
`backend/app/config.py`'s single `DEVELOPMENT_ENVIRONMENT`. That is strictly more
of what E0-37 item 2 wanted than the import was: after the conversion, the *shape*
of the comparison lives in one place too, not just the value.

The detector cannot distinguish that from the state it exists to catch, and the
two failure directions it is guarding are both still closed by other tests it
names itself — `test_db_engine_configuration.py` owns whether the engine still
echoes and hides parameters correctly, and it stays green over the conversion.

## The spec text I am relying on

`docs/SPEC.md` is silent. `ENVIRONMENT` appears zero times in it — the test's own
subject module says so, in `backend/app/config.py`:

> # The one `ENVIRONMENT` value that turns on a developer convenience. Free-form,
> # and **not** an enumeration `Settings` enforces — `ENVIRONMENT` appears zero
> # times in `docs/SPEC.md`, so this is a comparison against a convention
> # `.env.example` documents. Anything that is not this exact string is treated as
> # a deployment.

So this is not a spec question. The governing text is the test module's own
docstring, which states the criterion it means to enforce and then draws a line
that this case falls on the far side of:

> **What it does not assert.** Not the import *spelling* — `from app.config import
> DEVELOPMENT_ENVIRONMENT` and an attribute read off the imported module are both
> "read it from the one place", and choosing between them is style rather than the
> criterion. Not the constant's value either: what matters is that there is one of
> it, and `test_config_settings.py` owns what `ENVIRONMENT` may be.

"What matters is that there is one of it" is satisfied by the conversion. The
docstring declines to legislate import spelling and then legislates it anyway, by
enumerating two spellings and rejecting a third that did not exist yet.

## What I tried

The brief settles item 3 as:

> **3. One is-development predicate.** Add `def is_development(settings: Settings)
> -> bool` to `backend/app/config.py` next to `DEVELOPMENT_ENVIRONMENT` (line
> 104). Convert the four Settings-typed spellings to call it: main.py:65 (inside
> `documentation_is_served`, which keeps its name and delegates), db.py:111-121
> (delete `_is_development`, call the config one at its call sites
> db.py:134/158/196), api/dev.py:278 (`not is_development(...)`), api/deps.py:143
> (`secure=not is_development(settings)`).

Three of those four conversions are done and green: `main.py`, `api/dev.py` and
`api/deps.py` are not swept by this test, which reads only `ENGINE` and `SEED`.
Only `db.py` is in dispute.

I attempted the `db.py` conversion exactly as briefed and measured the red above.
I then looked for a way to satisfy both the brief and the detector, and there is
none that is not gaming it:

- Importing `DEVELOPMENT_ENVIRONMENT` alongside `is_development` and not using
  it fails `ruff` (`F401`), and would be a name imported solely to be seen by a
  test.
- Reaching the predicate as `config.is_development(...)` after `from app import
  config` produces an `ast.Attribute` whose `attr` is `is_development`, not
  `DEVELOPMENT_ENVIRONMENT`, so the detector still answers no.
- Keeping a one-line `_is_development` in `db.py` that delegates to the config
  predicate leaves the duplication item 3 exists to remove, and still does not
  name the constant.

I have **not** edited the test, and I have reverted `backend/app/db.py` to its
committed state, so the branch is green and `db.py` still carries its own
`_is_development`. Item 3 is therefore three-quarters done and says so in its
commit message.

## Why I believe the test rather than my code is at fault

The test asserts a proxy, and the proxy has come apart from the property. The
property is "there is one definition of what counts as development, and every
reader gets its answer from that one place". The proxy is "the reader's source
text contains the identifier". Converting `db.py` onto a predicate that
`app/config.py` exports makes the property *more* true and the proxy false, which
is the signature of a proxy that has outlived its formulation.

The concrete cost of leaving it as it stands is the one `docs/MISTAKES.md` entry
13 describes and that this very test was written about. There are now five places
in the tree that ask "is this development", and after this batch four of them go
through one predicate while `db.py` keeps a private second implementation of the
same comparison — which is the two-spellings-of-one-convention shape, one level up
from the string. The comparison is trivial today, so the drift risk is small; the
argument is about which of the two rules the repository wants to be enforcing.

**The honest counter-argument, which the arbitrator should weigh.** The test may
mean its criterion literally and locally: `db.py` is the module where E0-37 item 1
decided whether bound parameters are hidden, and requiring the value that decides
that to be *named in the file that decides it* is a defensible locality rule
rather than a stale proxy. Under that reading my change is the wrong one and item
3 should stop at three call sites permanently, with `db.py`'s `_is_development`
kept and a comment saying why it is not merged. I do not think that is what the
docstring says, but it is a coherent position and it is cheap.

I think this is an **outcome 3** shaped question rather than outcome 1 or 2: the
brief settled item 3 without knowing this sweep existed, and somebody has to
decide which rule E0-37's criterion actually is. Either ruling is one small edit
from here.
