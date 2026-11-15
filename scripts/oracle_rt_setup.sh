#!/usr/bin/env bash
# Oracle 서버 실시간 경로 설치(한 번만): KIS 웹소켓 수신(rt_kis) + 사이트 전달(rt_serve + Cloudflare 무료 터널).
# 비용 0. 키 값은 출력하지 않는다. 사용: bash scripts/oracle_rt_setup.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3)"
if ! command -v cloudflared >/dev/null; then
  ARCH="$(dpkg --print-architecture)"            # arm64(Ampere) 또는 amd64
  curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
  sudo dpkg -i /tmp/cloudflared.deb
fi
for name in rt_kis rt_serve; do
  sudo tee "/etc/systemd/system/trl-${name}.service" >/dev/null <<EOF
[Unit]
Description=TRL ${name}
After=network-online.target
[Service]
User=${USER}
WorkingDirectory=${REPO}
ExecStart=${PY} ${REPO}/tools/${name}.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF
done
sudo systemctl daemon-reload
sudo systemctl enable --now trl-rt_kis trl-rt_serve
sleep 20
systemctl --no-pager --lines=0 status trl-rt_kis trl-rt_serve | grep -E "●|Active"
echo "터널 주소: $(cat ~/.local/state/trendlab/rt_url.txt 2>/dev/null || echo '아직 없음(30초 뒤 다시 확인)')"
