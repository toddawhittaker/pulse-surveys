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

input=$(cat)
tool=$(jq -r '.tool_name // empty' <<<"$input")

# Read/Edit use file_path; Grep/Glob use path; Grep may also carry a glob filter.
target=$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<<"$input")
pattern=$(jq -r '.tool_input.glob // .tool_input.pattern // empty' <<<"$input")

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

exit 0
