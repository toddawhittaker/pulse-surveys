# Backend image — ticket E0-02, SPEC §7.2.
#
# Two stages. The builder resolves, compiles, and builds; the runtime stage
# receives a finished virtualenv and nothing else, so no compiler, no pip cache,
# no lockfile, and no test dependency ships. It runs as an unprivileged user and
# declares the HEALTHCHECK that `scripts/ci/wait_for_health.sh` waits on — that
# script treats a service with no health check as a configuration gap rather
# than as healthy, deliberately.
#
# Both stages name the same base image by tag *and* by digest; see
# docs/adr/0007-container-images-pinned-by-tag-and-digest.md.
#
# Installing follows docs/adr/0005-dependency-locking.md rather than inventing
# its own way: the closure comes from a committed lockfile under
# `--require-hashes`, and the project is built with `--no-build-isolation`
# against a setuptools that the same lockfile verified. That ADR says every
# container image installs the same way as CI, because the guarantee is only as
# good as the sloppiest install line.

FROM python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /src

# The runtime closure, into the virtualenv that ships. Its own layer, so
# editing a source file does not reinstall thirty-nine packages.
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --requirement requirements.txt

# The PEP 517 build backend, into this stage's own interpreter and never into
# /opt/venv. It comes from the dev lock because that is the only lockfile that
# carries a hash for it (ADR 0005 explains why it lives there); the rest of that
# file is test tooling, and none of this stage reaches the runtime stage.
COPY requirements-dev.txt ./
RUN pip install --require-hashes --requirement requirements-dev.txt

# Build the project with that verified setuptools and no build isolation, then
# install the wheel with no dependency resolution of its own — the closure above
# is already complete and already hash-checked.
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip wheel . --no-deps --no-build-isolation --wheel-dir /wheels \
 && /opt/venv/bin/pip install --no-deps --no-index /wheels/*.whl


FROM python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# An unprivileged system account with a fixed uid, so `id -u` is never 0 and a
# bind-mounted file's ownership is predictable across machines. No login shell
# and no home directory: nothing in this image is meant to be logged into.
RUN groupadd --system --gid 1001 pulse \
 && useradd --system --uid 1001 --gid pulse --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin pulse

COPY --from=builder --chown=root:root /opt/venv /opt/venv

WORKDIR /app
USER pulse
EXPOSE 8000

# The same endpoint the CI health gate requests over the published port. urllib
# is in the standard library, so this adds no package to the image and needs no
# shell; `urlopen` raises on any non-2xx, which is exactly the failure the check
# has to report.
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

# No `--reload` and no bind mount here. Development wiring is
# docker-compose.override.yml's job, so this is what every other deployment runs.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
