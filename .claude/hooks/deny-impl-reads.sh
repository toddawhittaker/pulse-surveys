#!/usr/bin/env bash
# Deny reads of implementation source.
#
# Scoped to the `test-author` agent via its frontmatter. AGENTS_INTENT.md:
# "If it can see implementation attempts, it writes tests the implementation
# passes, and red-green becomes theater."
#
# The failure this prevents is not dishonesty, it is gravity: a test author
# that has read the implementation writes assertions shaped like the code in
# front of it, and the suite then measures whether the code does what it does.
#
# Blocks Read/Grep/Glob against backend/app/** and frontend/src/**. The ticket,
# the spec, the design brief, and tests/** stay readable — those are what a test
# should be derived from.
#
# Known cost, deliberately accepted: from E1 on, tests extending an existing
# service are written blind against code that already exists. The mitigation is
# that each ticket states the public interface in its scope section.

set -euo pipefail

# Fail closed when jq is missing. Every field below is read with jq, so without
# it they all come back empty and the guard waves the call through. Worse, the
# harness treats a non-zero exit that is not 2 as a hook *error*, which does not
# block — so `set -e` killing this script on a missing jq (127) would let the
# read proceed. The wall has to notice its own absence.
if ! command -v jq >/dev/null 2>&1; then
  # printf is a shell builtin; `cat` here would need a PATH this guard
  # cannot assume, and a guard that dies while reporting its own failure
  # exits 127, which does not block.
  printf '%s\n' \
    'BLOCKED: jq is not installed, so this guard cannot inspect the tool call.' \
    '' \
    'Refusing to fail open — without jq this hook cannot tell a spec read from an implementation read,' \
    'and a guard that cannot see is not a guard. Install jq.' >&2
  exit 2
fi

input=$(cat)
tool=$(jq -r '.tool_name // empty' <<<"$input")

# Read/Edit use file_path; Grep/Glob use path; Grep may also carry a glob filter.
target=$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<<"$input")
pattern=$(jq -r '.tool_input.glob // .tool_input.pattern // empty' <<<"$input")
# Bash carries its whole command line instead of a path.
command_line=$(jq -r '.tool_input.command // empty' <<<"$input")

repo_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

blocked() {
  cat >&2 <<EOF
BLOCKED: the test author may not read implementation source.

  ${1}

Write tests from the ticket's acceptance criteria and the spec sections it
names — not from the code. A test derived from the implementation asserts that
the code does what it does, which is not a test.

Readable: docs/**, tests/**, docs/tickets/**, CLAUDE.md, and the spec.
Not readable: backend/app/**, frontend/src/**.

If the ticket does not tell you enough to write the test — a signature you
cannot infer, a return shape you would be guessing at — that is a defect in the
ticket. Say so and stop; do not go looking.

(AGENTS_INTENT.md — Test author)
EOF
  exit 2
}

check() {
  local p="$1"
  [ -z "$p" ] && return 0
  local rel="${p#"$repo_root"/}"
  rel="${rel#./}"
  case "$rel" in
    backend/app/*|*/backend/app/*|frontend/src/*|*/frontend/src/*) blocked "$rel" ;;
  esac
}

check "$target"

# A bare Grep/Glob with no path searches the tree; catch patterns aimed at
# implementation directories.
case "$pattern" in
  */backend/app/*|backend/app/*|*/frontend/src/*|frontend/src/*) blocked "$pattern" ;;
esac

# `cat backend/app/config.py` reaches the same bytes without going through Read.
# The test author no longer holds Bash at all, which is the real fix; this is
# here so that giving it back does not silently reopen the hole.
#
# Not a sandbox: a determined shell command can obfuscate a path past this. It
# does not need to stop an adversary. The failure it exists to prevent is
# gravity — reaching for the file because it is right there and the answer is in
# it — and for that, refusing the obvious spelling is enough.
case "$command_line" in
  *backend/app/*|*frontend/src/*) blocked "shell command: $command_line" ;;
esac

exit 0
