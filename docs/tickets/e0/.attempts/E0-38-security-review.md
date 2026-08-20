# E0-38 — independent security review (PR #48)

Reviewer: a Claude Code session separate from the one that built the ticket.
Date: 2026-08-19.

## What was reviewed, and how it was scoped

    working directory: /home/todd/projects/pulse-surveys
    diff:              git diff origin/epic/e0-foundations...e0/ci-docs-path-filter
    merge base:        3f62eb52268eb3fc98eaeff2a652e27674c97a67
    file count:        10

The ten files are `.github/workflows/ci.yml`, `scripts/ci/classify_changed_paths.py`,
`scripts/ci/test_ci_scripts.py`,
`tests/unit/test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`,
and six documentation files.

**The `/security-review` scoping defect fired again.** Run as-is, the skill
resolved its base to the repository default (`main`) rather than the pull
request's base, and handed itself roughly 370 files and a 5.9 MB diff — the whole
repository. That pass was discarded and the checklist was worked by hand against
the ten-file diff above. Same defect as PR #43.

Two passes were run, both named:

1. **Generic pass** — `/security-review`, discarded for the reason above and
   redone by hand against the correct diff.
2. **Gated specialists** — `spec-conformance` (fires on every pull request) and
   `app-security` (its usual triggers do not fire on this diff; run anyway
   because the diff modifies the control that decides whether five gates run).

Findings were reproduced by executing the code, not by reading it. The two HIGHs
came from different passes and neither pass found both, which is the argument for
having run both.

## Findings

### HIGH 1 — repository-wide sweeps live inside the job the classifier switches off

`scripts/ci/classify_changed_paths.py` (`INERT_DIRECTORIES`), and
`.github/workflows/ci.yml` (the `test` job).

The reasoning behind the inert set is that nothing in `docs/` or `design/` is
imported, executed, packaged or linted. That is true of those files as *inputs*.
It is not true of them as *subjects*: this suite holds guards that sweep the
whole repository, they cover `docs/**` and `design/**`, and they run only in the
`test` job — one of the five this change switches off. On a documentation-only
diff the guard whose whole job is to look at documentation is the guard that does
not run.

Two live instances, both verified.

**`tests/unit/test_no_unresolved_merge_conflicts.py`** enumerates through
`git ls-files -z`, so it covers every tracked file including all of `docs/`. A
merge that leaves `<<<<<<<` in `docs/MISTAKES.md` and touches nothing else is
classified inert, the `test` job prints its notice and skips both pytest steps,
and `CI` reports success with the markers committed. That is `docs/MISTAKES.md`
entry 21 exactly — commit `7f5b300` on PR #24, then again on PR #27, same file —
and entry 21's own root cause is that nothing in the build reads a Markdown file.
This sweep is the answer that incident produced, and this change switches it off
on precisely the diffs it was written for.

**`tests/unit/test_mock_lms_service.py::test_no_private_key_material_is_committed_to_the_repository`**
walks the working tree from the repository root, pruning only caches and `.git`,
so it too covers `docs/` and `design/`. Demonstrated in an isolated copy of the
tree: writing a PEM header into `docs/leaked-key.md` turns the sweep red —

    E   assert not [PosixPath('docs/leaked-key.md')]
    FAILED tests/unit/test_mock_lms_service.py::test_no_private_key_material_is_committed_to_the_repository

— while the classifier calls the same one-path diff inert:

    $ python3 scripts/ci/classify_changed_paths.py docs/leaked-key.md ; echo $?
    inert: all 1 changed path(s) are documentation nothing depends on:
      docs/leaked-key.md
    0

So a pull request that commits private key material under `docs/` or `design/`
and touches nothing else gets a green `CI` from a job that declined to look.
CLAUDE.md's secrets policy is explicit that a credential must never be written
into a fixture, a seed script or a log line; this is the mechanical check behind
that policy, and it goes dark on the diff shape most likely to carry a pasted
key.

**What someone would have to do.** Nothing deliberate. Both instances are
ordinary-mistake shapes: a conflicted merge of a documentation file committed
without reading it, or a key pasted into an ADR or a ticket note. No attacker is
required, which is what makes this the more serious of the two HIGHs.

**Consequence for the records.** ADR 0070 and the PR body both say the failure
mode of a wrong classification is a slow pipeline rather than a skipped gate.
That is not true as written, and it should be corrected in the same pull request
as the fix rather than left to be rediscovered.

**Fix.** The class matters more than the two instances: a guard whose subject is
"every tracked file" cannot live in a job that a subset of tracked files can
switch off. The smallest repair that closes both is to run these sweeps in a job
that is never gated. `lint-python` already runs unconditionally and already
installs the dev dependencies for mypy, so one step there —

    pytest tests/unit/test_no_unresolved_merge_conflicts.py \
           tests/unit/test_mock_lms_service.py -q

— costs seconds and holds on every diff. `ci-selftest` is the other candidate but
runs a plain script rather than pytest, so it would need more wiring.

