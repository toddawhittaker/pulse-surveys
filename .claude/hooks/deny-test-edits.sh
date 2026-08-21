#!/usr/bin/env bash
# Deny writes to test files.
#
# Scoped to the `implementer` agent via its frontmatter. CLAUDE.md, "How a ticket is built":
# "Never modify, skip, xfail, or delete a test to make it pass. If it believes
# a test is wrong, it escalates and stops."
#
# That is a rule an instruction cannot hold. An implementer one turn from green,
# looking at a test it is convinced is wrong, is exactly the situation where a
# suggestion loses. This is the wall.
#
# Reads the hook payload on stdin, exits 2 to block.

set -euo pipefail

# Fail closed when jq is missing. Every field below is read with jq, so without
# it `path` is empty and line 20 exits 0 — the wall waves the write through. And
# `set -e` killing this script on a missing jq exits 127, which the harness
# treats as a hook *error* rather than a block, so that fails open too. A wall
# that cannot see has to say so.
if ! command -v jq >/dev/null 2>&1; then
  # printf is a shell builtin; `cat` here would need a PATH this guard
  # cannot assume, and a guard that dies while reporting its own failure
  # exits 127, which does not block.
  printf '%s\n' \
    'BLOCKED: jq is not installed, so this guard cannot inspect the tool call.' \
    '' \
    'Refusing to fail open — without jq this hook cannot tell a source edit from a test edit,' \
    'and a guard that cannot see is not a guard. Install jq.' >&2
  exit 2
fi

input=$(cat)
path=$(jq -r '.tool_input.file_path // empty' <<<"$input")
tool=$(jq -r '.tool_name // empty' <<<"$input")
command_line=$(jq -r '.tool_input.command // empty' <<<"$input")

# A shell command rewrites a test without ever calling Write or Edit. Unlike the
# test author, the implementer genuinely needs Bash — it runs `make ci` — so the
# capability cannot simply be withdrawn, and this is the only guard available.
#
# Reading and running tests must keep working: `pytest tests/unit` is the
# implementer's whole feedback loop. So this matches mutation, not mention — a
# redirection into tests/, or a writing command with a test path as its target.
if [ -n "$command_line" ]; then
  case "$command_line" in
    *">"*tests/*|*">>"*tests/*|*tee*tests/*|\
    *rm\ *tests/*|*mv\ *tests/*|*cp\ *tests/*|*truncate*tests/*|\
    *sed\ -i*tests/*|*perl\ -i*tests/*|*patch*tests/*|\
    *git\ checkout*tests/*|*git\ restore*tests/*|*git\ apply*tests/*)
      cat >&2 <<EOF
BLOCKED: the implementer may not modify test files, including from a shell.

  $command_line

Running tests is fine — \`pytest tests/unit\` and \`make ci\` are your feedback
loop and are not blocked. Rewriting one is not. If you believe a test is wrong,
escalate rather than edit: write docs/disputes/<TICKET>-NN.md and stop. The
orchestrating session arbitrates from the sources.

(CLAUDE.md — How a ticket is built)
EOF
      exit 2
      ;;
  esac
fi

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
  2. Stop. The orchestrating session arbitrates from the sources.

Three outcomes: the test is wrong and its author is re-invoked; you are wrong
and get an explanation; or the spec is ambiguous, which is Todd's call and
produces a spec edit or an ADR. That third outcome is why the loop exists.

(CLAUDE.md — How a ticket is built)
EOF
    exit 2
    ;;
esac

exit 0
