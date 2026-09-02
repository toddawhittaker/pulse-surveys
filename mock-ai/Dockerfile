# Mock AI provider image — ticket E2-07, SPEC §9.2 and §13.
#
# The same two-stage shape as `backend/Dockerfile`, `mock-lms/Dockerfile` and
# `mock-idp/Dockerfile`, for the same reasons: the builder resolves and installs,
# the runtime stage receives a finished virtualenv and nothing else, and both
# stages name the base image by tag *and* by digest
# (docs/adr/0007-container-images-pinned-by-tag-and-digest.md).
#
# **It installs the backend's runtime lockfile.** This service needs FastAPI and
# uvicorn and nothing else, and it could be given a shorter list — but a shorter
# list is a second closure to maintain, with no `pip-compile` behind it and no
# hashes, which is exactly what docs/adr/0005-dependency-locking.md exists to
# prevent. So it installs `requirements.txt`, hash-verified, and carries a few
# libraries it never imports. The provider has **no dependency of its own**: it
# reads a prompt with `str.rfind`, decides with a character count, and serialises
# its answer with the standard library's `json`.
#
# The project itself is deliberately *not* installed here, and this image is the
# one where that matters most. The backend's package is also called `app`, and so
# are the mock platform's and the mock provider's (SPEC §13 names all four); an
# image holding two would resolve `import app` by whichever won the path — the
# same collision `tests/fixtures/app_imports.py` installs a scoped finder to
# avoid. Installing the backend here would be worse than untidy: this container
# would then hold the real classifier's code beside the thing that stands in for
# its provider. This image holds one `app`, at `/app/app`, and no wheel that
# could shadow it.
#
# There is no HEALTHCHECK instruction. `docker-compose.yml` declares the check
# for this service, and one copy is the point — see the comment there.

FROM python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /src

COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --requirement requirements.txt


FROM python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# An unprivileged system account with a fixed uid, as in the other three images.
# This service authenticates nobody and answers a completion for whoever asks, so
# the less the process can reach, the better.
RUN groupadd --system --gid 1001 pulse \
 && useradd --system --uid 1001 --gid pulse --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin pulse

COPY --from=builder --chown=root:root /opt/venv /opt/venv

# Root-owned, so nothing this image runs can rewrite its own code.
COPY --chown=root:root mock-ai/app /app/app

WORKDIR /app
USER pulse
EXPOSE 8000

# `--factory`, as the other three are started. There is no per-process key behind
# it here — this service holds none — but a module-level application object would
# read its configuration at import time, and the shape every Python service in
# this repository is started with is worth more than the one line it saves.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
