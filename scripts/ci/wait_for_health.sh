#!/usr/bin/env bash
# Wait for named Compose services to report healthy.
#
# A container that is "up" is not the same as a container that works: the API
# can be listening before migrations finish, and the worker can be running with
# no broker connection. This waits on the health check, so "the stack comes up"
# means something.
#
# Usage: wait_for_health.sh api worker beat [...]
#        TIMEOUT_SECONDS=180 wait_for_health.sh api

set -euo pipefail

TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-180}"
POLL_SECONDS="${POLL_SECONDS:-3}"

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <service> [service...]" >&2
  exit 2
fi

deadline=$(( SECONDS + TIMEOUT_SECONDS ))

for service in "$@"; do
  echo "Waiting for '${service}' to become healthy (timeout ${TIMEOUT_SECONDS}s)..."

  while :; do
    container="$(docker compose ps -q "${service}" 2>/dev/null || true)"

    if [ -z "${container}" ]; then
      status="not-created"
    else
      # A service with no HEALTHCHECK reports an empty .Health. Treat "running
      # with no health check defined" as a configuration gap, not as healthy —
      # api, worker, and beat are all required to declare one.
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "${container}" 2>/dev/null || echo unknown)"
      state="$(docker inspect -f '{{.State.Status}}' "${container}" 2>/dev/null || echo unknown)"

      if [ "${state}" = "exited" ] || [ "${state}" = "dead" ]; then
        echo "FAIL: '${service}' exited before becoming healthy." >&2
        docker compose logs --no-color --tail=100 "${service}" >&2 || true
        exit 1
      fi
    fi

    case "${status}" in
      healthy)
        echo "  ${service}: healthy"
        break
        ;;
      no-healthcheck)
        echo "FAIL: '${service}' declares no HEALTHCHECK." >&2
        echo "      api, worker, and beat must each declare one so this gate means something." >&2
        exit 1
        ;;
      unhealthy)
        echo "FAIL: '${service}' reported unhealthy." >&2
        docker compose logs --no-color --tail=100 "${service}" >&2 || true
        exit 1
        ;;
    esac

    if [ "${SECONDS}" -ge "${deadline}" ]; then
      echo "FAIL: timed out after ${TIMEOUT_SECONDS}s waiting for '${service}' (last status: ${status})." >&2
      docker compose ps >&2 || true
      docker compose logs --no-color --tail=100 "${service}" >&2 || true
      exit 1
    fi

    sleep "${POLL_SECONDS}"
  done
done

echo "All requested services are healthy."
