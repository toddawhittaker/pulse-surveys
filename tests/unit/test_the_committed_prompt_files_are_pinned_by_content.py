"""A committed prompt file's bytes are recorded, so an edit to one goes red — ticket E2-18.

ADR 0032's rule is "a prompt file is immutable once committed": changing a prompt
means adding the next version beside it and leaving the old file alone, because a
stored `prompt_version` (ADR 0031) is only worth recording if the text it names
can still be read. That record says plainly what it left unbuilt — "Nothing
enforces the immutability rule ... A CI check that refuses a diff to an existing
prompt file is the enforcing version of this rule and is not built here — it
belongs with E2, which is where the second prompt version and the first eval
floor arrive together." This module is that check, and E2-18 is where it lands.

**Why the gap is worth closing now rather than at E10.** The eval runner compares
the *stem* a gateway answered under against the stem a case is pinned to
(`tests/evals/runner.py`, `_answer`), and a stem does not change when the file it
names does. So an in-place edit of `backend/app/ai/prompts/validity.v2.md` clears
every gate in the repository: the runner's pin still matches, the set still
declares `validity.v2`, and SPEC §9.3's floors are then re-measured against text
nobody reviewed as a prompt change. The floors would move a little and no test
would say why.

**Where the hash moves, and what has to move with it.** A prompt change is a
*new version file* — `validity.v3.md` beside `validity.v2.md` — plus a deliberate
re-measure of SPEC §9.3's floors under it, plus a new row in `RECORDED_SHA256`
for the added file in that same pull request. The row for the old file does not
move, because the old file does not move.

**The forbidden move is an edited hash beside an edited file, and it is the pair
a reviewer should look for.** This test cannot tell a legitimate row from an
illegitimate one — a hash is a hash — so what it buys is that the edit can no
longer be silent: it must appear in the diff as two changes that only make sense
together, in a file whose whole subject is that they must not. A pull request
whose diff touches both `backend/app/ai/prompts/<something>.md` and a
`RECORDED_SHA256` row for that same file is ADR 0032 being broken, whatever the
commit message says.

**This pin is stricter than ADR 0032, and deliberately so.** That record exempts
two edits "because neither changes what the model was sent": a typo in
surrounding commentary the prompt does not include, and whitespace the model
never sees. Bytes cannot tell those from any other edit. The consequence is
accepted rather than worked around: an exempt edit moves its hash row in a pull
request that says which exemption it is claiming, which is a sentence somebody
should have to write anyway.

**The inventory descends, and E2-18's security review is why.** A first draft
globbed `*.md` flat, matching ADR 0032's naming scheme exactly — and matching the
scheme is the mistake that record already documents making once, in the packaging
glob. A nested `prompts/threat/threat.v1.md` was measured: it ships, it loads, it
satisfies the layout guard (which walks the whole tree and blesses nesting), and
it was invisible to this pin and to both directions of its totality. So the walk
is recursive and a key is the path *relative to the prompts directory*, which
makes a nested file representable instead of flattening it onto a name that
another directory could also hold.

**What this cannot see, said rather than implied.** The inventory is every `.md`
file under the directory, and ADR 0032 records that the packaging glob is
deliberately wider than that — `prompts/**/*` ships "everything under the
directory, at any depth and any extension", and `draft.v1.jinja` is named there as
a layout it was widened to carry. A prompt committed under another extension would
therefore reach production and would not be pinned here. What keeps that narrow
rather than open is ADR 0032's own scheme: the stored `prompt_version` is a stem
and "a stem identifies exactly one file only while the extension is fixed", so no
classification can cite a file this pin does not cover. If that ever stops being
true, this pattern is the line to widen, and it should be widened by the change
that makes it untrue.

This module pins bytes and says nothing about whether a file's *name* obeys the
scheme; `tests/unit/test_prompt_directory_layout.py` is the guard on the naming
rule, and ADR 0032 asks a scheme-breaking prompt to produce "a red test and an
argument about this record" while still shipping. Two guards, two mechanisms, one
directory — which is that record's principle, not an accident.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13: "`ai/prompts/` — versioned prompt templates, one file per
# task+version". ADR 0032's scheme is flat; the tree under it is walked anyway,
# because what ships is decided by the packaging glob and not by the scheme.
PROMPTS_DIRECTORY = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

# Matched with `rglob`, so it holds at any depth. ADR 0032 fixes the extension as
# part of the scheme — "a stem identifies exactly one file only while the
# extension is fixed" — and the module docstring says what that leaves outside.
PROMPT_GLOB = "*.md"

# ADR 0032 puts "the scheme, the immutability rule and the list of prompts on
# disk" in a README beside the prompts. It is documentation about the prompts
# rather than a prompt, no `prompt_version` ever names it, and it is expected to
# change whenever a version is added — so it is not pinned. The exclusion is by
# exact file name at any depth, so a prompt is not exempted by mentioning a readme
# in its own text, and a nested directory's readme is excluded like this one.
NOT_A_PROMPT = frozenset({"README.md"})

# The bytes of every committed prompt file, by path relative to the prompts
# directory — `validity.v2.md`, or `threat/threat.v1.md` if a task ever nests.
#
# **Filling a row is a two-step move and both steps belong in the pull request
# that adds the file.** Add the new version file, then take its digest and paste
# the row here:
#
#     python -c "import hashlib, pathlib; d = pathlib.Path('backend/app/ai/prompts'); \
#     [print(f'    {p.relative_to(d).as_posix()!r}: \
#     {hashlib.sha256(p.read_bytes()).hexdigest()!r},') \
#     for p in sorted(d.rglob('*.md')) if p.name != 'README.md']"
#
# `test_every_committed_prompt_file_has_a_recorded_hash` prints the same rows in
# its failure message, so the command is a convenience rather than the mechanism.
#
# **Never run that command to "refresh" a row that already exists.** Regenerating
# the whole mapping is exactly the move this module exists to make visible: it
# turns an edited prompt into a green test and a one-line diff. A row changes
# only when the file it names should never have existed in its old form, and that
# is a conversation rather than a command.
RECORDED_SHA256: dict[str, str] = {
    "validity.v1.md": "206efdc537c84da2896776c8806a419e83f42e24afe2a13c2a9ede8a6c695989",
    "validity.v2.md": "f642eb02afb09803e1230e9fcf907acc18780cbc949a33320701ce27d22f451e",
}


def committed_prompt_files() -> dict[str, Path]:
    """Every committed prompt, by path relative to the prompts directory.

    Reads the directory rather than the mapping, which is the half that makes the
    pin total: a pin whose inventory came from its own recorded names could never
    notice a file nobody recorded.

    **The walk descends.** A flat glob is the inventory ADR 0032's *scheme*
    describes, and the scheme is not what decides which files exist — a nested
    `threat/threat.v1.md` ships, loads and passes the layout guard, and E2-18's
    review measured it going straight past a flat pin. The key keeps the relative
    path for the same reason: two files with one name in two directories are two
    files, and a mapping keyed on the bare name would pin one of them twice.
    """
    if not PROMPTS_DIRECTORY.is_dir():
        return {}
    return {
        path.relative_to(PROMPTS_DIRECTORY).as_posix(): path
        for path in sorted(PROMPTS_DIRECTORY.rglob(PROMPT_GLOB))
        if path.is_file() and path.name not in NOT_A_PROMPT
    }


def digest_of(path: Path) -> str:
    """The sha256 of a file's bytes, read as bytes so no encoding or newline rule intervenes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_prompt_directory_holds_files_for_this_module_to_pin() -> None:
    """The anti-vacuity check, because every other assertion here loops.

    A pin over an empty inventory passes, and it passes hardest when something is
    wrong — a moved directory, a renamed extension, a `REPO_ROOT` that resolved
    one level out. `docs/MISTAKES.md` entry 3 is the general shape and this is the
    specific one, so the emptiness is asserted before anything is compared.

    **The mutation this kills:** point `PROMPTS_DIRECTORY` at a path that does not
    exist, which turns every test below into a loop over nothing and reports the
    whole module green.
    """
    found = committed_prompt_files()
    assert found, (
        f"no prompt files were found under {PROMPTS_DIRECTORY}, matching {PROMPT_GLOB!r} at "
        f"any depth and excluding {sorted(NOT_A_PROMPT)}. SPEC §13 puts versioned prompt "
        "templates there, "
        "and every other assertion in this module is a loop that passes over an empty "
        "inventory."
    )


