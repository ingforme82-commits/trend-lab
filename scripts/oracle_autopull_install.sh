#!/bin/bash
# Oracle 자동 업데이트(trl-autopull) 고정 사본 설치 — 11/22 보안 티켓 ①②.
# 서버는 저장소 안 스크립트를 직접 실행하지 않고, 이 설치가 만든 root 소유 사본만 5분마다 실행한다.
# 사본 갱신은 운영자가 이 설치를 다시 돌릴 때만(autopull 은 자기 자신을 갱신하지 않음).
#
# 사용(서버, 관리 사용자로 ssh 접속 후 — 운영자만):
#   sudo bash oracle_autopull_install.sh --user ubuntu              # 설치(사본·유닛·타이머), 끝에 sha256 출력
#   sudo bash oracle_autopull_install.sh --uninstall                # 이전 유닛(백업)으로 되돌림
#   bash oracle_autopull_install.sh --render <폴더> --user ubuntu --home /home/ubuntu   # 테스트: 폴더에 결과만 생성
# 옵션: --home <절대경로>  실행 사용자 홈(기본: 시스템 사용자 정보). 저장소는 <홈>/projects/trend-lab-site·market-site
set -euo pipefail
umask 022

LIB_DIR=/usr/local/lib/trl-autopull
COPY_NAME=autopull.sh
UNIT_DIR=/etc/systemd/system
BACKUP_DIR=/root/trl-backup-autopull
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SRC_DIR/oracle_autopull.sh"