Whatever is chosen, the durable half is a guard against the next such sweep. The
existing `PARSED_DOCUMENTS` sweep cannot serve: it collects `Path` division
chains out of the AST, and neither of these modules builds a path — one goes
through `git ls-files`, the other through `root.walk()`. That blind spot is named
in the abstract at the sweep's docstring, and two live instances are already
sitting in it. A second sweep asserting that no test enumerating `git ls-files`
or walking the repository root lives in a gated job would have caught both.

### HIGH 2 — a root file whose name begins with `-h` turns five gates off

`.github/workflows/ci.yml` (the classifier invocation in the `changed` job) and
`scripts/ci/classify_changed_paths.py` (`main`).

The workflow invokes the classifier as

    python3 scripts/ci/classify_changed_paths.py "${changed[@]}"

with no `--` separator, and `changed` comes straight from
`git diff --name-only -z`. `argparse` therefore parses the changed-path list
looking for options. A path that argparse resolves to its built-in help option
prints usage and **exits 0**, which the shell reads as the classifier's "inert"
answer.

Reproduced end to end in a scratch repository under `/tmp`, using the same
`git diff --no-renames --name-only -z`, `mapfile -t -d ''` and invocation the
workflow uses:

    path: -h
    path: backend/app/main.py
    usage: classify_changed_paths.py [-h] [paths ...]
    ...
    STATUS=0  -> inert=true

A commit adding an empty root file named `-h` alongside any code change emits
`inert=true`. The `test` job then short-circuits every step — pytest, the
coverage run, **and the §4.1 invariant suite with `check_invariants.py` and
`check_invariant_assertions.py`** — and reports success. `docker`, `e2e`, `evals`
and `supply-chain` do the same. The aggregate `CI` check sees seven successes and
goes green. CLAUDE.md says the invariant suite may never be skipped precisely
because a skip and a passing assertion are indistinguishable in a green
checkmark; this skips it and reports success.

**The dangerous class is wider than `-h` and `--help`.** Measured:

| path handed to the classifier | exit | read as |
|---|---|---|
| `backend/app/main.py -h` | 0 | inert |
| `backend/app/main.py --help` | 0 | inert |
| `-hx` | 0 | inert |
| `--hel` | 0 | inert |
| `-q`, `--no-such` | 2 | not inert (the `*)` warning branch) |
| `--`, `-`, `backend/app/main.py --` | 1 | not inert |

`-hx` exits 0 because argparse reads it as a cluster of short options beginning
with `-h`; `--hel` exits 0 through argparse's prefix abbreviation of `--help`. So
the class is any repository-root file named `-h…`, or `--h`/`--he`/`--hel`/
`--help`. `-hotfix`, `--header` and `-h.md` are all in it. Only root-level files
qualify: `docs/-h` arrives as `docs/-h`, which has no leading dash.

**What someone would have to do.** Commit a file named `-h` at the repository
root in the same push as the code change — a fork pull request needs no write
access. There is a plausible accidental route too: `curl -o -h …` or a redirect
into `-h`, then `git add -A`.

Every near-miss fails safe, which is why the existing batteries did not catch it:
any other leading-dash path exits 2 and the `case` block routes that to
`inert=false`. Only argparse's zero-exit options are dangerous, and neither test
file has a leading-dash case at all.

**Fix.** One token in `ci.yml`:

    python3 scripts/ci/classify_changed_paths.py -- "${changed[@]}"

Verified: with `--`, a leading-dash path alongside a code file, a bare `-h`, a
bare `--help` and a bare `--` all return exit 1, and an ordinary inert diff still
returns 0. Worth doing both halves — add the separator, and have the classifier
reject an argument beginning with `-` outright — because the separator lives in
the workflow while the classifier's docstring advertises a general
`<changed path>...` command line and does not say the caller must supply it. Add
the case to `scripts/ci/test_ci_scripts.py` as well as the pytest module, since
the pytest module is in the job the classifier can switch off.

### MEDIUM 1 — on a push to an epic branch the verdict becomes incremental while the tree does not

`.github/workflows/ci.yml`, the `case` selecting `PUSH_BEFORE`.

The workflow also runs `on: push: branches: ['epic/**']`, where the base is
`github.event.before` — the previous branch tip. `git diff before HEAD` therefore
covers only the newly pushed commits, not the state of the branch.

So: a ticket merges into the epic branch and its gates go red. A documentation
ticket merges next — an ADR, a MISTAKES entry, a ticket note. `before` is now the
red commit, `HEAD` the documentation merge, every path in the two-dot diff is
inert, and `test`, `e2e`, `evals`, `docker` and `supply-chain` all short-circuit
and report success. `CI` is green on a branch head that still contains the code
those gates failed on. Before this change every push ran the gates against the
whole tree, so a broken tree stayed red until it was fixed.

Given this repo's own workflow — every ticket reaches an epic branch as a merge
commit, and documentation-only tickets are common enough that E0-38 counts six of
them — this is reachable without anyone doing anything unusual.

MEDIUM rather than HIGH because pull requests are unaffected:
`pull_request.base.sha` gives the whole delta, so the code always reappears in
the ticket-into-epic and epic-into-`main` pull requests and the gates always run
there. Only the epic branch's own head badge lies, and `main` is still protected
by a full run.