def test_every_committed_prompt_file_still_holds_the_bytes_that_were_recorded() -> None:
    """ADR 0032: "a prompt file is immutable once committed". This is what says so.

    One byte anywhere in a committed prompt — a word, a comma, an instruction
    reworded — changes the digest and turns this red. That is the whole point: the
    stem the runner pins does not move when the text does, so without this the
    edit reaches SPEC §9.3's floors and nothing anywhere says the measurement is
    about a different program.

    The comparison is over `path.read_bytes()`, not decoded text, so a newline
    conversion or an encoding change is a change. A prompt is what is sent to a
    model, and a model is sent bytes.

    **The mutation this kills:** edit one byte in the middle of
    `backend/app/ai/prompts/validity.v2.md` and commit it, which today passes the
    eval runner's prompt-version pin, the set's own version test and every
    structural test in the suite. **The near miss that must stay green:** adding
    `validity.v3.md` beside it with its own recorded row, which is what ADR 0032
    asks a prompt change to look like.
    """
    found = committed_prompt_files()
    changed = {
        name: {"recorded": recorded, "on disk": digest_of(found[name])}
        for name, recorded in sorted(RECORDED_SHA256.items())
        if name in found and digest_of(found[name]) != recorded
    }
    assert not changed, (
        f"these committed prompt files no longer hold the bytes recorded for them: "
        f"{changed}.\n"
        "\n"
        "ADR 0032: a prompt file is immutable once a classification cites it, because a "
        "stored `prompt_version` is a claim about a text that must still be readable. The "
        "eval runner compares version stems and a stem does not move when its file does, so "
        "an edit here re-measures SPEC §9.3's floors against text that was never reviewed as "
        "a prompt change.\n"
        "\n"
        "The repair is not to update the hash. It is to restore the file and add the next "
        "version beside it — `validity.v3.md` — re-measure the floors under it, and record "
        "the new file's hash in the same pull request. An edited hash beside an edited file "
        "is the move this test exists to make visible."
    )


