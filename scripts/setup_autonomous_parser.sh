#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/setup_autonomous_parser.sh [pages_per_run] [target_offers] [interval] [sleep_seconds]
# Example: ./scripts/setup_autonomous_parser.sh 5 0 15min 30

PAGES_PER_RUN="${1:-5}"
TARGET_OFFERS="${2:-0}"
TIMER_INTERVAL="${3:-15min}"
SLEEP_SECONDS="${4:-30}"

SERVICE_NAME="cian-autonomous"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_PATH="/etc/systemd/system/${SERVICE_NAME}.timer"
WORKDIR="/home/ubuntu/realestate"

echo "🔧 Installing ${SERVICE_NAME}.service (pages=${PAGES_PER_RUN}, target=${TARGET_OFFERS}, sleep=${SLEEP_SECONDS}s)..."
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=Autonomous CIAN parser
After=network.target

[Service]
Type=oneshot
WorkingDirectory=${WORKDIR}
Environment=CIAN_DETAIL_TIMEOUT=${CIAN_DETAIL_TIMEOUT:-45}
Environment=CIAN_FORCE_RUN=0
ExecStart=/usr/bin/python3 -m etl.collector_cian.cli autonomous \\
    --payload etl/collector_cian/payloads/base.yaml \\
    --pages ${PAGES_PER_RUN} \\
    --target-offers ${TARGET_OFFERS} \\
    --sleep-seconds ${SLEEP_SECONDS}
EOF

echo "⏱️  Installing ${SERVICE_NAME}.timer (interval=${TIMER_INTERVAL})..."
sudo tee "${TIMER_PATH}" >/dev/null <<EOF
[Unit]
Description=Schedule autonomous CIAN parser

[Timer]
OnBootSec=5min
OnUnitActiveSec=${TIMER_INTERVAL}
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo "🔄 Reloading systemd..."
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.timer"

echo "✅ Done. Check status with: sudo systemctl status ${SERVICE_NAME}.service && systemctl list-timers | grep ${SERVICE_NAME}"



