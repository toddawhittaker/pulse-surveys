#!/usr/bin/env bash
# Check that `.dockerignore` keeps editor and merge debris out of the runtime
# image — ticket E0-36 item 4.
#
# `pyproject.toml` ships `app.ai` package data `prompts/**/*`, so every
# non-hidden file left in `backend/app/ai/prompts/` is copied into the build
# context, packaged into the wheel, and installed into the runtime image. E0-12
# added four re-exclusions for that — `backend/**/*~`, `*.orig`, `*.rej` and
# `*.bak` — because the file this guards against is a key parked beside a prompt
# while debugging: untracked, invisible in review, and sitting on the machine
# that runs the build.
#
# `backend/**/*.pem` and `backend/**/*.key` reach that directory the same way and
# are covered here too. They are not a fifth and sixth suffix of the same kind:
# they are lines whose deletion ships a private key rather than a stray note, and
# they had nothing watching them until E0-36's review measured it.
# `backend/**/*.pfx` and `backend/**/*.secret` are two more of that kind, added
# by E0-37 item 9 — which measured both suffixes *reaching* the image, since
# until that item no line excluded them. `backend/**/*.p12` and the four
# extensionless OpenSSH default key basenames — `backend/**/id_rsa`,
# `backend/**/id_ed25519`, `backend/**/id_ecdsa`, `backend/**/id_dsa` — are five
# more again, added by the Batch H review, which found the commonest names item 9
# left uncovered still reaching the image: `.p12` is the same format as `.pfx`
# under its commoner extension, and the `id_*` names are what OpenSSH writes a
# private key as by default (`id_ed25519` the modern one).
#
# **Deleting any of those thirteen lines leaves every other gate green.** That is
# what this exists for. It is not a test of `.dockerignore`'s text, and E0-36
# says why: a text assertion passes against a typo'd pattern, which carries the
# file just as surely. So this plants one file per pattern, builds the image, and
# looks inside it.
#
# It is a script and not two copies of the same shell — .github/workflows/ci.yml
# and the Makefile both call it — for the reason at the top of
# scripts/ci/check_job_runtime.sh: the part most easily written wrong is written
# once.
#
# **The positive control is not ceremony** (docs/MISTAKES.md entry 3). A check
# that inspects a path where nothing ever lands reports "nothing stray was found"
# forever, and a typo in the inspection path is then a permanently green gate.
# So a file that must be there is asserted present before the absence of the
# planted ones is believed.
#
# Usage: run it from anywhere, with a Docker daemon available.
#
#        ./scripts/ci/check_image_contents.sh

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"

# Where the package data comes from in the source tree, and where it lands in the
# image. The second is not hardcoded: it is asked of the installed package, so
# that a change to the venv path or the Python version does not turn this into a
# check of a directory that is not there.
PROMPTS_SOURCE_DIRECTORY="backend/app/ai/prompts"

# The positive control. This file is tracked, is shipped as package data, and
# must be in the image; if it is not, the inspection below is looking in the
# wrong place and its silence about the planted files means nothing.
CONTROL_FILE="validity.v1.md"

# One file per re-exclusion this covers, so that a deleted line names itself in
# the failure rather than being one of thirteen candidates. The stem says what
# they are and where they came from, because a build that dies between the plant
# and the cleanup leaves them in somebody's working tree.
#
# The `.pem` and `.key` are the point of the whole check and were the two it
# missed. They are in this list on a measurement rather than on symmetry:
# planting one of each in the prompts directory and listing the installed
# directory inside a built image showed both excluded — by the two lines in
# `.dockerignore` that name them, reached through the same `pyproject.toml`
# package-data glob that carries the four above.
#
# The `.pfx` and `.secret` arrived with E0-37 item 9, on the same kind of
# measurement with the opposite answer: planted the same way, both **reached**
# the image, because nothing in `.dockerignore` matched them. That item added the
# two lines and these two plants together.
#
# The `.p12`, `id_rsa`, `id_ed25519`, `id_ecdsa` and `id_dsa` arrived with the
# Batch H review, again the same measurement with the same opposite answer —
# planted the same way and all **reached** the image, because item 9's two lines
# did not match them. The four `id_*` keys have no suffix, so each planted file is
# named by that literal basename rather than with the shared stem, because
# `.dockerignore` matches each as `backend/**/id_*`. So the nine names whose
# deletion ships key material now all have something watching them. It stops at
# OpenSSH's four default names: `.jks`, `.keystore`, `.p8` and `.der` are
# speculative beside an AI-prompt directory, and the review agreed not to add them.
PLANTED_FILES=(
  "e0-36-image-content-check.md~"     # backend/**/*~
  "e0-36-image-content-check.orig"    # backend/**/*.orig
  "e0-36-image-content-check.rej"     # backend/**/*.rej
  "e0-36-image-content-check.bak"     # backend/**/*.bak
  "e0-36-image-content-check.pem"     # backend/**/*.pem
  "e0-36-image-content-check.key"     # backend/**/*.key
  "e0-37-image-content-check.pfx"     # backend/**/*.pfx
  "e0-37-image-content-check.secret"  # backend/**/*.secret
  "e0-37-image-content-check.p12"     # backend/**/*.p12
  "id_rsa"                            # backend/**/id_rsa
  "id_ed25519"                        # backend/**/id_ed25519
  "id_ecdsa"                          # backend/**/id_ecdsa
  "id_dsa"                            # backend/**/id_dsa
)

