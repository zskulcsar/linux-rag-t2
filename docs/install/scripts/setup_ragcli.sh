#!/usr/bin/env bash
# shellcheck shell=bash
#
# setup_ragcli.sh prepares directories, ownership, and default configuration
# for the Linux RAG backend. Usage:
#   sudo bash setup_ragcli.sh /opt/linux-rag-t2 ragcli
#
# Arguments:
#   $1 - Absolute path to the linux-rag-t2 repository
#   $2 - System user that will own runtime directories (default: ragcli)
#
set -euo pipefail

REPO_PATH="${1:-}"
SERVICE_USER="${2:-ragcli}"

if [[ -z "${REPO_PATH}" ]]; then
  echo "Usage: $0 /path/to/linux-rag-t2 [service-user]" >&2
  exit 1
fi

if [[ ! -d "${REPO_PATH}" ]]; then
  echo "Repository path ${REPO_PATH} does not exist" >&2
  exit 1
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  echo "Creating user ${SERVICE_USER}"
  useradd --system --create-home --home-dir /var/lib/${SERVICE_USER} \
    --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

CONFIG_DIR="/etc/ragcli"
STATE_DIR="/var/lib/ragcli"
LOG_DIR="/var/log/ragcli"
RUNTIME_DIR="/run/ragcli"

echo "Creating directories..."
install -d -m 0755 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${STATE_DIR}"
install -d -m 0755 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${STATE_DIR}/ragcli"
install -d -m 0755 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${STATE_DIR}/ragcli/kiwix"
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${LOG_DIR}"
install -d -m 0755 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${RUNTIME_DIR}"
install -d -m 0755 "${CONFIG_DIR}"

CONFIG_FILE="${CONFIG_DIR}/config.yaml"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Writing default config to ${CONFIG_FILE}"
  cat >"${CONFIG_FILE}" <<'YAML'
ragman:
  confidence_threshold: 0.35
  presenter_default: markdown
ragadmin:
  output_default: table
YAML
fi
chown "${SERVICE_USER}:${SERVICE_USER}" "${CONFIG_FILE}"
chmod 0644 "${CONFIG_FILE}"

ENV_FILE="${CONFIG_DIR}/ragbackend.env"
echo "Writing environment file to ${ENV_FILE}"
cat >"${ENV_FILE}" <<ENV
# Runtime paths
RAGCLI_CONFIG=${CONFIG_FILE}
RAGCLI_RUNTIME_DIR=${RUNTIME_DIR}
RAGCLI_STATE_DIR=${STATE_DIR}
RAGCLI_LOG_DIR=${LOG_DIR}

# Transport endpoints
RAGCLI_SOCKET=\${RAGCLI_RUNTIME_DIR}/backend.sock
WEAVIATE_URL=http://localhost:8080
OLLAMA_URL=http://localhost:11434
PHOENIX_URL=http://localhost:6006

# Repository location
RAGCLI_REPO=${REPO_PATH}
ENV
chmod 0644 "${ENV_FILE}"

echo "Setup complete."
