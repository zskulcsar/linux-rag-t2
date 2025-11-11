#!/usr/bin/env bash
# shellcheck shell=bash
#
# install_weaviate.sh downloads a Weaviate release, provisions service user,
# and configures the accompanying systemd unit.
#
# Usage:
#   sudo bash install_weaviate.sh [version]
#
set -euo pipefail

VERSION="${1:-1.30.0}"
ARCH="$(uname -m)"
if [[ "${ARCH}" != "x86_64" ]]; then
  echo "This installer currently supports x86_64 hosts. For other architectures, install manually." >&2
  exit 1
fi

ASSET="weaviate-v${VERSION}-linux-amd64.tar.gz"
URL="https://github.com/weaviate/weaviate/releases/download/v${VERSION}/${ASSET}"

TMP_DIR="$(mktemp -d)"
echo "[DEBUG] TMP_DIR :: '${TMP_DIR}'"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "[weaviate] downloading ${URL}"
curl -fsSL "${URL}" -o "${TMP_DIR}/weaviate.tar.gz"
if [ $? -ne 0 ]; then
  echo "[weaviate] download failed with error code $?. Check the curl manual for error codes."
  exit 1
fi

echo "[weaviate] creating system user and directories"
if ! id -u weaviate >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/weaviate --shell /usr/sbin/nologin weaviate
fi
install -d -o weaviate -g weaviate /opt/weaviate
install -d -o weaviate -g weaviate /var/lib/weaviate

echo "[weaviate] extracting binaries to /opt/weaviate"
tar -C /opt/weaviate -xzf "${TMP_DIR}/weaviate.tar.gz"
chmod +x /opt/weaviate/weaviate
chown -R weaviate:weaviate /opt/weaviate

echo "[weaviate] writing environment defaults to /etc/weaviate/weaviate.env"
install -d /etc/weaviate
install -m 0644 "$(dirname "$0")/../config/weaviate.env" /etc/weaviate/weaviate.env

echo "[weaviate] installing systemd unit"
install -m 0644 "$(dirname "$0")/../systemd/weaviate.service" /etc/systemd/system/weaviate.service
systemctl daemon-reload
systemctl enable --now weaviate.service

echo "[weaviate] installation complete. Inspect logs with: journalctl -u weaviate -f"