die() { echo "중단: $*" >&2; exit 1; }
valid_user() { [[ "$1" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; }
valid_home() { [[ "$1" =~ ^/[A-Za-z0-9._/-]+$ ]] && [[ "$1" != *..* ]] && [[ "$1" != *//* ]] && [ "$1" != / ]; }

MODE=install RUN_USER="" HOME_DIR="" RENDER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) [ $# -ge 2 ] || die "--user 값 없음"; RUN_USER="$2"; shift 2 ;;
    --home) [ $# -ge 2 ] || die "--home 값 없음"; HOME_DIR="$2"; shift 2 ;;
    --render) [ $# -ge 2 ] || die "--render 값 없음"; RENDER="$2"; MODE=render; shift 2 ;;
    --uninstall) MODE=uninstall; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) die "모르는 옵션: $1" ;;
  esac
done

# ── 사본·유닛 내용 ──────────────────────────────────────────────
render_copy() {   # 템플릿의 설정 블록을 고정 값으로 바꿔 표준 출력으로
  awk -v u="$RUN_USER" -v h="$HOME_DIR" '
    NR == 1 { print "#!/bin/bash"
              print "# 설치 사본(oracle_autopull_install.sh) — 원본: 저장소 scripts/oracle_autopull.sh. root 소유·실행 사용자 쓰기 불가."
              print "# 갱신은 운영자가 설치를 다시 실행할 때만. 이 파일을 직접 고치지 말 것."
              next }
    /^# @@TRL-CONFIG-BEGIN/ { inblk = 1; seen++
              print "# 설치 고정 값 — 실행 사용자 " u ", 저장소 절대경로(실행 때 HOME·환경변수·저장소 파일로 경로를 만들지 않음)"
              print "if [ \"$(/usr/bin/id -un)\" != \"" u "\" ]; then echo \"실행 사용자가 " u " 가 아님 — 중단\"; exit 1; fi"
              print "REPOS=(\"" h "/projects/trend-lab-site\" \"" h "/projects/market-site\")"
              next }
    /^# @@TRL-CONFIG-END/ { inblk = 0; next }
    inblk { next }
    { print }
    END { if (seen != 1) exit 3 }
  ' "$TEMPLATE"
}

render_service() {
  cat <<EOF
[Unit]
Description=TRL auto pull (root 소유 고정 사본 — oracle_autopull_install.sh)
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=${RUN_USER}
ExecStart=${LIB_DIR}/${COPY_NAME}
EOF
}

render_timer() {
  cat <<'EOF'
[Unit]
Description=TRL auto pull every 5 min
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
}

check_copy() {   # 만든 사본에 저장소 경로 실행·HOME 사용이 남지 않았는지
  local f="$1"
  grep -q 'REPOS=("/' "$f" || die "사본에 고정 저장소 경로가 없음"
  if grep -vE '^[[:space:]]*#' "$f" | grep -nE '\$HOME|\$\{HOME|(^|[;&|[:space:]])(source|\.)[[:space:]]|python|bash[[:space:]]+[^-]'; then
    die "사본에 HOME·source·python·bash 실행 줄이 남음(위 줄)"
  fi
}

write_file() {   # 임시 파일에 쓰고 권한을 맞춘 뒤 한 번에 교체. $1=대상 $2=권한, 내용은 표준 입력
  local dst="$1" mode="$2" tmp
  tmp=$(mktemp "$(dirname "$dst")/.trl-tmp.XXXXXX")
  cat >"$tmp"
  chmod "$mode" "$tmp"
  [ "$MODE" = render ] || chown root:root "$tmp"
  mv -f "$tmp" "$dst"
}

# ── 입력 확인(아무것도 만들기 전에) ───────────────────────────────
if [ "$MODE" != uninstall ]; then
  valid_user "$RUN_USER" || die "--user 이름이 올바르지 않음(영소문자·숫자·_- 만): '${RUN_USER}'"
  [ "$RUN_USER" != root ] || die "root 로는 돌리지 않음"
  if [ -z "$HOME_DIR" ]; then
    HOME_DIR=$(getent passwd "$RUN_USER" | cut -d: -f6) || true
    [ -n "$HOME_DIR" ] || die "사용자 ${RUN_USER} 의 홈을 찾지 못함(--home 으로 지정)"
  fi
  valid_home "$HOME_DIR" || die "--home 경로가 올바르지 않음: '${HOME_DIR}'"
  [ -f "$TEMPLATE" ] || die "원본 없음: $TEMPLATE"
fi

case "$MODE" in
  render)
    [ -n "$RENDER" ] || die "--render 폴더 없음"
    R="${RENDER%/}"
    mkdir -p "$R$LIB_DIR" "$R$UNIT_DIR"
    render_copy | write_file "$R$LIB_DIR/$COPY_NAME" 0755
    check_copy "$R$LIB_DIR/$COPY_NAME"
    render_service | write_file "$R$UNIT_DIR/trl-autopull.service" 0644
    render_timer | write_file "$R$UNIT_DIR/trl-autopull.timer" 0644
    echo "생성(테스트): $R"
    ;;
  install)
    [ "$(id -u)" = 0 ] || die "root 로 실행(sudo bash $0 --user ${RUN_USER})"
    id "$RUN_USER" >/dev/null 2>&1 || die "사용자 없음: ${RUN_USER}"
    sys_home=$(getent passwd "$RUN_USER" | cut -d: -f6)
    [ "$sys_home" = "$HOME_DIR" ] || die "--home(${HOME_DIR}) 이 시스템 홈(${sys_home}) 과 다름"
    [ -d "$HOME_DIR/projects/trend-lab-site/.git" ] || echo "경고: $HOME_DIR/projects/trend-lab-site 저장소가 없음(있는 저장소만 받음)"
    install -d -m 0700 -o root -g root "$BACKUP_DIR"
    for f in trl-autopull.service trl-autopull.timer; do   # 처음 설치 전 유닛만 보관(되돌리기용, 덮어쓰지 않음)
      if [ -f "$UNIT_DIR/$f" ] && [ ! -e "$BACKUP_DIR/$f.orig" ]; then cp -p "$UNIT_DIR/$f" "$BACKUP_DIR/$f.orig"; fi
    done
    install -d -m 0755 -o root -g root "$LIB_DIR"
    render_copy | write_file "$LIB_DIR/$COPY_NAME" 0755
    check_copy "$LIB_DIR/$COPY_NAME"
    render_service | write_file "$UNIT_DIR/trl-autopull.service" 0644
    render_timer | write_file "$UNIT_DIR/trl-autopull.timer" 0644
    systemctl daemon-reload
    systemctl enable --now trl-autopull.timer
    echo "설치 완료 — 사본:"
    ls -l "$LIB_DIR/$COPY_NAME"
    sha256sum "$LIB_DIR/$COPY_NAME"
    echo "확인: systemctl cat trl-autopull.service (ExecStart=$LIB_DIR/$COPY_NAME) · journalctl -u trl-autopull -n 20"
    ;;
  uninstall)
    [ "$(id -u)" = 0 ] || die "root 로 실행(sudo bash $0 --uninstall)"
    [ -f "$BACKUP_DIR/trl-autopull.service.orig" ] || die "백업 없음: $BACKUP_DIR/trl-autopull.service.orig — 되돌릴 이전 유닛이 없음"
    cp -p "$BACKUP_DIR/trl-autopull.service.orig" "$UNIT_DIR/trl-autopull.service"
    if [ -f "$BACKUP_DIR/trl-autopull.timer.orig" ]; then cp -p "$BACKUP_DIR/trl-autopull.timer.orig" "$UNIT_DIR/trl-autopull.timer"; fi
    rm -f "$LIB_DIR/$COPY_NAME"; rmdir "$LIB_DIR" 2>/dev/null || true
    systemctl daemon-reload
    systemctl enable --now trl-autopull.timer
    echo "되돌림 완료 — 이전 유닛 복원(저장소 스크립트를 직접 실행하는 이전 방식)."
    ;;
esac
