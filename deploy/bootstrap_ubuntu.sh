#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/copyTrading"
APP_USER="copytrade"

apt-get update
apt-get install -y python3 python3-venv python3-pip git curl ca-certificates

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "${APP_USER}"
fi

mkdir -p "${APP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

runuser -u "${APP_USER}" -- python3 -m venv "${APP_DIR}/.venv"
runuser -u "${APP_USER}" -- "${APP_DIR}/.venv/bin/pip" install --upgrade pip
runuser -u "${APP_USER}" -- "${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}"
"${APP_DIR}/.venv/bin/playwright" install --with-deps chromium

install -m 0644 "${APP_DIR}/deploy/copytrade-monitor.service" /etc/systemd/system/copytrade-monitor.service
systemctl daemon-reload

echo "Bootstrap complete."
echo "Next: create ${APP_DIR}/.env and ${APP_DIR}/profiles.json, copy playwright_state.json to the server, then enable the service."
