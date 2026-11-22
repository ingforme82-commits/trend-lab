#!/bin/bash
# Oracle 서버 실행 사용자 권한 축소 — 11/22 보안 티켓 ③. 저장소 코드가 도는 사용자(보통 ubuntu)가 root 로 못 가게 한다.
#   - sudo 는 실시간 서비스 재시작 한 줄만(/etc/sudoers.d/trl-autopull)
#   - sudo·lxd·admin·docker 그룹에서 뺌, 90-cloud-init-users 의 전체 NOPASSWD 줄을 주석 처리
#   - 실행 사용자 유닛에 NoNewPrivileges=yes 드롭인(trl-autopull·trl-opsq 제외)
# 관리(sudo) 작업은 별도 관리 사용자(예: trladmin)로. --apply 는 그 관리 사용자로 로그인해 sudo 로 실행했을 때만 진행한다.
#
# 사용(서버, ssh 접속 후 — 운영자만):
#   sudo bash oracle_harden.sh --check --user ubuntu [--admin trladmin]   # 읽기만: 현재 상태 출력
#   sudo bash oracle_harden.sh --apply --user ubuntu --admin trladmin     # 적용(관리 사용자 세션에서만)
#   sudo bash oracle_harden.sh --rollback                                 # 마지막 백업으로 되돌림(root·시리얼 콘솔 가능)
#   bash oracle_harden.sh --render <폴더> --user ubuntu                   # 테스트: 폴더에 sudoers·드롭인만 생성
# 추가 옵션: --unit <유닛>   드롭인 대상 추가(trl-* 와 User=<실행 사용자> 유닛은 자동)
#            --skip-unit <유닛>  드롭인에서 뺌(서버 홈 스크립트가 sudo 를 쓰는 유닛 등)
#            --root <폴더>   (테스트 전용) 모든 경로 앞에 붙임
set -euo pipefail
umask 022

RESTART_CMD='/usr/bin/systemctl restart trl-rt_kis trl-rt_serve'   # oracle_autopull.sh 의 재시작 줄과 같아야 함
SUDOERS_NAME=trl-autopull
DROPIN_NAME=trl-hardening.conf
EXCLUDE_UNITS=" trl-autopull.service trl-opsq.service "
DROP_GROUPS="sudo lxd admin docker"
BASE_UNITS="trl-rt_kis.service trl-rt_serve.service"

die() { echo "중단: $*" >&2; exit 1; }
warn() { echo "경고: $*" >&2; }
valid_user() { [[ "$1" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; }
valid_unit() { [[ "$1" =~ ^[A-Za-z0-9_.@:-]+\.service$ ]] && [[ "$1" != *..* ]]; }

MODE="" RUN_USER="" ADMIN="" R="" EXTRA_UNITS="" SKIP_UNITS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check|--apply|--rollback) MODE="${1#--}"; shift ;;
    --render) [ $# -ge 2 ] || die "--render 값 없음"; MODE=render; R="${2%/}"; shift 2 ;;
    --root) [ $# -ge 2 ] || die "--root 값 없음"; R="${2%/}"; shift 2 ;;
    --user) [ $# -ge 2 ] || die "--user 값 없음"; RUN_USER="$2"; shift 2 ;;
    --admin) [ $# -ge 2 ] || die "--admin 값 없음"; ADMIN="$2"; shift 2 ;;
    --unit|--skip-unit)
      [ $# -ge 2 ] || die "$1 값 없음"
      u="$2"; [[ "$u" == *.service ]] || u="$u.service"
      valid_unit "$u" || die "유닛 이름이 올바르지 않음: '$2'"
      if [ "$1" = --unit ]; then EXTRA_UNITS="$EXTRA_UNITS $u"; else SKIP_UNITS="$SKIP_UNITS $u "; fi
      shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) die "모르는 옵션: $1" ;;
  esac
done
[ -n "$MODE" ] || die "--check / --apply / --rollback / --render 중 하나"

# ── 입력 확인(아무것도 만들기 전에) ───────────────────────────────
if [ "$MODE" != rollback ]; then
  valid_user "$RUN_USER" || die "--user 이름이 올바르지 않음(영소문자·숫자·_- 만): '${RUN_USER}'"
  [ "$RUN_USER" != root ] || die "root 는 대상이 아님"
fi
if [ "$MODE" = apply ]; then
  valid_user "$ADMIN" || die "--admin 관리 사용자 이름이 올바르지 않음: '${ADMIN}'"
  [ "$ADMIN" != "$RUN_USER" ] && [ "$ADMIN" != root ] || die "관리 사용자는 실행 사용자·root 와 달라야 함"
