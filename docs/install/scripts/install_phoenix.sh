#!/usr/bin/env bash
# shellcheck shell=bash
#
# install_phoenix.sh provisions the Arize Phoenix observability server under
# /opt/phoenix and registers the accompanying systemd unit.
#
# Usage:
#   sudo bash install_phoenix.sh [version]
#
set -euo pipefail

VERSION="${1:-latest}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to install Phoenix." >&2
  exit 1
fi

echo "[phoenix] creating system user and directories"
if ! id -u phoenix >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /opt/phoenix --shell /usr/sbin/nologin phoenix
fi
install -d -o phoenix -g phoenix /opt/phoenix

echo "[phoenix] creating virtual environment"
python3 -m venv /opt/phoenix/venv
/opt/phoenix/venv/bin/pip install --upgrade pip

if [[ "${VERSION}" == "latest" ]]; then
  /opt/phoenix/venv/bin/pip install "arize-phoenix[server]"
else
  /opt/phoenix/venv/bin/pip install "arize-phoenix[server]==${VERSION}"
fi
chown -R phoenix:phoenix /opt/phoenix

echo "[phoenix] writing environment file to /etc/phoenix/phoenix.env"
install -d /etc/phoenix
cat > /etc/phoenix/phoenix.env <<'ENV'
PHOENIX_HOST=0.0.0.0
PHOENIX_PORT=6006
ENV
chmod 0644 /etc/phoenix/phoenix.env

echo "[phoenix] installing systemd unit"
install -m 0644 "$(dirname "$0")/../systemd/phoenix.service" /etc/systemd/system/phoenix.service
systemctl daemon-reload
systemctl enable --now phoenix.service

echo "[phoenix] installation complete. Open http://localhost:6006 to verify."