**Fix.** The simple one is to emit `inert=false` for every `push` event and let
the filter apply to pull requests alone. That is where the fifteen minutes E0-38
measured were actually being spent, so it gives up little. Nothing in either test
module covers this shape; the module does exercise a push case, but with a base
that makes the answer come out right.

### MEDIUM 2 — two of the five short-circuited jobs say nothing when they decline

`.github/workflows/ci.yml`, the `e2e` and `evals` jobs.

`test`, `docker` and `supply-chain` each gained a "Documentation-only diff"
notice step. `e2e` and `evals` gained guards but no notice. ADR 0070's
consequences say the `::notice::` line in each short-circuited job is the only
thing that says which gates declined, and the PR body's push instruction says to
expect a notice in each of the five. Both are false for two of the five.

Today those jobs instead print "No `tests/e2e` specs yet" and "No eval sets yet",
which are statements about the tree rather than about the diff — so the
scratch-branch check for criterion 1 would pass on a notice that means something
else. After E0-18 lands, `detect.e2e` becomes true, that step switches off, every
work step is off, and the job prints nothing at all: a green gate with no line
anywhere recording that it declined to look.

Two notice steps, copied from the three that have them.

### MEDIUM 3 — `frontend-build` is a sixth expensive job and is guarded by nothing

`.github/workflows/ci.yml`, the `frontend-build` job.

It runs `npm ci`, a production build and the bundle budget. It has no `changed`
guard and is named nowhere — not among the five to short-circuit, not among the
jobs deliberately left running, not in ADR 0070 — while the PR body says nothing
is deferred.

It is free today only because `detect.frontend` is false. When the frontend
scaffold lands, documentation-only pull requests will run a production build
again and part of the saving quietly disappears, with no record saying it was a
decision. Either guard it or name it in the PR body and the ADR as the one
expensive gate deliberately left out. The unguarded direction is the safe one, so
this is about the record as much as the runner time.

### LOW 1 — the sweep that guards `PARSED_DOCUMENTS` reads one idiom only

`tests/unit/test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`,
`repository_paths_named_in`.

The guard is load-bearing rather than self-confirming — see the answer to
question 2 below. But it recognises only `Path` division chains rooted at the
`…parents[N]` idiom. Tested by planting a module under `tests/unit/` in an
isolated copy of the tree:

| how the planted module names the document | sweep |
|---|---|
| `REPO_ROOT = Path(__file__).resolve().parents[2]` then `REPO_ROOT / "docs" / "MISTAKES.md"` | **fails, correctly**, naming file and module |
| `Path("docs/MISTAKES.md")` — a bare string literal | passes |
| `pytestconfig.rootpath / "docs" / "MISTAKES.md"` | passes |

The bare-literal blind spot is deliberate and the docstring says why: `README.md`
and `docs/MISTAKES.md` both appear as literals in this suite for reasons
unrelated to reading them, so collecting literals would produce false failures.
That trade is defensible.

The `pytestconfig.rootpath` blind spot is not documented. It is not exploitable —
it needs a future author to use an idiom no module here currently uses — but it
is the silent widening the sweep exists to prevent. A sentence in the docstring
naming the idiom the sweep reads, and the ones it does not, would make the guard
honest about its own scope. Extending `is_repository_root` to accept `rootpath`
attributes is also small.

Related: the sweep walks `tests/` only. Nothing under `scripts/`, `backend/` or
the mocks reads a `docs/` file today — checked — so there is no live instance,
but a CI script that started parsing a document would not be covered.

Note that HIGH 1 sits in this blind spot. That is the argument for the extra
sweep proposed there rather than for widening this one.

### LOW 2 — `..` segments are classified inert

`scripts/ci/classify_changed_paths.py`, `is_inert`.

`is_inert` matches on the raw string, so `docs/../backend/app/main.py`,
`design/../pyproject.toml` and `docs/x/../../Makefile` all return inert
(confirmed by running it). Not reachable today: the only caller is the `changed`
job, and `git diff --name-only` from the repository root emits normalised
repository-relative paths and never a `..` segment.

It becomes live the moment a second caller appears — a Makefile target, a
pre-push hook, a future job — because the docstring advertises a general
`<changed path>...` command line and says nothing about the input needing to be
normalised. One line rejecting any path with a `..` component closes it
permanently and costs nothing. Worth folding into the same commit as HIGH 2,
since both are about the classifier trusting its argv.

### LOW 3 — a fork pull request supplies the classifier that decides its own gates

`.github/workflows/ci.yml`, the `changed` job.

`on: pull_request` checks out the merge commit, so on a fork pull request
`scripts/ci/classify_changed_paths.py` is the contributor's copy. Editing it to
return 0 unconditionally produces `inert=true` and a green `CI` with every job
name still present.

Not introduced here — a fork could already edit `ci.yml` to hollow out the `test`
job, and GitHub runs the pull request's own workflow file. What changes is that
the bypass now fits in a small helper rather than in the workflow file a reviewer
reads closely. The mitigation is process, not code, and it does not block this
pull request. Worth one line in ADR 0070's consequences so it is recorded rather
than rediscovered.

