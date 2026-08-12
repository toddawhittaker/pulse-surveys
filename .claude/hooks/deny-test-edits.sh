#!/usr/bin/env bash
# Deny writes to test files.
#
# Scoped to the `implementer` agent via its frontmatter. AGENTS_INTENT.md:
# "Never modify, skip, xfail, or delete a test to make it pass. If it believes
# a test is wrong, it escalates and stops."
#
# That is a rule an instruction cannot hold. An implementer one turn from green,
# looking at a test it is convinced is wrong, is exactly the situation where a
# suggestion loses. This is the wall.
#
# Reads the hook payload on stdin, exits 2 to block.

set -euo pipefail

input=$(cat)
path=$(jq -r '.tool_input.file_path // empty' <<<"$input")
tool=$(jq -r '.tool_name // empty' <<<"$input")

[ -z "$path" ] && exit 0

# Normalise to a repo-relative path so ../ and absolute forms cannot slip past.
repo_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
rel="${path#"$repo_root"/}"

case "$rel" in
  tests/*|*/tests/*|*_test.py|*.test.ts|*.test.tsx|*.spec.ts|*.spec.tsx|conftest.py|*/conftest.py)
    cat >&2 <<EOF
BLOCKED: the implementer may not $tool test files.

  $rel

If you believe this test is wrong, do not change it. Escalate:

  1. Write docs/disputes/<TICKET>-NN.md containing
       - the test, quoted
       - what you believe it asserts incorrectly
       - the spec section you are relying on, quoted
       - what you tried, and why you think the test rather than the code is
         at fault
  2. Stop. The arbitrator is a separate session and will rule.

Three outcomes: the test is wrong and its author is re-invoked; you are wrong
and get an explanation; or the spec is ambiguous, which is Todd's call and
produces a spec edit or an ADR. That third outcome is why the loop exists.

(AGENTS_INTENT.md — Implementer, hard rules)
EOF
    exit 2
    ;;
esac

exit 0
