#!/usr/bin/env bash
# Check the Celery job runtime against E0-03's acceptance criteria 2, 3 and 4.
#
# Each of the three needs a running daemon and a running stack, so none of them
# can live in pytest: a task has to cross a real network to a real worker in
# another container, beat has to be restarted, and Redis has to be taken away.
# `tests/unit/test_celery_app.py` holds what is checkable without one, and
# `tests/integration/test_celery_ping_roundtrip.py` holds the round trip inside
# one process.
#
# It is a script and not two copies of the same shell — .github/workflows/ci.yml
# and the Makefile both call it — because the polling below is the part most
# easily written wrong, and writing it twice is writing that mistake twice.
#
# Usage: run it from the repository root with the stack already up and healthy.
#
#        ./scripts/ci/wait_for_health.sh api worker beat
#        ./scripts/ci/check_job_runtime.sh

set -euo pipefail

# Both are generous on purpose. A container's health status changes only after
# `retries` consecutive failures, so a poll window equal to that debounce
# reports "it did not happen" for something that had not had time to happen yet
# (docs/MISTAKES.md entry 7). The worker's own debounce is 3 × 15s; this waits
# four times that, and reads the health log rather than the summary alone.
HEALTH_POLL_SECONDS="${HEALTH_POLL_SECONDS:-180}"
PING_TIMEOUT_SECONDS="${PING_TIMEOUT_SECONDS:-60}"

SCHEDULE_DIRECTORY=/var/lib/celery
SCHEDULE_FILE="${SCHEDULE_DIRECTORY}/beat-schedule"
CANARY_FILE="${SCHEDULE_DIRECTORY}/ci-canary"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

group() { echo "::group::$*"; }
endgroup() { echo "::endgroup::"; }
fail() {
  echo "FAIL: $*" >&2
  exit 1
}

container_of() {
  local service="$1" id
  id="$(docker compose ps -q "${service}" 2>/dev/null || true)"
  [ -n "${id}" ] || fail "no container for the '${service}' service — is the stack up?"
  echo "${id}"
}

health_status_of() {
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$1"
}

# The whole health object, not the one-word summary: the summary lags the
# evidence by the debounce, and the log underneath already says what went wrong.
report_health_of() {
  echo "  health of $2:"
  docker inspect --format '{{json .State.Health}}' "$1" || true
}

# Poll until a container's health reaches `want`, or give up loudly.
await_health() {
  local service="$1" want="$2" container status waited=0
  container="$(container_of "${service}")"

  while [ "${waited}" -lt "${HEALTH_POLL_SECONDS}" ]; do
    status="$(health_status_of "${container}")"
    echo "  ${service}: ${status} (${waited}s)"
    if [ "${status}" = "${want}" ]; then
      return 0
    fi
    sleep 5
    waited=$((waited + 5))
  done

  report_health_of "${container}" "${service}"
  fail "'${service}' did not report ${want} within ${HEALTH_POLL_SECONDS}s (last: ${status}).
      That window is four times this check's own debounce, so it is not a
      matter of waiting longer."
}

# ---------------------------------------------------------------------------
# Criterion 2 — the round trip, from the API container.
#
# The integration test proves an application enqueuing to itself. This proves
# the two things that test cannot reach: the message crosses the Compose network
# from one container to another, and the process that runs the task is not the
# process that asked for it.
# ---------------------------------------------------------------------------
group "Criterion 2: ping from the api container comes back through Redis"
docker compose exec -T api python - "${PING_TIMEOUT_SECONDS}" <<'PYTHON'
import sys

from app.jobs.tasks import ping

timeout = float(sys.argv[1])
async_result = ping.delay()
print(f"  enqueued {async_result.id}")
value = async_result.get(timeout=timeout)
print(f"  result: {value!r}")
if not async_result.successful():
    raise SystemExit(f"ping finished in state {async_result.state!r}")
PYTHON
endgroup

# ---------------------------------------------------------------------------
# Criterion 3 — beat restarts cleanly and keeps its schedule file.
#
# Two restarts, because they answer different questions. `restart` is what the
# criterion names, and it proves beat comes back healthy against a store it did
# not have to rebuild. It proves nothing at all about the volume: a restarted
# container keeps its own filesystem, so a beat writing its schedule into the
# image would pass that half untouched. Replacing the container is what makes
# the named volume load-bearing, and a canary written beside the schedule file
# is what makes the answer legible — the store itself is a `shelve` whose
# contents are identical whether it survived or was rebuilt, since E0-03's
# schedule is empty by design.
#
# Whether the *file* survived is asked by its birth time, and the first version
# of this script asked by its inode instead, which was wrong in a way only
# measurement showed. Corrupting the store with beat stopped makes celery take
# `_destroy_open_corrupted_schedule`: it unlinks the file and creates another,
# logging "Removing corrupted schedule file". ext4 then hands the new file the
# inode the old one just freed, so the inode is unchanged across exactly the
# event the comparison existed to catch. Birth time is not reused; it moved.
# ---------------------------------------------------------------------------
# Empty rather than an error when the file is gone, which is the interesting
# case: `set -o pipefail` would otherwise abort the script on `cat`'s exit code
# and the comparison below — the one that can say what a missing canary means —
# would never run.
read_canary() {
  docker compose exec -T beat cat "${CANARY_FILE}" 2>/dev/null | tr -d '\r' || true
}