fi
if [ "$MODE" = render ] && [ -z "$R" ]; then die "--render 폴더 없음"; fi

SYSD="$R/etc/systemd/system"

sudoers_content() {
  echo "# TRL 보안(oracle_harden.sh, 11/22): 실행 사용자는 실시간 서비스 재시작 이 한 줄만 sudo 가능. 와일드카드·셸 금지."
  echo "${RUN_USER} ALL=(root) NOPASSWD: ${RESTART_CMD}"
}

dropin_content() {
  echo "# TRL 보안(oracle_harden.sh, 11/22): 저장소 코드가 sudo·setuid 로 권한을 올리지 못하게"
  echo "[Service]"
  echo "NoNewPrivileges=yes"
}

unit_uses_sudo() {   # 유닛 ExecStart 가 가리키는 파일에 sudo 가 있으면 0
  local f="$SYSD/$1" tok
  [ -f "$f" ] || return 1
  for tok in $(sed -n 's/^ExecStart=[-@:+!]*//p' "$f"); do
    [[ "$tok" == /* ]] || continue
    if [ -f "$R$tok" ] && grep -qw sudo "$R$tok" 2>/dev/null; then echo "$tok"; return 0; fi
  done
  return 1
}

units_to_harden() {   # 기본 2개 + trl-*.service + User=<실행 사용자> 유닛 + --unit, 제외 목록 빼고
  local list="$BASE_UNITS $EXTRA_UNITS" f n
  for f in "$SYSD"/*.service; do
    [ -f "$f" ] || continue
    n="${f##*/}"
    if [[ "$n" == trl-* ]] || grep -qx "User=${RUN_USER}" "$f"; then list="$list $n"; fi
  done
  for n in $list; do
    [[ "$EXCLUDE_UNITS" == *" $n "* ]] && continue
    [[ "$SKIP_UNITS" == *" $n "* ]] && continue
    echo "$n"
  done | sort -u
}

write_dropins() {
  local u why
  for u in $(units_to_harden); do
    if why=$(unit_uses_sudo "$u"); then
      warn "$u 는 실행 파일($why)에 sudo 가 있어 드롭인에서 뺌 — 운영자 확인 필요"
      continue
    fi
    mkdir -p "$SYSD/$u.d"
    dropin_content >"$SYSD/$u.d/$DROPIN_NAME"
    chmod 0644 "$SYSD/$u.d/$DROPIN_NAME"
    echo "드롭인: $u"
  done
}

# ── --check: 읽기만 ────────────────────────────────────────────
do_check() {
  set +e
  local home f
  home=$(getent passwd "$RUN_USER" | cut -d: -f6)
  echo "== id $RUN_USER"; id "$RUN_USER"
  echo "== sudo 권한($RUN_USER)"; sudo -n -l -U "$RUN_USER" 2>&1 || echo "(root 로 실행하면 보임: sudo bash $0 --check ...)"
  echo "== /etc/sudoers.d"; ls -la /etc/sudoers.d
  echo "== 90-cloud-init-users"; cat /etc/sudoers.d/90-cloud-init-users 2>&1
  echo "== 다른 sudoers 의 $RUN_USER 줄"; grep -nE "^[[:space:]]*${RUN_USER}[[:space:]]" /etc/sudoers /etc/sudoers.d/* 2>&1
  echo "== 유닛 내용"; systemctl cat trl-autopull.service trl-rt_kis.service trl-rt_serve.service --no-pager 2>&1
  echo "== trl-* 유닛 목록"; systemctl list-unit-files 'trl-*' --no-pager 2>&1
  echo "== 유닛별 User·ExecStart·NoNewPrivileges (드롭인 대상 후보)"
  for f in $(units_to_harden) trl-autopull.service trl-opsq.service; do
    echo "-- $f"; systemctl show -p User -p ExecStart -p NoNewPrivileges "$f" 2>&1 | sed 's/^/   /'
  done
  echo "== $home 를 실행하는데 User 가 없는(root 로 도는) 유닛"
  for f in "$SYSD"/*.service; do
    [ -f "$f" ] || continue
    if grep -q "$home/" "$f" && ! grep -q '^User=' "$f"; then echo "   주의: ${f##*/} (root 로 저장소·홈 파일 실행)"; fi
  done
  echo "== 서버 홈 스크립트의 sudo"; grep -n sudo "$home"/*.py "$home"/*.sh 2>/dev/null || echo "   없음"
  echo "== authorized_keys 지문($RUN_USER) — 운영자 키 말고 다른 줄이 없는지"
  ls -la "$home/.ssh/authorized_keys"; ssh-keygen -lf "$home/.ssh/authorized_keys"
  if [ -n "$ADMIN" ] && id "$ADMIN" >/dev/null 2>&1; then
    local ah; ah=$(getent passwd "$ADMIN" | cut -d: -f6)
    echo "== 관리 사용자 $ADMIN"; id "$ADMIN"; passwd -S "$ADMIN" 2>&1; ssh-keygen -lf "$ah/.ssh/authorized_keys" 2>&1
  fi
  echo "== 고정 사본"; ls -la /usr/local/lib/trl-autopull/ 2>&1; sha256sum /usr/local/lib/trl-autopull/autopull.sh 2>&1
  echo "== 드롭인 적용 상태"; ls "$SYSD"/*.service.d/"$DROPIN_NAME" 2>&1
  echo "(--check 는 아무것도 바꾸지 않음)"
}

# ── --apply ───────────────────────────────────────────────────
preflight() {   # 관리 사용자가 실제로 로그인해 sudo 를 쓸 수 있는지 — 안 되면 아무것도 바꾸지 않고 중단
  [ "$(id -u)" = 0 ] || die "root 로 실행해야 함(관리 사용자 세션에서 sudo bash ...)"
  [ "${SUDO_USER:-}" = "$ADMIN" ] || die "관리 사용자(${ADMIN})로 로그인한 세션에서 sudo 로 실행해야 함 — 지금 SUDO_USER='${SUDO_USER:-}'. 2단계(새 창에서 ${ADMIN} 로그인 → sudo 확인)를 먼저"
  id "$RUN_USER" >/dev/null 2>&1 || die "실행 사용자 없음: $RUN_USER"
  id "$ADMIN" >/dev/null 2>&1 || die "관리 사용자 없음: $ADMIN"
  id -nG "$ADMIN" | tr ' ' '\n' | grep -qx sudo || die "관리 사용자 ${ADMIN} 가 sudo 그룹이 아님"
  grep -Eq '^[[:space:]]*%sudo[[:space:]]+ALL[[:space:]]*=[[:space:]]*\(ALL(:ALL)?\)[[:space:]]+ALL' "$R/etc/sudoers" \
    || die "/etc/sudoers 에 '%sudo ALL=(ALL:ALL) ALL' 규칙이 없음 — 관리 사용자 sudo 가 보장되지 않음"
  local ah; ah=$(getent passwd "$ADMIN" | cut -d: -f6)
  [ -n "$ah" ] && [ -s "$R$ah/.ssh/authorized_keys" ] || die "관리 사용자 SSH 키 없음: $ah/.ssh/authorized_keys"
  [ "$(passwd -S "$ADMIN" | awk '{print $2}')" = P ] || die "관리 사용자 비밀번호가 없음(시리얼 콘솔·sudo 용) — sudo passwd ${ADMIN}"
  command -v visudo >/dev/null || die "visudo 없음"
}

install_sudoers_file() {   # $1=대상, 내용은 표준 입력. visudo 통과한 것만 설치
  local dst="$1" tmp
  tmp=$(mktemp "$R/etc/sudoers.d/.trl-tmp.XXXXXX")   # 이름에 '.' 이 있으면 sudo 가 읽지 않음
  cat >"$tmp"
  chmod 0440 "$tmp"; chown root:root "$tmp"
  if ! visudo -cf "$tmp" >/dev/null; then rm -f "$tmp"; die "visudo 검사 실패: $dst (바꾸지 않음)"; fi
  mv -f "$tmp" "$dst"
}

do_apply() {
  preflight
  # 이미 적용된 상태에서 다시 적용하면 '적용 뒤 상태'가 최신 백업이 되어 되돌리기가 불완전해짐 → 먼저 되돌리기
  if [ -e "$R/root/trl-backup-latest" ]; then die "이미 적용 기록이 있음($(cat "$R/root/trl-backup-latest")) — 다시 적용하려면 먼저 --rollback"; fi
  local ts B g removed="" f
  ts=$(date +%Y%m%d-%H%M%S)
  B="/root/trl-backup-$ts"
  mkdir -p "$R$B"; chmod 0700 "$R$B"
  cp -a "$R/etc/sudoers.d" "$R$B/sudoers.d"
  mkdir -p "$R$B/systemd"
  for f in "$SYSD"/trl-*; do [ -e "$f" ] && cp -a "$f" "$R$B/systemd/"; done
  echo "$RUN_USER" >"$R$B/user.txt"
  id -nG "$RUN_USER" >"$R$B/groups_before.txt"
  : >"$R$B/groups_removed.txt"
  echo "$B" >"$R/root/trl-backup-latest"
  echo "백업: $B"

  sudoers_content | install_sudoers_file "$R/etc/sudoers.d/$SUDOERS_NAME"
  echo "sudoers: /etc/sudoers.d/$SUDOERS_NAME (재시작 한 줄)"

  f="$R/etc/sudoers.d/90-cloud-init-users"
  if [ -f "$f" ] && grep -Eq "^[[:space:]]*${RUN_USER}[[:space:]]" "$f"; then
    sed -E "s|^([[:space:]]*${RUN_USER}[[:space:]].*)$|# trl-harden 해제(백업 $B): \\1|" "$f" | install_sudoers_file "$f"
    echo "90-cloud-init-users: ${RUN_USER} 전체 NOPASSWD 줄 주석 처리"
  fi
  if ! visudo -c >/dev/null; then
    cp -a "$R$B/sudoers.d/." "$R/etc/sudoers.d/"; rm -f "$R/etc/sudoers.d/$SUDOERS_NAME"
    die "전체 sudoers 검사 실패 — sudoers.d 를 백업으로 되돌림"
  fi
  if grep -lE "^[[:space:]]*${RUN_USER}[[:space:]]" "$R/etc/sudoers" "$R"/etc/sudoers.d/* 2>/dev/null \
       | grep -vE "/(${SUDOERS_NAME}|trl-opsq|90-cloud-init-users)$"; then
    warn "위 파일에 ${RUN_USER} sudo 줄이 더 있음 — 손대지 않았음, 운영자 확인 필요"
  fi

  for g in $DROP_GROUPS; do
    if id -nG "$RUN_USER" | tr ' ' '\n' | grep -qx "$g"; then
      gpasswd -d "$RUN_USER" "$g" >/dev/null
      echo "$g" >>"$R$B/groups_removed.txt"; removed="$removed $g"
    fi
  done
  echo "그룹 제거:${removed:- 없음}"

  write_dropins
  systemctl daemon-reload
  cat <<EOF
적용 완료. 남은 것:
 - 상시 서비스는 재시작해야 그룹 제거·NoNewPrivileges 가 적용됨(장 밖 시간에): sudo systemctl restart trl-rt_kis trl-rt_serve
 - 주기 작업(타이머) 유닛은 다음 실행부터 적용
 - ${RUN_USER} 의 열려 있는 ssh 세션은 로그아웃 뒤 새 그룹으로
 - 되돌리기: sudo bash $0 --rollback
EOF
}

do_rollback() {
  [ "$(id -u)" = 0 ] || die "root 로 실행"
  local B u g
  B=$(cat "$R/root/trl-backup-latest" 2>/dev/null) || die "백업 기록 없음: /root/trl-backup-latest"
  [[ "$B" =~ ^/root/trl-backup-[0-9]{8}-[0-9]{6}$ ]] && [ -d "$R$B" ] || die "백업 폴더가 올바르지 않음: $B"
  u=$(cat "$R$B/user.txt"); valid_user "$u" || die "백업의 사용자 이름이 올바르지 않음"
  if [ -f "$R$B/sudoers.d/90-cloud-init-users" ]; then
    rm -f "$R/etc/sudoers.d/90-cloud-init-users"
    cp -p "$R$B/sudoers.d/90-cloud-init-users" "$R/etc/sudoers.d/90-cloud-init-users"
    echo "90-cloud-init-users 복원"
  fi
  rm -f "$R/etc/sudoers.d/$SUDOERS_NAME"
  while read -r g; do
    [[ "$g" =~ ^[a-z_][a-z0-9_-]*$ ]] || continue
    usermod -aG "$g" "$u"; echo "그룹 복원: $u → $g"
  done <"$R$B/groups_removed.txt"
  find "$SYSD" -path "*.service.d/$DROPIN_NAME" -type f -print -delete
  find "$SYSD" -mindepth 1 -maxdepth 1 -type d -name '*.service.d' -empty -delete
  visudo -c >/dev/null || warn "sudoers 검사 실패 — 백업 $B 에서 손으로 확인"
  systemctl daemon-reload
  mv -f "$R/root/trl-backup-latest" "$R/root/trl-backup-latest.rolledback-$(date +%Y%m%d-%H%M%S)"
  echo "되돌림 완료(백업 $B). 상시 서비스는 재시작해야 이전 상태: sudo systemctl restart trl-rt_kis trl-rt_serve"
}

case "$MODE" in
  check) do_check ;;
  apply) do_apply ;;
  rollback) do_rollback ;;
  render)
    mkdir -p "$R/etc/sudoers.d" "$SYSD"
    sudoers_content >"$R/etc/sudoers.d/$SUDOERS_NAME"
    write_dropins
    echo "생성(테스트): $R"
    ;;
esac
