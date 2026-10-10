"""SPEC §12 carries ruling 5 — E6-01, criterion 14.

The owner ruled on 2026-10-09 (`docs/tickets/e6/README.md`, ruling 5): no
deployment reaches real students until E10's Care queue exists, because before it
a `threat_case` row has no reader — a student at risk whose comment is held from
every view and read by nobody. E6-01 writes that into SPEC §12's phase lines and
into ADR 0187. The criterion is checkable as a grep: "A grep of §12 for 'Care
queue' finds the sentence."

**The grep alone would pass today, which is why it is not the whole test.** §12's
Phase 2 line already says "Care queue" in a list of what ships then — so a search
for the phrase finds that line on the tree before E6-01. The sentence the
criterion means is the one that also says *no deployment reaches real students*,
so the predicate requires both in one sentence, and the existing Phase 2 line is
run against it as the near miss it must refuse (`docs/MISTAKES.md` entry 3: run
the pattern against the text it claims to allow as well as the text it claims to
catch, and keep a canary that is certainly present).

ADR 0187's statement of the ruling is checked by review, not here, because a test
reading `docs/adr` would need the CI classifier to treat that file as non-inert.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "SPEC.md"

# The canary: the Phase 1 line, copied whole from §12 (entry 3: copy whole lines,
# never retype). Certainly present, so a section split that has gone blind says so.
PHASE_1_CANARY = "- **Phase 1 (MVP):** Epics E0–E4 and E6–E8"  # noqa: RUF001 — copied whole from SPEC §12

# The near miss: §12's Phase 2 line, copied whole. It names the Care queue and says
# nothing about who a deployment may reach.
PHASE_2_LINE = (
    "- **Phase 2:** Epics E5, E9–E12 — benchmarks, leadership roll-ups, Care queue, admin "  # noqa: RUF001 — copied whole from SPEC §12
    "console, notifications; E13 hardening gates release."
)


def section_12(spec_text: str) -> str:
    """The text of `## 12.` up to `## 13.`."""
    return spec_text.split("\n## 12.", 1)[1].split("\n## 13.", 1)[0]


def sentences(text: str) -> list[str]:
    """The text split at sentence ends, with line breaks folded, so a wrapped sentence is one."""
    folded = re.sub(r"\s+", " ", text)
    return [part.strip() for part in re.split(r"(?<=[.;])\s+", folded) if part.strip()]


def states_ruling_5(sentence: str) -> bool:
    """Whether one sentence says the Care queue gates real students."""
    lowered = sentence.lower()
    return "care queue" in lowered and "real students" in lowered


def test_the_ruling_predicate_refuses_the_phase_2_line_and_accepts_the_ruling() -> None:
    """The predicate, run against what it must allow and what it must catch. Green on any tree."""
    assert not any(states_ruling_5(sentence) for sentence in sentences(PHASE_2_LINE)), (
        "The predicate accepts §12's existing Phase 2 line, which names the Care queue and says "
        "nothing about real students — so the grep below would pass on the tree before E6-01."
    )
    ruling = (
        "No deployment reaches real students until E10's Care queue exists, because before it a "
        "`threat_case` row has no reader."
    )
    assert any(
        states_ruling_5(sentence) for sentence in sentences(ruling)
    ), "The predicate refuses the ticket's own wording of ruling 5, so it can never find it."


def test_spec_section_12_gates_real_students_on_the_care_queue() -> None:
    """Criterion 14: §12's phase lines say no deployment reaches real students before E10's queue."""
    text = section_12(SPEC_PATH.read_text(encoding="utf-8"))
    assert PHASE_1_CANARY in text, (
        "SPEC §12 as read here does not contain its own Phase 1 line, so the section split is not "
        "reading §12 and the search below would be over the wrong text."
    )
    found = [sentence for sentence in sentences(text) if states_ruling_5(sentence)]
    assert found, (
        "SPEC §12 has no sentence naming the Care queue and real students together. Ruling 5 "
        "(2026-10-09): no deployment reaches real students until E10's Care queue exists, because "
        "before it a `threat_case` row has no reader. E6-01 writes it into §12's phase lines."
    )
    assert any("E10" in sentence for sentence in found), (
        f"§12's sentence {found} does not say which epic's queue it waits for; the ruling names "
        "E10's."
    )
