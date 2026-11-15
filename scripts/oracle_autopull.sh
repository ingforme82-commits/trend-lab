#!/usr/bin/env bash
# Oracle 서버 자동 업데이트(5분마다, systemd 타이머 trl-autopull). 2026-11-16 운영자: "오라클 서버 업데이트 수시로".
# - trend-lab-site·market-site 를 git pull --ff-only (충돌·로컬 변경이 있으면 그 저장소는 건너뜀 — 강제로 덮지 않음)
# - 실시간 코드(rt_kis·rt_serve·keystore·srcscore)가 바뀌면 실시간 서비스만 다시 시작
# - 속보·브리핑(live_news)은 실행할 때마다 최신 파일을 읽으므로 pull 만으로 반영된다
set -u
for d in "$HOME/projects/trend-lab-site" "$HOME/projects/market-site"; do
  [ -d "$d/.git" ] || continue
  before=$(git -C "$d" rev-parse HEAD)
  if ! git -C "$d" pull --ff-only -q 2>/tmp/trl_autopull.err; then
    echo "$(date '+%F %T') pull 실패: $d $(head -c 200 /tmp/trl_autopull.err)"
    continue
  fi
  after=$(git -C "$d" rev-parse HEAD)
  [ "$before" = "$after" ] && continue
  echo "$(date '+%F %T') 업데이트: ${d##*/} ${before:0:8}→${after:0:8}"
  if [ "${d##*/}" = "trend-lab-site" ] && git -C "$d" diff --name-only "$before" "$after" | grep -qE '^tools/(rt_kis|rt_serve|keystore|srcscore)\.py$'; then
    sudo systemctl restart trl-rt_kis trl-rt_serve && echo "$(date '+%F %T') 실시간 서비스 다시 시작"
  fi
done
