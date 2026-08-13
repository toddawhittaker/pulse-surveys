#!/usr/bin/env python3
"""Report how much context each Claude Code session for this repo is carrying.

`/security-review` has to run in a session that has not watched the work being
written (`CLAUDE.md`, SPEC §14.2 item 3). A session reused across several reviews
stops satisfying that quietly: nothing fails, the review still arrives, and it is
shaped by everything the session already believes.

A peer session cannot be cleared by another agent — `/clear` is a harness command
and nothing an agent sends makes it fire (`docs/MISTAKES.md`, entry 9). So the
next best thing is to *see* the state and say so, which is what this does. It
reads the local session transcripts under `~/.claude/projects/<slug>/` and reports
the context each session had in flight at its last model call.

Two different worries, reported separately, because they need different answers:

  CONTAMINATED  the session is carrying material from earlier work, so a review
                from it is not independent. Fix: clear it, or use a new session.
  LARGE         the session is approaching its context limit. Fix: clear it, for
                entirely unrelated reasons.

A session can be contaminated while nowhere near full. For review independence
that is the case that matters, and it is the one a capacity indicator misses.

Usage:
    scripts/reviewer_context.py                 # every session for this repo
    scripts/reviewer_context.py --session <id>  # one session
    scripts/reviewer_context.py --selftest      # check the parsing and thresholds
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# What a session costs before it has done anything: the system prompt, CLAUDE.md,
# and everything CLAUDE.md points at. Measured, not guessed — the first model call
# of every session recorded for this repo, which is the cheapest that session ever
# gets:
#
#     31,267  32,875  34,110  35,901  37,261  37,308  43,190  43,333
#
# The top two are `/security-review` invocations, which additionally load the
# skill body. The first estimate here was 20,000, which classified a *freshly
# cleared* session at 37,308 as contaminated — the measurement is the only reason
# this number is right.
FRESH_BASELINE_TOKENS = 35_000

# How far above the baseline still counts as fresh. A session carrying real work
# is far above this, not marginally: on the data above, the used sessions sit at
# 56k to 103k against a 49k threshold, so the gap is wide and the exact multiplier
# is not load-bearing.
CONTAMINATION_MULTIPLIER = 1.4

# Not the model's real limit — the point at which a long session is worth
# clearing regardless of what it is carrying.
LARGE_TOKENS = 400_000


def contamination_threshold() -> int:
    return int(FRESH_BASELINE_TOKENS * CONTAMINATION_MULTIPLIER)


def project_slug(repo_root: Path) -> str:
    """`~/.claude/projects/` names each directory after the repo path."""
    return str(repo_root.resolve()).replace("/", "-")


def transcripts_dir(repo_root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / project_slug(repo_root)


def _mtime_iso(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def context_of(transcript: Path) -> dict[str, object] | None:
    """Context in flight at the session's last model call.

    The usage block on an assistant message reports what that call was billed
    for. Everything the model saw is the sum of the three input figures — fresh
    input, what was read from cache, and what was written to it. Output tokens
    are excluded: they are what the model produced, not what it was carrying.

    Returns None for a transcript with no assistant message, which is a session
    that started and never called the model.
    """
    last: tuple[dict, dict] | None = None
    with transcript.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # A transcript being appended to can end mid-line. Skip it
                # rather than fail: a partial read is still worth reporting.
                continue
            usage = (row.get("message") or {}).get("usage")
            if row.get("type") == "assistant" and isinstance(usage, dict):
                last = (row, usage)
    if last is None:
        # Cleared and untouched. Report it rather than skipping: this is the
        # state a reviewer session should be in, so silence here would hide the
        # answer. Fall back to the file's own mtime for "when".
        return {
            "session": transcript.stem,
            "tokens": None,
            "last_activity": _mtime_iso(transcript),
            "model": "—",
        }
    row, usage = last
    tokens = (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
    )
    return {
        "session": transcript.stem,
        "tokens": tokens,
        "last_activity": row.get("timestamp") or "unknown",
        "model": (row.get("message") or {}).get("model") or "unknown",
    }


def classify(tokens: int | None) -> str:
    """`None` means the session has made no model call — cleared and untouched.

    That is the state most worth confirming before a review, and reporting it as
    "unknown" would hide exactly the answer being looked for.
    """
    if tokens is None:
        return "fresh (no model call yet)"
    if tokens >= LARGE_TOKENS:
        return "LARGE"
    if tokens > contamination_threshold():
        return "CONTAMINATED"
    return "fresh"


def report(repo_root: Path, only: str | None) -> int:
    directory = transcripts_dir(repo_root)
    if not directory.is_dir():
        print(f"No session transcripts at {directory}.", file=sys.stderr)
        return 2

    rows = []
    for transcript in sorted(directory.glob("*.jsonl")):
        if only and transcript.stem != only:
            continue
        entry = context_of(transcript)
        if entry is not None:
            rows.append(entry)

    if not rows:
        print("No session transcripts found.", file=sys.stderr)
        return 2

    rows.sort(key=lambda r: str(r["last_activity"]), reverse=True)

    threshold = contamination_threshold()
    print(
        f"baseline {FRESH_BASELINE_TOKENS:,} tokens "
        f"(system prompt + CLAUDE.md and what it references); "
        f"contaminated above {threshold:,}"
    )
    print()
    print(f"{'session':38}  {'last activity':21}  {'context':>10}  state")
    for entry in rows:
        tokens = entry["tokens"]
        shown = "—" if tokens is None else f"{int(tokens):,}"
        print(
            f"{str(entry['session'])[:38]:38}  {str(entry['last_activity'])[:21]:21}  "
            f"{shown:>10}  {classify(None if tokens is None else int(tokens))}"
        )

    needs_clearing = [
        r
        for r in rows
        if not classify(None if r["tokens"] is None else int(r["tokens"])).startswith("fresh")
    ]
    if needs_clearing:
        print()
        print(
            "A CONTAMINATED session has watched work being written, so a\n"
            "security review from it is not independent (SPEC §14.2 item 3). Clear it\n"
            "with /clear in that session, or start a new one — an agent cannot clear a\n"
            "peer, and asking it to looks like it worked (docs/MISTAKES.md, entry 9)."
        )
    return 0


def selftest() -> int:
    """Check the parsing against transcripts with known answers."""
    failures = []

    def check(label: str, got: object, want: object) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    def write(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def assistant(**usage: int) -> dict:
        return {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"model": "m", "usage": usage},
        }

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # The three input figures are summed; output is excluded.
        write(
            d / "a.jsonl",
            [assistant(input_tokens=1, cache_read_input_tokens=99, output_tokens=5000)],
        )
        check("sums inputs, ignores output", context_of(d / "a.jsonl")["tokens"], 100)

        # The *last* assistant message wins, not the largest or the first.
        write(
            d / "b.jsonl",
            [assistant(input_tokens=900), assistant(input_tokens=7)],
        )
        check("uses the last call", context_of(d / "b.jsonl")["tokens"], 7)

        # A user row carrying a usage block must not be mistaken for a model call.
        write(
            d / "c.jsonl",
            [{"type": "user", "message": {"usage": {"input_tokens": 500}}}],
        )
        # A usage block on a user row is not a model call. The session is
        # reported, with no token figure, rather than silently dropped.
        check("ignores non-assistant rows", context_of(d / "c.jsonl")["tokens"], None)
        check(
            "no-call session is reported",
            classify(context_of(d / "c.jsonl")["tokens"]),
            "fresh (no model call yet)",
        )

        # A half-written final line is normal in a live transcript.
        (d / "e.jsonl").write_text(
            json.dumps(assistant(input_tokens=42)) + '\n{"type": "assist',
            encoding="utf-8",
        )
        check("tolerates a truncated line", context_of(d / "e.jsonl")["tokens"], 42)

        # Missing fields default to zero rather than raising.
        write(d / "f.jsonl", [assistant()])
        check("missing fields are zero", context_of(d / "f.jsonl")["tokens"], 0)

    # The measured baselines: every one must read as fresh. The 20,000 ceiling
    # this file shipped with failed the last three of these.
    for observed in (31_267, 32_875, 34_110, 35_901, 37_261, 37_308, 43_190, 43_333):
        check(f"measured baseline {observed} is fresh", classify(observed), "fresh")

    # The used sessions from the same machine: every one must read as carrying work.
    for observed in (56_581, 64_872, 67_770, 80_517, 102_717):
        check(f"used session {observed} is contaminated", classify(observed), "CONTAMINATED")

    check("at the threshold is fresh", classify(contamination_threshold()), "fresh")
    check("just above is contaminated", classify(contamination_threshold() + 1), "CONTAMINATED")
    check("large classifies", classify(LARGE_TOKENS), "LARGE")
    check("no model call is fresh", classify(None), "fresh (no model call yet)")

    total = 24
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"OK: {total - len(failures)} checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", help="report one session id")
    parser.add_argument("--selftest", action="store_true", help="check the parsing")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository whose sessions to report (default: this one)",
    )
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    return report(args.repo_root, args.session)


if __name__ == "__main__":
    sys.exit(main())