### LOW 4 — `design/**` is inert and is a build input in waiting

`scripts/ci/classify_changed_paths.py`, `INERT_DIRECTORIES`.

Nothing consumes `design/` today; every reference from `.py`, `.yml`, `.sh`,
`Makefile` and `pyproject.toml` was checked and all are prose citations. But
`design/tokens.css` is named by `docs/DESIGN_BRIEF.md` and by CLAUDE.md's
read-before-you-touch table as the token source for any UI work, and
`design/support.js` exists. The first commit that has the frontend import either
one makes a shipped asset inert, and no guard would notice — the
`PARSED_DOCUMENTS` sweep looks for documents the test suite opens, not assets the
frontend imports.

No action needed in this pull request. A sentence in ADR 0070's consequences puts
it where whoever wires the frontend to `design/tokens.css` will meet it.

### LOW 5 — the PR body describes the prompt Markdown as an exception to `docs/**`

`PARSED_DOCUMENTS` holds `docs/SPEC.md` alone.
`backend/app/ai/prompts/validity.v1.md` is not an exception to `docs/**` — it is
outside every inert family and never reaches that check, because the root-Markdown
rule is `"/" not in path`. The classifier's own docstring gets this right; the PR
body does not. Someone maintaining the exception list later will look for a prompt
entry that is not there.

### LOW 6 — `docker`'s teardown runs on an inert run

"Compose logs on failure" (`if: failure()`) and "Tear down" (`if: always()`) are
unguarded. On an inert run the teardown executes `docker compose down -v || true`
against a stack never brought up and a `.env` never copied. Harmless because of
`|| true`, and the wiring test cannot see it because `EXPENSIVE_GATES["docker"]`
matches only `docker compose … build|up`. Noted for completeness, not worth a
change.

## Checked and clean

- **Script injection through a filename.** The `changed` job's `run:` block
  contains no `${{ }}` interpolation at all. `github.event_name`,
  `github.event.pull_request.base.sha` and `github.event.before` arrive through
  `env:` and are quoted at every use. Filenames never reach the shell as text:
  NUL-delimited into a file, read with `mapfile -d ''`, expanded as a quoted
  array, printed with `printf '%s'` against a literal format. A filename holding
  `$(...)`, a backtick, a quote, a newline or a space is harmless here. This part
  is done properly.
- **Trigger and permissions.** `on: pull_request` plus `push: branches:
  ['epic/**']`. No `pull_request_target` anywhere in `.github/`. One
  workflow-level `permissions: contents: read`, no job-level override in any job,
  so nothing widens the token. No `secrets.*` expression exists in the file.
- **Every failure path in the shell falls toward the full run.** Traced: an empty
  base; the all-zero `before` a new branch pushes; a base commit absent from the
  clone (force push, shallow clone); `git diff` exiting non-zero; `mapfile`
  exiting non-zero; the classifier exiting 2 or anything else. All six emit
  `inert=false`. An empty path list reaches the classifier as zero arguments and
  returns 1. If `GITHUB_OUTPUT` were unset, `set -u` kills the step, the
  dependent jobs report `skipped`, and E0-36's aggregate treats `skipped` as
  failure. **HIGH 2 is the only route to `inert=true` other than a diff the
  classifier genuinely reads as inert.**
- **The diff computation on a pull request.** `git diff base HEAD` is two-dot
  against the merge commit with `fetch-depth: 0`. Because the merge commit has
  the base as a parent, this equals the three-dot diff. Every way `base.sha` can
  be stale relative to the merge ref makes the path list *larger*, never smaller.
  A force push leaves `before` unreachable and the `git cat-file -e` guard
  catches it. The push case is MEDIUM 1 above.
- **`--no-renames` is present on the live command and is load-bearing.** Without
  it, `git mv backend/app/services/authz.py docs/whatever.md` arrives as one
  inert destination path. The comment explaining it is accurate.
- **Case and unicode.** `Docs/x.md` and `DOCS/x.md` are not inert; `docsX/foo`
  and a bare `docs` are not inert. Runners are Linux, so case is respected.
- **Submodules.** There is no `.gitmodules`, so the submodule-pointer case does
  not arise.
- **`PARSED_DOCUMENTS` completeness.** Swept for code that opens a `docs/` file
  at run time. `docs/SPEC.md`, read by `tests/unit/test_ai_contracts.py`, is the
  only one. The list is complete as of this commit. Prompt Markdown under
  `backend/app/ai/prompts/` is correctly outside the inert set.
- **Allowlist rather than denylist.** `.github/**`, `scripts/**`,
  `requirements*.txt`, `docker-compose*.yml`, `pyproject.toml` and an unheard-of
  path are all non-inert.
- **Guard coverage and guard sense across the five jobs.** Every step was walked
  from the parsed YAML. Every work step reads
  `needs.changed.outputs.inert != 'true'`; every notice step reads `== 'true'`;
  the three compound conditions have the right sense in both halves. No reversed
  guard, and no heavy work step left ungated. `changed` is correctly absent from
  `ci`'s `needs`.