# Its own tag, so a build that does carry a planted file cannot be left behind as
# the image the rest of the Docker gate then runs.
PROBE_IMAGE="pulse-surveys/image-content-check:probe"

group() { echo "::group::$*"; }
endgroup() { echo "::endgroup::"; }
fail() {
  echo "FAIL: $*" >&2
  exit 1
}

listing_file="$(mktemp)"

# The files this run actually wrote, appended one at a time as each `printf`
# succeeds. **Not `PLANTED_FILES`**, and the difference is a file somebody
# loses: the plant loop below refuses rather than overwrites a name that is
# already there, and a cleanup iterating the full list then deleted exactly the
# file the refusal existed to protect — the run exited 1 telling the developer
# to delete their file, having already deleted it. Found by E0-36's independent
# security review and reproduced.
#
# So this array is the record of what is ours to remove. It stays empty until
# something is written, which makes the refusal path remove nothing at all.
written_files=()

# Everything this planted, and the image it built, whichever way the script
# leaves. A check that leaves a `.bak` in the prompts directory has planted
# exactly the file it exists to prevent.
cleanup() {
  local status=$?
  local name
  for name in "${written_files[@]}"; do
    rm -f "${repo_root}/${PROMPTS_SOURCE_DIRECTORY}/${name}"
  done
  rm -f "${listing_file}"
  docker image rm --force "${PROBE_IMAGE}" >/dev/null 2>&1 || true
  return "${status}"
}
trap cleanup EXIT

cd "${repo_root}"

[ -f .dockerignore ] || fail ".dockerignore is not in the repository root. The build context is
      then everything in the tree, and the re-exclusions this checks for do not
      exist to check."
[ -d "${PROMPTS_SOURCE_DIRECTORY}" ] || fail "${PROMPTS_SOURCE_DIRECTORY} does not exist, so there is
      nowhere to plant a file and nothing for the package-data glob in
      pyproject.toml to match. If the prompts moved, move this check with them."

group "Planting one file per .dockerignore re-exclusion"
for name in "${PLANTED_FILES[@]}"; do
  planted="${PROMPTS_SOURCE_DIRECTORY}/${name}"
  # Refuse rather than overwrite. These names are this script's own, so one
  # already existing means either a previous run died before its cleanup or
  # somebody is using the name for something else; either way, silently
  # truncating a file in the working tree is not this check's business.
  if [ -e "${planted}" ]; then
    fail "${planted} already exists. This script plants and removes that file,
      so it will not write over one that is already there. Delete it if it is
      debris from an interrupted run."
  fi
  # A comment saying what the file is, and nothing that resembles the thing two
  # of these suffixes stand for. These markers are read by name, never by
  # content, so there is no reason for one to hold anything key-shaped.
  printf '%s\n%s\n' \
    '# planted by scripts/ci/check_image_contents.sh (E0-36 item 4), and removed by it.' \
    '# A marker read by name. It holds no key material and never has.' > "${planted}"
  [ -f "${planted}" ] || fail "could not create ${planted}, so the check below would look for a file
      that was never planted and pass having found nothing."
  # Recorded only now, after the write succeeded, so cleanup can never remove a
  # file this run did not create.
  written_files+=("${name}")
  echo "  ${planted}"
