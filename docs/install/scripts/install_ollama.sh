#!/usr/bin/env bash
# shellcheck shell=bash
#
# install_ollama.sh installs the Ollama runtime, creates the ollama system user,
# and registers the systemd service bundled with this repository.
#
# Usage:
#   sudo bash install_ollama.sh
#
set -euo pipefail

ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64)  TAR_URL="https://ollama.com/download/ollama-linux-amd64.tgz" ;;
  aarch64) TAR_URL="https://ollama.com/download/ollama-linux-arm64.tgz" ;;
  *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;;
esac

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "[ollama] downloading binaries from ${TAR_URL}"
curl -fsSL "${TAR_URL}" -o "${TMP_DIR}/ollama.tgz"

echo "[ollama] extracting to /usr"
tar -C /usr -xzf "${TMP_DIR}/ollama.tgz"

if ! id -u ollama >/dev/null 2>&1; then
  echo "[ollama] creating system user"
  useradd --system --create-home --home-dir /usr/share/ollama --shell /usr/sbin/nologin ollama
fi

install -d -o ollama -g ollama /usr/share/ollama
chown -R ollama:ollama /usr/share/ollama

echo "[ollama] installing systemd unit"
install -m 0644 "$(dirname "$0")/../systemd/ollama.service" /etc/systemd/system/ollama.service
systemctl daemon-reload
systemctl enable --now ollama.service

echo "[ollama] pulling default models (gemma3:1b and embeddinggemma:latest)"
sudo -u ollama /usr/bin/ollama pull gemma3:1b
sudo -u ollama /usr/bin/ollama pull embeddinggemma:latest

echo "[ollama] installation complete. Inspect logs with: journalctl -u ollama -f"