- **The escalation into `ci-selftest` holds for the classifier's own behaviour.**
  `ci-selftest` declares no `needs` and no `inert` condition, so
  `scripts/ci/test_ci_scripts.py` runs on every pull request including an inert
  one, and it invokes the classifier as a subprocess rather than importing
  `is_inert`, so it does cross the command-line boundary. All six unclassified
  paths, all seven inert families, the spec case, the `.py` case, both orders of
  a mixed diff and the empty diff are duplicated. The guards not duplicated — the
  AST sweep, the workflow-wiring assertions, the `bash -e` harness, the rename
  case — all have subjects under `tests/**`, `scripts/**` or
  `.github/workflows/ci.yml`, none of which is inert, so each fires on the diff
  that would break it. That closure argument is right and it holds. What the
  self-test lacks is an option-shaped case, which is why HIGH 2 survived it.
- **Both batteries are green** on this commit: 15 passed in the pytest module,
  and `OK: 100 checks passed.` from the self-test.
- **`/tmp/changed-paths.z` is a fixed path.** Fine on ephemeral GitHub-hosted
  runners; would want `mktemp` if self-hosted runners are ever adopted. Not
  raised as a finding.

## The two questions the ticket asked

### Is accepting `README.md` as both inert and a build input right?

Confirmed as described: `pyproject.toml` declares `readme = "README.md"` and
`backend/Dockerfile` has `COPY pyproject.toml README.md ./`.
`tests/unit/test_prompt_directory_layout.py` already holds `"README.md"` in a
`BUILD_INPUTS` tuple, so the suite knows this.

Split the case in two, because the halves are not alike.

**Editing `README.md` is fine.** The content lands in wheel metadata and nothing
tests it. Skipping the image build on a README edit gives up nothing real.

**Deleting `README.md` is the case that bites**, and it bites on a later,
unrelated pull request. The deleting pull request is classified inert, `docker`
short-circuits, and the broken `COPY pyproject.toml README.md ./` first appears
on whichever pull request next touches code. That author sees a Dockerfile
failure with no connection to anything in their diff.

I would not call this hidden. The failure is loud, immediate on the next
code-touching pull request, and the error names the missing file. It is delayed
and misattributed, not silent. Accepting it is defensible.

That said, I would take `README.md` out of the inert set, and it is close to
free. The rule becomes root Markdown except `README.md`, one line beside the
`docs/SPEC.md` exception. What it costs is the saving on README-only pull
requests, which are rare — the six inert pull requests this epic produced were
tickets, ADRs and mistakes files, not README edits. What it buys is that a
declared build input is never in the set that switches the build off, which is a
rule that can be stated without a paragraph of qualification. Note the classifier
deliberately never touches the filesystem, so it cannot tell a deletion from an
edit; the choice really is binary.

This is a judgment call and could go either way. If `README.md` stays inert, ADR
0070's consequences already record it honestly, and that is the minimum.

### Is the `PARSED_DOCUMENTS` guard load-bearing, or self-confirming?

**It is load-bearing.** Keeping the derivation on the guard's side rather than in
the classifier was the right call.

Verified by mutation in an isolated copy rather than by reading it. Planting a
module under `tests/unit/` that names `docs/MISTAKES.md` through the standard
`REPO_ROOT / "docs" / "MISTAKES.md"` idiom turns
`test_nothing_the_test_suite_opens_by_path_is_classified_inert` red, and the
failure names both the document and the module reading it, and says the repair is
to except the file rather than to stop reading it. Baseline on the unmutated copy
passes, so the red is caused by the plant and not by the copy.

But you asked whether you had fooled yourself, and the honest answer is: not
about this guard, and yes about the thing next to it. The guard is sound within
its scope, and its scope is narrower than the property it appears to protect. It
answers "does a test *open* a document that is called inert?" The property that
actually matters is "does a test *make an assertion about* a file that is called
inert", and HIGH 1 is two live instances of the second that are invisible to the
first, because a sweep enumerating `git ls-files` or walking the repository root
builds no path for the AST to collect. The reservation in LOW 1 about which
idioms the sweep reads is the small version of that; HIGH 1 is the large version.

## Verdict

Two HIGHs, three MEDIUMs, six LOWs. Neither HIGH blocks in the sense of being
hard to fix — HIGH 2 is a two-character change plus a regression case, and HIGH 1
is one unconditional step plus a correction to ADR 0070 and the PR body — but
both need to land before this is merged, because each makes `CI` report success
over work it did not do.

The fail-closed reasoning through the shell is careful and I could not find a
second way past it. Neither HIGH is a hole in that reasoning. HIGH 2 is
underneath it, in a layer the reasoning never reaches, since `argparse` answers
before `main` runs. HIGH 1 is beside it: the reasoning is about `docs/` as an
input to the build, and the gap is `docs/` as a subject of the tests.

---

# Second pass — the fix round

**Diff reviewed:** `git diff a7419ad..b1bbb37`, nine files, 1225 insertions — the
count matches. **Working directory:** the shared checkout at
`/home/todd/projects/pulse-surveys` for reading, and a detached worktree at
`b1bbb37` under this session's scratchpad for every mutation. No `/security-review`
pass was used: it resolves its base to `main` and would have re-read the whole
branch. This is a hand review of that range only.