done
endgroup

# Same context and same Dockerfile as the `api`, `worker` and `beat` services in
# docker-compose.yml, and the same final stage. `--load` because CI's builder is
# the docker-container driver (docker/setup-buildx-action), which builds into its
# own cache and puts nothing in the image store unless told to — and this has to
# run the image afterwards.
#
# The build is a cache hit in the passing case, and that is the mechanism rather
# than an optimisation: if `.dockerignore` excludes the planted files, the
# context is unchanged, every layer is reused, and the image is the one that was
# already built. If it does not exclude them, the context changes, `COPY backend`
# and the wheel build below it re-run, and the file is in the image. The answer
# is the same either way; only the cost differs.
group "Building the runtime image over the planted files"
docker build --load --file backend/Dockerfile --tag "${PROBE_IMAGE}" .
endgroup

# What is actually installed, asked of the installed package rather than of a
# path this script guessed. Redirected to a file and the status checked
# separately: reading a gate's result through a pipe reports the exit code of the
# last command in it (docs/MISTAKES.md entry 34).
group "Listing the prompts directory inside the image"
if ! docker run --rm "${PROBE_IMAGE}" python -c '
import pathlib
import sys

import app.ai

directory = pathlib.Path(app.ai.__file__).parent / "prompts"
if not directory.is_dir():
    sys.stderr.write(f"no prompts directory at {directory} in this image\n")
    raise SystemExit(2)
for entry in sorted(directory.iterdir()):
    print(entry.name)
' > "${listing_file}"; then
  fail "could not list the installed prompts directory inside ${PROBE_IMAGE}. Until that
      listing can be read, this check cannot say anything about what reached the
      image — and an unreadable listing is not an empty one."
fi
cat "${listing_file}"
endgroup

# Non-empty first. An empty listing satisfies every absence check below without
# looking at anything, and it is what a wrong inspection path produces.
[ -s "${listing_file}" ] || fail "the prompts directory inside ${PROBE_IMAGE} is empty. That is not a
      pass: the package data in pyproject.toml ships ${CONTROL_FILE} and a
      README, so an empty directory means this is inspecting the wrong image or
      the wrong path, and the absence of the planted files below would mean
      nothing."

# The positive control, and the reason it is here is in this file's header.
if ! grep -Fxq "${CONTROL_FILE}" "${listing_file}"; then
  fail "${CONTROL_FILE} is not installed in ${PROBE_IMAGE}, and it must be — pyproject.toml
      ships \`prompts/**/*\` as \`app.ai\` package data and that file is tracked.
      Something between the package-data glob, the wheel build and this listing
      is not doing what this check assumes, so the planted files being absent is
      not evidence that .dockerignore excluded them."
fi

carried=()
for name in "${PLANTED_FILES[@]}"; do
  if grep -Fxq "${name}" "${listing_file}"; then
    carried+=("${name}")
  fi
done

if [ "${#carried[@]}" -gt 0 ]; then
  echo "FAIL: these planted files reached the runtime image: ${carried[*]}" >&2
  cat >&2 <<'EXPLANATION'

      `.dockerignore` re-excludes thirteen patterns under `backend/`: `*~`,
      `*.orig`, `*.rej` and `*.bak` at the end of the file, and `*.pem`, `*.key`,
      `*.pfx`, `*.p12`, `*.secret` and the four extensionless OpenSSH key
      basenames `id_rsa`, `id_ed25519`, `id_ecdsa` and `id_dsa` in the block with
      the `.env` patterns. Each planted file above matches exactly one of them, so
      each name says which line is gone or no longer matches what it used to.

      This is not cosmetic. `pyproject.toml` ships `prompts/**/*` as `app.ai`
      package data, so anything left in `backend/app/ai/prompts/` is packaged
      into the wheel and installed into the image — a key parked beside a prompt
      while debugging included. The file is untracked, so nothing in review shows
      it, and every other gate stays green.

      Restore the missing line in `.dockerignore` rather than renaming the file
      that tripped this.
EXPLANATION
  exit 1
fi

echo "Image contents: ${CONTROL_FILE} is installed and none of the ${#PLANTED_FILES[@]} planted files reached the image."
