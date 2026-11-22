#!/bin/bash
# Oracle 서버 자동 업데이트(5분마다, systemd 타이머 trl-autopull). 2026-11-16 운영자: "오라클 서버 업데이트 수시로".
# ※ 이 파일은 '원본(템플릿)'이다. 서버는 이 파일을 직접 실행하지 않고, 운영자가 sudo 로 1회 실행하는
#    scripts/oracle_autopull_install.sh 가 만든 root 소유 고정 사본(/usr/local/lib/trl-autopull/autopull.sh)만 실행한다.
#    저장소가 바뀌어도 사본은 바뀌지 않는다(사본 갱신 = 운영자가 설치를 다시 돌릴 때만). 11/22 보안 티켓.
#    (설치 전 서버는 이전 방식대로 이 파일을 직접 실행한다 — 그래서 아래 기본값으로도 그대로 동작해야 한다.)
# - trend-lab-site·market-site 를 git pull --ff-only (충돌·로컬 변경이 있으면 그 저장소는 건너뜀 — 강제로 덮지 않음)
# - 저장소 파일을 실행·source 하지 않는다(git pull·rev-parse·diff 만, 훅도 끔)
# - 실시간 코드(rt_kis·rt_serve·keystore·srcscore)가 바뀌면 실시간 서비스만 다시 시작
#   (재시작 명령은 아래 고정 한 줄 — /etc/sudoers.d/trl-autopull 줄의 명령 부분과 글자까지 같아야 sudo 가 허용)
# - 속보·브리핑(live_news)은 실행할 때마다 최신 파일을 읽으므로 pull 만으로 반영된다
set -u
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
GIT=/usr/bin/git
# @@TRL-CONFIG-BEGIN — 설치 스크립트가 이 블록을 고정 값(실행 사용자·저장소 절대경로)으로 바꿔 넣는다.
# 아래 값은 설치 전 이전 방식(저장소에서 직접 실행)일 때만 쓰인다.
REPOS=("$HOME/projects/trend-lab-site" "$HOME/projects/market-site")
# @@TRL-CONFIG-END
RESTART_WHEN='^tools/(rt_kis|rt_serve|keystore|srcscore)\.py$'
err=$(mktemp /tmp/trl-autopull.XXXXXXXX) || exit 1
trap 'rm -f "$err"' EXIT
for d in "${REPOS[@]}"; do
  [ -d "$d/.git" ] || continue
  before=$("$GIT" -C "$d" rev-parse HEAD) || continue
  if ! "$GIT" -C "$d" -c core.hooksPath=/dev/null pull --ff-only -q 2>"$err"; then
    echo "$(date '+%F %T') pull 실패: $d $(head -c 200 "$err")"
    continue
  fi
  after=$("$GIT" -C "$d" rev-parse HEAD) || continue
  [ "$before" = "$after" ] && continue
  echo "$(date '+%F %T') 업데이트: ${d##*/} ${before:0:8}→${after:0:8}"
  if [ "${d##*/}" = "trend-lab-site" ] && "$GIT" -C "$d" -c core.hooksPath=/dev/null diff --name-only "$before" "$after" | grep -qE "$RESTART_WHEN"; then
    if /usr/bin/sudo -n /usr/bin/systemctl restart trl-rt_kis trl-rt_serve; then
      echo "$(date '+%F %T') 실시간 서비스 다시 시작"
    else
      echo "$(date '+%F %T') 실시간 서비스 재시작 실패(sudo 거부 또는 오류) — 다음 회차 계속"
    fi
  fi
done
exit 0