**Standing caveat.** I wrote the first report. The distinction it drew —
documentation as a build *input* versus documentation as a *subject* — is now in
the workflow comments, in ADR 0070, in the guard's name and in the commit
messages. I can test whether the fixes work. I cannot test whether that
distinction is the right cut, and a section at the end names every place where it
is the thing holding the fix up.

## Half one — the five findings, tested by mutation

Every mutation was applied in the scratchpad worktree, run, and reverted from a
file snapshot rather than by `git checkout`. Baseline before and after: 18 passed.

### HIGH 1 — a repository-wide sweep inside a job the filter switches off — **closed**

Three mutations, three kills, plus an end-to-end check that the sweeps actually
fire on a `docs/` offence.

- Removing the two private-key node ids from the `lint-python` step fails
  `test_every_repository_wide_sweep_runs_in_a_job_the_filter_cannot_switch_off`
  with `tests/unit/test_mock_lms_service.py (uses .walk() from the repository
  root, git ls-files)`.
- The blind spot named in the brief is genuinely gone. Rewriting the single
  `ls-files` occurrence in `test_mock_lms_service.py`'s docstring to "enumerating
  the index" *and* removing the node ids still fails, now reporting `.walk() from
  the repository root` alone. The `root` widening is doing the work, not the
  string.
- Appending a conflict marker to `docs/MISTAKES.md` turns
  `test_the_index_holds_no_conflict_marker` red. Appending a PEM private-key
  header to `docs/adr/0070-…md` turns
  `test_no_private_key_material_is_committed_to_the_repository` red. Both offences
  live in paths `classify_changed_paths.py` calls inert, and both node ids now run
  in `lint-python`, which has no `if:` and does not need `changed`.
- The three node ids run standalone with `DATABASE_URL` unset, and `lint-python`
  installs `requirements-dev.txt`, so pytest and the imports are there. The step
  will not fail for want of a database.

I also swept `tests/` by hand for a third live instance the guard cannot see —
`os.walk`, `Path.cwd()`, an imported root, a `.parent.parent` chain, `subprocess`
calling `find`/`grep`/`git`. There is none. Every other `rglob`/`walk` in the
suite is scoped to `APP_ROOT`, `PROMPTS_DIR`, `SERVICES_ROOT`, `VIEWS_SQL_DIR`,
`WORKFLOWS_DIR` or `TEST_TREE`. The finding is closed for the tree as it stands.
What the guard will do about the *next* one is new finding 2.

### HIGH 2 — argparse answering before the guard — **closed, both halves**

- Removing `--` from the workflow fails
  `test_the_workflow_passes_a_separator_before_the_path_list`.
- Removing the script's dash-rejection branch fails
  `test_a_leading_dash_path_is_refused_rather_than_classified` on `-h.md` and
  `--help.md`, and fails `scripts/ci/test_ci_scripts.py` on the same two cases.
  The near misses are what make the second half load-bearing, exactly as the
  comments claim: with `--` present but the refusal gone, bare `-h` still exits 1
  because it is not an inert family, and only the dash-named Markdown cases
  survive to catch it.
- Direct behaviour, run against the classifier: without `--`, `-h`, `-hx` and
  `--hel` all exit 0 and `-q` exits 2 — the original finding reproduces exactly.
  With `--`, every one of those exits 1, and so do `-h.md`, `--help.md`,
  `docs/../backend/app/main.py`, `README.md` and an empty list. A second `--` in
  the path list is refused by the dash branch rather than swallowed, so
  `-- -- docs/MISTAKES.md` exits 1. Every route I could find is fail-closed.

### MEDIUM 1 — only a pull request may be inert — **closed**

Restoring the `case` that selected `PUSH_BEFORE`, and putting `PUSH_BEFORE` back
in the step's `env:`, fails
`test_the_changed_job_classifies_the_diff_on_a_runner_that_has_only_python3` on
the documentation-only-push case. That test executes the real shell step rather
than matching its text, which is the right shape. `PUSH_BEFORE` survives nowhere
that reads it: the only remaining references are prose, and three test fixtures
that still pass it in the environment where the step now ignores it. Harmless —
if anyone re-added `${PUSH_BEFORE:-}` it would be empty, the base would be empty,
and the "no base commit" branch emits `inert=false`.

### MEDIUM 2 — `e2e` and `evals` have their own notice steps — **closed in the workflow, undefended**

Both steps are present and correctly conditioned. Deleting both of them leaves
the whole suite green. The consequence of a silent revert is a log line rather
than a gate, so this is not worth a test on its own — but it is worth knowing
that nothing holds it, because ADR 0070 now records the notices as the only thing
distinguishing "every gate passed" from "every gate declined to look."

### MEDIUM 3 — `frontend-build` guarded and in `changed`'s needs — **closed in the workflow, undefended, and see new finding 1**

The guard is there and `needs: [changed, detect, fast-gate]` is correct. But
removing the notice step, stripping `&& needs.changed.outputs.inert != 'true'`
from all four remaining steps, and dropping `changed` from the job's needs — a
complete revert of the fix — leaves 18 passed in the guard module and 3 passed in
`test_the_aggregate_ci_check_sees_an_upstream_failure.py`. Nothing objects.

## Half two — new findings

### 1. MEDIUM — the inventory that would defend the `frontend-build` guard still lists five jobs

`EXPENSIVE_GATES` in
`tests/unit/test_a_documentation_only_diff_does_not_run_the_expensive_gates.py:277`
holds `test`, `docker`, `e2e`, `evals`, `supply-chain`. `frontend-build` is not in
it, and `test_every_expensive_gate_reaches_the_classification_and_conditions_its_work_on_it`
reads that table, so the job it was added to guard is the one job the test does
not check. `.github/workflows/ci.yml:61` still says "read by the five expensive
gates" and `docs/tickets/e0/.attempts/E0-38.md:12` still says "the five expensive
ones guard their own steps." ADR 0070 is the only record that says six.

This is the finding MEDIUM 3 was about, one level up. MEDIUM 3 was "a sixth
expensive job exists and no record knows it." The fix guarded the job and
corrected one record, and left the inventory the guard test reads — the thing
that makes the property enforceable rather than asserted — still saying five.

What it takes to reach the bad outcome: someone tidies the `frontend-build`
conditions, or reverts this commit's hunk, after the frontend scaffold lands. CI
stays green and a documentation-only pull request runs `npm ci` and a production
build again. Cost is minutes of runner time, not a skipped safety gate, which is
why this is MEDIUM rather than HIGH.

Fix: add `frontend-build` to `EXPENSIVE_GATES` with `npm run build` as its work
pattern, and correct the two remaining "five" claims.

### 2. MEDIUM — the sweep detector catches the idiom it was built for and misses every other route to the repository root

I wrote eight probe modules into `tests/unit/` and ran the guard against them.

| Probe | Route to the repository root | Detected |
|---|---|---|
| H (control) | `REPO_ROOT = Path(__file__).resolve().parents[2]`, then `REPO_ROOT.rglob` | **yes** |
| A | `os.walk(REPO_ROOT)` | no |
| B | `Path.cwd().rglob("*")` | no |
| C | `from tests.conftest import REPO_ROOT`, then `REPO_ROOT.rglob` | no |
| D | `subprocess.run(["grep", "-r", …, str(REPO_ROOT)])` | no |
| E | `subprocess.run(["git", "grep", "-l", …])` | no |
| F | `TREE = Path(__file__).resolve().parent.parent.parent`, then `TREE.rglob` | no |
| G | a fixture named `project_tree` returning the root | no |

Probe E is worth singling out. On its first run it *was* detected — because I had
written the words "git ls-files" in its docstring. That is the same string-match
accident the brief describes finding in `test_mock_lms_service.py`, reproduced by
accident in a file written to test for it. Once the docstring was reworded it went
undetected.

The detector requires all three of: an `ast.Attribute` call named
`walk`/`rglob`/`glob`/`iterdir`; a receiver that is a bare `ast.Name`; and that
name being in `ROOT_FIXTURE_NAMES` or assigned a `<expr>.parents[N]` subscript in
the same module. `os.walk` fails the receiver test. `Path.cwd()` is a call, not a
name. An imported `REPO_ROOT` has no assignment to find. `.parent.parent.parent`
is not a `parents[N]` subscript. A fixture named anything but `repo_root`,
`repository_root` or `root` is not in the list. Anything reaching the tree through
a subprocess is invisible entirely.

None of these is exotic. `os.walk` and `Path.cwd()` are what a Python programmer
who has not read this module writes, and `subprocess` calling `git` is what
`test_no_unresolved_merge_conflicts.py` — one of the two modules the fix exists
for — already does.

What it takes to reach the bad outcome: write a new repository-wide test in the
ordinary way. The guard says nothing, the sweep lives in the `test` job, and a
documentation-only pull request switches off the answer to whatever it checks.
That is HIGH 1 recurring, with a guard in place that reports success. MEDIUM
rather than HIGH because no current module escapes and it needs a future commit
to bite.

Suggestion, and it is a judgment call: match on the *call* rather than the
receiver — any `walk`/`rglob`/`glob`/`iterdir` in a test module whose receiver is
not demonstrably a subdirectory constant, plus any `subprocess` argument list
whose first element is `git`, `grep` or `find`. That over-detects much harder than
`root` does, and it needs the exception set to be trustworthy first, which is
finding 3.

### 3. LOW — `SWEEPS_THAT_NEED_NO_PROTECTION` is a place to put anything inconvenient

You asked directly, so: the three entries are honest today, and nothing makes them
stay that way.

The two E0-35 entries check out. Both modules call `swept_modules(APP_ROOT)` where
`APP_ROOT = REPO_ROOT / "backend" / "app"` and the helper does `root.rglob("*.py")`.
The reason given is accurate.

Nothing validates the set. I added `"tests/unit/test_a_module_that_does_not_exist.py"`
with the reason `"no reason at all"`, and exempted
`test_no_unresolved_merge_conflicts.py` — one of the two modules the whole fix
exists for — with the reason `"inconvenient"`. 18 passed. A key naming a deleted
module persists silently, and if a future module ever takes that path it is
exempted for free.

Compounding it: the detector over-detects in a way that will feed the set. Probe
J was `HERE = Path(__file__).resolve().parents[0]` then `HERE.rglob("test_*.py")`
— a walk of `tests/unit` and nothing more — and it was reported as "uses `.rglob()`
from the repository root," because `is_repository_root` matches any `.parents[N]`
subscript including `parents[0]`. Every such module has to be triaged into the
exception set, the set fills with entries whose reasons nobody rereads, and the
triage becomes rote. That is the mechanism by which a set like this stops doing
work.

Two cheap changes, in order of value: assert that every key resolves to a file
that the detector still flags, so a stale or unnecessary key is a failure; and
require `is_repository_root` to match `parents[N]` for `N >= 1` at minimum, or
better, compare the resolved depth against the module's own.

### 4. LOW — `lint-frontend` has the guard and not the dependency, so the guard is dead

`lint-frontend` declares `needs: detect` at `.github/workflows/ci.yml:345`, and
four of its steps now read `needs.changed.outputs.inert != 'true'`. GitHub
populates the `needs` context only from declared needs, so that expression
evaluates against null: `'' != 'true'` is true, and the steps run on every event
regardless of the classification. I checked every job in the file; `lint-frontend`
is the only one with an undeclared `needs.` reference.

The failure is in the safe direction — the work runs when it might have been
skipped — and `lint-frontend` is a fast job with no frontend to check today, so
nothing is at risk. But the workflow reads as though the job is guarded and it is
not, and the same polarity means this class of mistake will always look harmless
and always be invisible. Either add `changed` to the job's needs or take the four
conditions back out; do not leave it saying something untrue.

### 5. LOW — a condition duplicated in `supply-chain`

`.github/workflows/ci.yml:884` and `:889` both read
`needs.detect.outputs.frontend == 'true' && needs.changed.outputs.inert != 'true'
&& needs.changed.outputs.inert != 'true'`. It is a no-op. It is in the diff, which
means the guard edits went in by pattern rather than being read back, and that is
the same process that produced finding 4.

### Checked and clean

- **`README.md` leaving the inert set.** Correct and complete. `pyproject.toml:26`
  declares `readme = "README.md"` and `backend/Dockerfile:44` has
  `COPY pyproject.toml README.md ./`; those are the only two consumers. `CLAUDE.md`
  and `CONTRIBUTING.md` are the other root Markdown files and neither is a build
  input. No record anywhere still claims README.md is inert. Verified directly:
  `README.md` exits 1, `CONTRIBUTING.md` exits 0.
- **The `..` refusal.** `Path(path).parts` catches `docs/../backend/app/main.py`.
  `./docs/SPEC.md`, an absolute path and a path with a backslash all fall through
  to not-inert on their own.
- **The empty path list.** `python3 classify_changed_paths.py --` with no paths
  exits 1.
- **`PUSH_BEFORE`.** Nothing that reads it remains.
- **The guard module exempting itself.** The stated reason holds: a change that
  could add a sweep module is a `.py` change, which is never inert, so the module
  cannot be switched off on a diff that could invalidate it.

## Where a genuinely independent reader is needed

These are the places where my own report's framing is what the fix rests on. A
reviewer who inherited the distinction cannot check it, and I inherited it from
myself.

1. **The input/subject distinction itself.** It is now in ADR 0070's consequences,
   in three workflow comments, in the guard's failure message ("The inert set is
   about what the build reads; this is about what the suite asserts") and in
   MISTAKES entry 38. If that is the wrong cut — if there is a third category, or
   if "subject" is broader than test assertions and takes in something like the
   licence scan or the image content check — every one of those records is now
   wrong in the same direction, and I am the last person who would notice.
2. **`lint-python` as the home for the sweeps.** I supplied "unconditional job" as
   the criterion and the fix satisfies it literally. Nobody has asked whether
   duplicating three node ids into a lint job is better than making the sweep
   portion of the `test` job unconditional, or than a small job of its own. The
   guard test hard-codes `UNCONDITIONAL_SWEEP_JOB = "lint-python"`, so the choice
   is now load-bearing in a second place.
3. **The MEDIUM 1 verdict that a push may never be inert.** My report argued it,
   the fix implements the argument, and the test now asserts the argument. Nothing
   independent has checked whether a documentation-only push to an epic branch
   with previously-red gates is a real path in this repository's merge flow, or
   whether the saving given up matters. It could go either way and I am not the
   one to say.
4. **The three entries in `SWEEPS_THAT_NEED_NO_PROTECTION`.** I verified the two
   E0-35 ones by reading their call sites. The third — the guard module exempting
   itself — rests on reasoning I would have written the same way, which is not the
   same as it being right.
5. **`README.md`'s reversal.** I raised it and ADR 0070 now records my reasoning
   as the decision, including the claim that this epic has produced no README-only
   pull requests. Somebody should check that count against the branch history
   rather than against the record that asserts it.