# When the file was created, to nanoseconds, or `-` where the filesystem does
# not record it. Nanoseconds rather than `%W`'s whole seconds, so that an unlink
# and a create inside the same second are still two different files.
schedule_birth() {
  docker compose exec -T beat stat -c '%w' "${SCHEDULE_FILE}" | tr -d '\r'
}

group "Criterion 3: beat returns to healthy and keeps its schedule file"
docker compose exec -T beat sh -c "date -u +%s%N > '${CANARY_FILE}'"
canary_before="$(docker compose exec -T beat cat "${CANARY_FILE}" | tr -d '\r')"
birth_before="$(schedule_birth)"
echo "  before: schedule created ${birth_before}, canary ${canary_before}"

# Asserted before it is compared, because a value that means "unknown" is the one
# value that makes both comparisons below pass without looking at anything
# (docs/MISTAKES.md entry 3): all three readings come back the same placeholder,
# and the file could have been rebuilt twice in between.
#
# Validated by what a birth time has to look like, rather than by listing the
# ways it can be missing. A blacklist here would have to know every spelling of
# failure, and the two that occur are not the two you would guess — measured,
# both exiting 0: GNU coreutils prints `?` for a directive it does not
# understand, and busybox `stat -c %w` prints the letter `w`. Neither is an
# empty string and neither is a dash, so the blacklist this replaces would have
# passed all three of them straight through, which is `docs/MISTAKES.md` entry 3
# again — a pattern that matches nothing, silently.
#
# ext4 does record a birth time and the named volume lives on the host
# filesystem, so this fires today only if that stops being true.
case "${birth_before}" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]" "[0-9][0-9]:[0-9][0-9]:[0-9]*) ;;
  *)
    fail "the birth time of ${SCHEDULE_FILE} reads '${birth_before}', which is not a
      date. Either the filesystem behind ${SCHEDULE_DIRECTORY} does not record
      one — GNU stat prints '?', busybox prints 'w', and both exit 0 — or this
      \`stat\` spells it differently. Both comparisons below would then compare
      that placeholder with itself and pass whatever had happened to the file,
      so criterion 3 needs an observable this filesystem keeps before it means
      anything here."
    ;;
esac

docker compose restart beat
"${here}/wait_for_health.sh" beat

birth_after="$(schedule_birth)"
canary_after="$(read_canary)"
echo "  after restart: schedule created ${birth_after}, canary ${canary_after}"
[ "${birth_after}" = "${birth_before}" ] || fail "beat replaced its schedule file across a restart
      (created ${birth_before}, now ${birth_after}). The file was rebuilt rather
      than reopened, so anything it held — the last-run times E2 depends on —
      is gone."

docker compose up -d --force-recreate --no-deps beat
"${here}/wait_for_health.sh" beat

canary_recreated="$(read_canary)"
birth_recreated="$(schedule_birth)"
echo "  after recreate: schedule created ${birth_recreated}, canary ${canary_recreated:-<gone>}"
[ "${canary_recreated}" = "${canary_before}" ] || fail "the beat schedule directory did not survive
      a container replacement: a file written before it read '${canary_before}'
      and afterwards reads '${canary_recreated:-nothing — the file is gone}'.
      ${SCHEDULE_DIRECTORY} is not on a named volume, so beat starts from an
      empty schedule every time its container is replaced. Verified by
      reproduction: with the volume taken off the service, the restart above
      still passes — a restarted container keeps its own filesystem — and this
      is the check that fails."

# Second, and not the same question as the canary. The canary says the directory
# came back; this says the schedule file in it is the same file rather than one
# beat built again. They come apart when beat finds a store it cannot read and
# takes `_destroy_open_corrupted_schedule` — the volume is intact, the last-run
# times are gone, and a criterion 3 that only looked at the canary would call
# that a pass. Reproduced: corrupt the store with beat stopped, and this is the
# comparison that fails.
[ "${birth_recreated}" = "${birth_before}" ] || fail "beat rebuilt its schedule file when its
      container was replaced (created ${birth_before}, now ${birth_recreated}),
      even though the volume itself survived — the canary above is intact. The
      store was discarded and started again, so whatever it held is gone. beat
      rebuilds a store it cannot read and says so in its log: 'Removing
      corrupted schedule file'."

docker compose exec -T beat rm -f "${CANARY_FILE}"
endgroup

# ---------------------------------------------------------------------------
# Criterion 4 — the worker health check fails when Redis is stopped.
#
# The one that says the check is worth having. A health check that reports
# healthy no matter what is worse than none, because the gate that reads it goes
# green: `celery inspect ping` needs the broker to answer, so taking the broker
# away has to turn it red.
# ---------------------------------------------------------------------------
group "Criterion 4: the worker goes unhealthy when Redis stops"
docker compose stop redis
await_health worker unhealthy
report_health_of "$(container_of worker)" worker

echo "  restoring redis"
docker compose start redis
"${here}/wait_for_health.sh" redis
await_health worker healthy
endgroup

echo "Job runtime: round trip, beat restart, and worker health all check out."