def test_every_committed_prompt_file_has_a_recorded_hash() -> None:
    """Totality one way: a prompt on disk that nobody pinned is a prompt outside the rule.

    Without this, the pin is opt-in — an added `validity.v3.md` with no row is
    unguarded from the day it lands, and the first edit to it is silent again. The
    row has to arrive with the file, in the pull request that adds it, which is
    also the pull request that re-measures the floors.

    The failure message prints the rows to paste, so adding a version does not
    need the command in the comment above and does not tempt anybody into
    regenerating the whole mapping.

    **The mutation this kills:** add a prompt file and leave `RECORDED_SHA256`
    alone, which without this test is green forever.
    """
    found = committed_prompt_files()
    unpinned = sorted(name for name in found if name not in RECORDED_SHA256)
    rows = "\n".join(f"    {name!r}: {digest_of(found[name])!r}," for name in unpinned)
    assert not unpinned, (
        f"these prompt files have no recorded hash: {unpinned}.\n"
        "\n"
        "ADR 0032 makes every committed prompt immutable, and a file nobody recorded is one "
        "this module cannot notice an edit to. Add its row to `RECORDED_SHA256` in the pull "
        "request that adds the file, beside the re-measured SPEC §9.3 floors:\n"
        "\n"
        f"{rows}\n"
        "\n"
        "Paste the rows for the files named above and nothing else. Replacing the whole "
        "mapping would also record whatever else has changed, which is the one thing this "
        "module is here to refuse."
    )


