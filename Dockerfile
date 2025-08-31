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

# --- OS deps in a single, efficient layer ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl bash ca-certificates openssh-client && \
    # Docker CE CLI (official client)
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && apt-get install -y docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

# --- Create user matching host IDs & grant Docker access ---
RUN groupadd -g ${GID} simula || true && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash simula && \
    if [ "${DOCKER_GID}" != "0" ]; then \
      groupadd -g ${DOCKER_GID} dockerhost || true && \
      usermod -aG ${DOCKER_GID} simula || usermod -aG dockerhost simula || true ; \
    fi

# --- Workdirs ---
RUN mkdir -p ${APP_HOME} ${REPO_ROOT} /models/hf && chown -R ${UID}:${GID} ${APP_HOME} ${REPO_ROOT} /models
WORKDIR ${APP_HOME}

# --- Copy sources ---
COPY --chown=simula:simula . ${APP_HOME}

# --- Python: create a venv and install deps into it (avoids PEP 668) ---
RUN python -m venv ${VENV_PATH} && \
    ${VENV_PATH}/bin/pip install --no-cache-dir -U pip setuptools wheel && \
    if [ -f "requirements.txt" ]; then \
      ${VENV_PATH}/bin/pip install --no-cache-dir -r requirements.txt ; \
    elif [ -f "pyproject.toml" ]; then \
      ${VENV_PATH}/bin/pip install --no-cache-dir . ; \
    fi

# Make the venv the default Python
ENV PATH="${VENV_PATH}/bin:${PATH}"

# --- System-wide git config ---
RUN git config --system core.filemode false && \
    git config --system core.autocrlf input && \
    git config --system --add safe.directory ${REPO_ROOT} && \
    git config --system --add safe.directory ${APP_HOME}

USER simula

EXPOSE ${APP_PORT}

HEALTHCHECK --interval=60s --timeout=30s --retries=10 \
  CMD curl -fsS "http://127.0.0.1:${APP_PORT}/simula/sim_health" || exit 1

CMD ["bash","-lc","exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port \"$APP_PORT\" --log-level info"]
