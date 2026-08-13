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
    scripts/reviewer_context.py --selftest      # check the parsing
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# A session that has only loaded its system prompt, CLAUDE.md, and the repo
# preamble sits somewhere near this. Above it, the session is carrying work.
# Deliberately not tuned finely: the question is "has this session been used",
# not "exactly how much", and a wrong answer in the cautious direction costs one
# unnecessary clear.
FRESH_CEILING_TOKENS = 20_000

# Not the model's real limit — the point at which a long session is worth
# clearing regardless of what it is carrying.
LARGE_TOKENS = 400_000


def project_slug(repo_root: Path) -> str:
    """`~/.claude/projects/` names each directory after the repo path."""
    return str(repo_root.resolve()).replace("/", "-")


def transcripts_dir(repo_root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / project_slug(repo_root)


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
        return None
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


def classify(tokens: int) -> str:
    if tokens >= LARGE_TOKENS:
        return "LARGE"
    if tokens > FRESH_CEILING_TOKENS:
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
        print("No sessions with a model call yet.", file=sys.stderr)
        return 2

    rows.sort(key=lambda r: str(r["last_activity"]), reverse=True)

    print(f"{'session':38}  {'last activity':21}  {'context':>10}  state")
    for entry in rows:
        tokens = int(entry["tokens"])
        print(
            f"{str(entry['session'])[:38]:38}  {str(entry['last_activity'])[:21]:21}  "
            f"{tokens:>10,}  {classify(tokens)}"
        )

    needs_clearing = [r for r in rows if classify(int(r["tokens"])) != "fresh"]
    if needs_clearing:
        print()
        print(
            "A session above the fresh ceiling has watched work being written, so a\n"
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
        check("ignores non-assistant rows", context_of(d / "c.jsonl"), None)

        # A half-written final line is normal in a live transcript.
        (d / "e.jsonl").write_text(
            json.dumps(assistant(input_tokens=42)) + '\n{"type": "assist',
            encoding="utf-8",
        )
        check("tolerates a truncated line", context_of(d / "e.jsonl")["tokens"], 42)

        # Missing fields default to zero rather than raising.
        write(d / "f.jsonl", [assistant()])
        check("missing fields are zero", context_of(d / "f.jsonl")["tokens"], 0)

    check("fresh classifies", classify(FRESH_CEILING_TOKENS), "fresh")
    check("above ceiling classifies", classify(FRESH_CEILING_TOKENS + 1), "CONTAMINATED")
    check("large classifies", classify(LARGE_TOKENS), "LARGE")

    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"OK: {8 - len(failures)} checks passed.")
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
