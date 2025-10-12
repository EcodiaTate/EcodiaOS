# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ARG UID=1000
ARG GID=1000
ARG DOCKER_GID=0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf/transformers \
    REPO_ROOT=/repo \
    APP_HOME=/app \
    APP_PORT=8000 \
    APP_MODULE="app:app" \
    VENV_PATH=/opt/venv

# --- OS deps ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl bash ca-certificates openssh-client && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    . /etc/os-release && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $VERSION_CODENAME stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && apt-get install -y docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

# --- User / dirs ---
RUN groupadd -g ${GID} simula || true && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash simula && \
    if [ "${DOCKER_GID}" != "0" ]; then \
      groupadd -g ${DOCKER_GID} dockerhost || true && \
      usermod -aG ${DOCKER_GID} simula || usermod -aG dockerhost simula || true ; \
    fi

RUN mkdir -p ${APP_HOME} ${REPO_ROOT} /models/hf && \
    chown -R ${UID}:${GID} ${APP_HOME} ${REPO_ROOT} /models
WORKDIR ${APP_HOME}

# --- Python venv first ---
RUN python -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

# --- Dependency caching: copy just reqs, install, then (bind-mount code at runtime) ---
COPY --chown=simula:simula requirements.txt ${APP_HOME}/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -U pip setuptools wheel && \
    if [ -f "${APP_HOME}/requirements.txt" ]; then \
      pip install --no-cache-dir -r ${APP_HOME}/requirements.txt ; \
    fi

# Ensure a plain .cache dir for runtime (overlayfs quirks)
RUN mkdir -p ${APP_HOME}/.cache && chown -R ${UID}:${GID} ${APP_HOME}/.cache

# Dev tools (optional)
RUN pip install --no-cache-dir pytest ruff mypy

# --- git config ---
RUN git config --system core.filemode false && \
    git config --system core.autocrlf input && \
    git config --system --add safe.directory ${REPO_ROOT} && \
    git config --system --add safe.directory ${APP_HOME}

USER simula
EXPOSE ${APP_PORT}

# Align healthcheck with compose (your compose hits /health)
HEALTHCHECK --interval=60s --timeout=30s --retries=10 \
  CMD curl -fsS "http://127.0.0.1:${APP_PORT}/health" || exit 1

CMD ["bash","-lc","exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port \"$APP_PORT\" --log-level info"]