def test_every_recorded_hash_still_names_a_committed_prompt_file() -> None:
    """Totality the other way: a pinned prompt that has left the tree.

    ADR 0032: "Retiring a prompt is a deletion decision with a retention question
    attached. Once classifications cite `validity.v1`, deleting the file breaks
    their audit trail, so it may only go when the rows citing it have gone under
    §4's retention period." So a disappeared file is not tidying — it is an audit
    trail broken quietly, and it is the failure mode a hash mapping would
    otherwise hide, since a row whose file is absent compares against nothing.

    **The mutation this kills:** delete `validity.v1.md` once `validity.v2` is in
    use, which every other test in this module and in the eval suite accepts —
    they all read the version the application currently loads.
    """
    found = committed_prompt_files()
    missing = sorted(name for name in RECORDED_SHA256 if name not in found)
    assert not missing, (
        f"these prompt files have a recorded hash and are not in "
        f"{PROMPTS_DIRECTORY.relative_to(REPO_ROOT)}: {missing}. The directory holds "
        f"{sorted(found)}.\n"
        "\n"
        "ADR 0032 makes retiring a prompt a deletion decision with a retention question "
        "attached: classifications citing that version can no longer be reproduced once the "
        "file is gone. Removing the row here is how that decision gets recorded — after the "
        "rows citing the version have gone under SPEC §4's retention period, not before."
    )


def test_the_prompt_version_the_application_loads_is_one_of_the_pinned_files(
    configured_env: dict[str, str],
) -> None:
    """The pin covers the prompt actually in use, not merely some files.

    The three tests above are each about the *relationship* between the directory
    and the mapping, and all three are satisfied by a directory and a mapping that
    agree with each other about the wrong thing. This one reaches outside both: ADR
    0031 makes the recorded version the prompt file's stem, so
    `app.ai.tasks.VALIDITY_PROMPT_VERSION` plus `.md` is the file every §3.3
    classification and every SPEC §9.3 measurement is currently made under, and
    that file is the one whose immutability has consequences today.

    The key expected is the flat one, which is a claim as well as a lookup: ADR
    0032's scheme resolves a stored stem to a file "with no lookup table between
    them", so the prompt a version string names sits directly in the directory. A
    live prompt that had moved into a subdirectory would be red here, and rightly —
    the walk descends so that nested files are *pinned*, not so that the version
    scheme quietly acquires a search path.

    `configured_env` is `docs/MISTAKES.md` entry 40: importing `app.ai.tasks`
    reaches the settings, and a red that depended on the developer's shell would be
    a red about the machine.

    **The mutation this kills:** move the live prompt out of the pinned inventory —
    into a subdirectory, or to another extension — which leaves the mapping total
    over what remains and leaves the text that is actually being sent unguarded.
    """
    from app.ai.tasks import VALIDITY_PROMPT_VERSION

    expected = f"{VALIDITY_PROMPT_VERSION}.md"
    found = committed_prompt_files()

    assert expected in found, (
        f"`app.ai.tasks.VALIDITY_PROMPT_VERSION` is {VALIDITY_PROMPT_VERSION!r}, so the "
        f"prompt being sent today is {expected}, and this module's inventory of "
        f"{PROMPTS_DIRECTORY.relative_to(REPO_ROOT)} holds {sorted(found)}. A prompt outside "
        "the inventory is a prompt outside the pin, and it is the one whose edit would move "
        "SPEC §9.3's floors."
    )
    assert expected in RECORDED_SHA256, (
        f"{expected} is the prompt the application loads and it has no recorded hash. Every "
        "classification stored today cites it (ADR 0031), so it is the file ADR 0032's "
        "immutability rule is most about."
    )
