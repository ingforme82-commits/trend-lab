"""Oracle autopull 보안(11/22 티켓) 테스트 — 서버·네트워크 없이, 표준 라이브러리만.

  python scripts/test_oracle_harden.py -v

실제 /etc 는 건드리지 않는다: 설치·권한 스크립트는 --render(폴더에 결과만) 또는 --apply --root <임시 폴더>
+ 가짜 시스템 명령(id·getent·passwd·visudo·gpasswd·usermod·systemctl·chown)으로만 돌린다.
Windows 에서는 Git Bash 를 쓴다(System32 의 WSL bash 아님). 다른 bash: 환경변수 TRL_BASH.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
AUTOPULL = SCRIPTS / "oracle_autopull.sh"
INSTALL = SCRIPTS / "oracle_autopull_install.sh"
HARDEN = SCRIPTS / "oracle_harden.sh"
RT_SETUP = SCRIPTS / "oracle_rt_setup.sh"
KEYS_EXPORT = ROOT / "tools" / "keys_export.py"
COPY_REL = "usr/local/lib/trl-autopull/autopull.sh"


def find_bash() -> str | None:
    if os.environ.get("TRL_BASH"):
        return os.environ["TRL_BASH"]
    if os.name == "nt":
        for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if Path(p).exists():
                return p
        w = shutil.which("bash")
        return None if (w is None or "system32" in w.lower()) else w
    return shutil.which("bash")


BASH = find_bash()


def posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def run(args: list[str], env: dict | None = None, fake_bin: Path | None = None) -> subprocess.CompletedProcess:
    """bash 실행. fake_bin 은 bash 안에서 PATH 맨 앞에 붙인다(Git Bash 실행기가 PATH 앞에 /usr/bin 을 넣기 때문)."""
    e = dict(os.environ)
    e.pop("SUDO_USER", None)
    if env:
        e.update(env)
    if fake_bin is not None:
        args = ["-c", 'p=$(cygpath -u "$1" 2>/dev/null || echo "$1"); PATH="$p:$PATH"; shift; exec bash "$@"', "_", posix(fake_bin), *args]
    return subprocess.run([BASH, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)


def files_under(d: Path) -> list[str]:
    return sorted(posix(p.relative_to(d)) for p in d.rglob("*") if p.is_file())


def restart_in_copy(text: str) -> str:
    m = re.findall(r"/usr/bin/sudo -n ([^;\n]+);", text)
    assert len(m) == 1, m
    return m[0].strip()


def sudoers_rules(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


@unittest.skipIf(BASH is None, "bash 없음")
class TestAutopullInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trlh_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def render(self, user="ubuntu", home="/home/ubuntu"):
        return run([posix(INSTALL), "--render", posix(self.tmp), "--user", user, "--home", home])

    def test_1_unit_runs_fixed_copy(self):
        r = self.render()
        self.assertEqual(r.returncode, 0, r.stderr)
        svc = (self.tmp / "etc/systemd/system/trl-autopull.service").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/local/lib/trl-autopull/autopull.sh\n", svc)
        self.assertIn("User=ubuntu\n", svc)
        self.assertNotIn("projects", svc)                     # 저장소 경로 없음
        self.assertNotIn("oracle_autopull.sh", svc)
        tmr = (self.tmp / "etc/systemd/system/trl-autopull.timer").read_text(encoding="utf-8")
        self.assertIn("OnBootSec=2min", tmr)
        self.assertIn("OnUnitActiveSec=5min", tmr)

    def test_2_copy_does_not_execute_repo(self):
        self.assertEqual(self.render().returncode, 0)
        text = (self.tmp / COPY_REL).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/bash\n"))
        code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        body = "\n".join(code)
        self.assertNotIn("$HOME", body)
        self.assertNotIn("${HOME", body)
        self.assertIn('REPOS=("/home/ubuntu/projects/trend-lab-site" "/home/ubuntu/projects/market-site")', body)
        for ln in code:
            self.assertNotRegex(ln, r"(^|[;&|\s])(source|\.)\s", ln)
            self.assertNotRegex(ln, r"\bpython", ln)
            self.assertNotRegex(ln, r"\bbash\s", ln)
        self.assertIn("core.hooksPath=/dev/null pull --ff-only", body)
        self.assertIn('!= "ubuntu" ]', body)                 # 다른 사용자로 돌면 중단
        self.assertNotIn("@@TRL-CONFIG", text)
        # 경로를 만드는 데 쓰는 변수는 사본 안에서 정한 것뿐(REPOS·d·err·GIT 등)
        env_like = set(re.findall(r"\$\{?([A-Z_][A-Z0-9_]*)", body)) - {"REPOS", "GIT", "RESTART_WHEN"}
        self.assertEqual(env_like, set(), env_like)

    def test_3_restart_matches_sudoers(self):
        self.assertEqual(self.render().returncode, 0)
        copy_cmd = restart_in_copy((self.tmp / COPY_REL).read_text(encoding="utf-8"))
        h = self.tmp / "h"
        r = run([posix(HARDEN), "--render", posix(h), "--user", "ubuntu"])
        self.assertEqual(r.returncode, 0, r.stderr)
        rules = sudoers_rules((h / "etc/sudoers.d/trl-autopull").read_text(encoding="utf-8"))
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].split("NOPASSWD:", 1)[1].strip(), copy_cmd)
        self.assertEqual(copy_cmd, "/usr/bin/systemctl restart trl-rt_kis trl-rt_serve")
        # 템플릿(설치 전 직접 실행 경로)도 같은 줄
        self.assertEqual(restart_in_copy(AUTOPULL.read_text(encoding="utf-8")), copy_cmd)

    def test_5_bad_user_rejected_nothing_made(self):
        for bad in ("ubuntu; rm", "../x", "", "Root", "a b", "ubuntu\nroot"):
            d = self.tmp / "bad"
            r = run([posix(INSTALL), "--render", posix(d), "--user", bad, "--home", "/home/ubuntu"])
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertFalse(d.exists(), bad)
        for bad_home in ("/home/../etc", "relative", "/home/u buntu", "/"):
            d = self.tmp / "badh"
            r = run([posix(INSTALL), "--render", posix(d), "--user", "ubuntu", "--home", bad_home])
            self.assertNotEqual(r.returncode, 0, bad_home)
            self.assertFalse(d.exists(), bad_home)
        r = run([posix(INSTALL), "--render", posix(self.tmp / "root"), "--user", "root", "--home", "/root"])
        self.assertNotEqual(r.returncode, 0)


@unittest.skipIf(BASH is None, "bash 없음")
class TestHarden(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trlh_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_units(self, root: Path):
        sysd = root / "etc/systemd/system"
        sysd.mkdir(parents=True, exist_ok=True)
        units = {
            "trl-rt_kis.service": "User=ubuntu\nExecStart=/usr/bin/python3 /home/ubuntu/projects/trend-lab-site/tools/rt_kis.py\n",
            "trl-rt_serve.service": "User=ubuntu\nExecStart=/usr/bin/python3 /home/ubuntu/projects/trend-lab-site/tools/rt_serve.py\n",
            "trl-autopull.service": "User=ubuntu\nExecStart=/usr/local/lib/trl-autopull/autopull.sh\n",
            "trl-opsq.service": "User=ubuntu\nExecStart=/usr/bin/python3 /home/ubuntu/projects/market-site/oracle/opsq.py\n",
            "site-news.service": "User=ubuntu\nExecStart=/usr/bin/python3 /home/ubuntu/oracle_site_runtime.py news\n",
            "site-sudo.service": "User=ubuntu\nExecStart=/usr/bin/python3 /home/ubuntu/uses_sudo.py\n",
            "nginx.service": "ExecStart=/usr/sbin/nginx\n",
        }
        for n, body in units.items():
            (sysd / n).write_text("[Service]\n" + body, encoding="utf-8", newline="\n")
        home = root / "home/ubuntu"
        home.mkdir(parents=True, exist_ok=True)
        (home / "uses_sudo.py").write_text("import os\nos.system('sudo systemctl restart x')\n", encoding="utf-8")
        (home / "oracle_site_runtime.py").write_text("print('ok')\n", encoding="utf-8")

    def test_4_render_sudoers_and_dropins(self):
        self.fake_units(self.tmp)
        r = run([posix(HARDEN), "--render", posix(self.tmp), "--user", "ubuntu"])
        self.assertEqual(r.returncode, 0, r.stderr)
        rules = sudoers_rules((self.tmp / "etc/sudoers.d/trl-autopull").read_text(encoding="utf-8"))
        self.assertEqual(len(rules), 1, rules)
        self.assertRegex(rules[0], r"^ubuntu ALL=\(root\) NOPASSWD: /")
        cmd = rules[0].split("NOPASSWD:", 1)[1].strip()
        self.assertTrue(cmd.startswith("/usr/bin/systemctl "))
        self.assertNotIn("*", cmd)
        self.assertNotRegex(cmd, r"\bALL\b")
        self.assertNotRegex(cmd, r"\b(bash|sh)\b")
        dropins = [p for p in files_under(self.tmp) if p.endswith("/trl-hardening.conf")]
        names = sorted(p.split("/")[-2] for p in dropins)
        self.assertEqual(names, ["site-news.service.d", "trl-rt_kis.service.d", "trl-rt_serve.service.d"])
        self.assertIn("site-sudo.service", r.stderr)                 # sudo 쓰는 유닛은 빼고 경고
        for p in dropins:
            self.assertIn("NoNewPrivileges=yes", (self.tmp / p).read_text(encoding="utf-8"))

    def test_5_bad_user_rejected_nothing_made(self):
        for bad in ("ubuntu; rm", "../x", ""):
            d = self.tmp / "bad"
            r = run([posix(HARDEN), "--render", posix(d), "--user", bad])
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertFalse(d.exists(), bad)
        d = self.tmp / "badunit"
        r = run([posix(HARDEN), "--render", posix(d), "--user", "ubuntu", "--unit", "../../x"])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(d.exists())

    # ── --apply: 가짜 시스템 명령 ──────────────────────────────
    def fake_bin(self, admin_groups="trladmin sudo", admin_pw="P") -> Path:
        b = self.tmp / "fakebin"
        b.mkdir(exist_ok=True)
        log = posix(self.tmp / "calls.log")
        cmds = {
            "id": f"""case "$1" in
  -u) echo 0 ;;
  -un) echo root ;;
  -nG) if [ "$2" = trladmin ]; then echo "{admin_groups}"; else echo "ubuntu adm sudo lxd"; fi ;;
  ubuntu|trladmin) echo "uid=1000($1)" ;;
  *) exit 1 ;;
esac""",
            "getent": 'case "$2" in ubuntu) echo "ubuntu:x:1000:1000::/home/ubuntu:/bin/bash";; '
                      'trladmin) echo "trladmin:x:1001:1001::/home/trladmin:/bin/bash";; *) exit 2;; esac',
            "passwd": f'echo "$2 {admin_pw} 2026-11-22 0 99999 7 -1"',
            "visudo": "exit 0",
            "gpasswd": "exit 0",
            "usermod": "exit 0",
            "systemctl": "exit 0",
            "chown": "exit 0",
        }
        for n, body in cmds.items():
            p = b / n
            p.write_text(f'#!/bin/bash\necho "{n} $*" >> "{log}"\n{body}\n', encoding="utf-8", newline="\n")
            p.chmod(0o755)
        return b

    def fake_root(self) -> Path:
        r = self.tmp / "root"
        self.fake_units(r)
        (r / "etc/sudoers.d").mkdir(parents=True)
        (r / "etc/sudoers").write_text("root ALL=(ALL:ALL) ALL\n%sudo   ALL=(ALL:ALL) ALL\n", encoding="utf-8", newline="\n")
        (r / "etc/sudoers.d/90-cloud-init-users").write_text(
            "# Created by cloud-init\n# User rules for ubuntu\nubuntu ALL=(ALL) NOPASSWD:ALL\n", encoding="utf-8", newline="\n")
        (r / "root").mkdir()
        ak = r / "home/trladmin/.ssh"
        ak.mkdir(parents=True)
        (ak / "authorized_keys").write_text("ssh-ed25519 AAAAfake operator\n", encoding="utf-8")
        return r

    def apply(self, root: Path, fb: Path, sudo_user: str | None):
        env = {"SUDO_USER": sudo_user} if sudo_user is not None else None
        return run([posix(HARDEN), "--apply", "--user", "ubuntu", "--admin", "trladmin", "--root", posix(root)], env, fb)

    def assert_untouched(self, root: Path, before: list[str]):
        self.assertEqual(files_under(root), before)
        self.assertIn("NOPASSWD:ALL", (root / "etc/sudoers.d/90-cloud-init-users").read_text(encoding="utf-8"))
        calls = (self.tmp / "calls.log").read_text(encoding="utf-8") if (self.tmp / "calls.log").exists() else ""
        self.assertNotRegex(calls, r"(?m)^(gpasswd|usermod|systemctl) ")

    def test_8_apply_aborts_without_admin_session(self):
        root = self.fake_root()
        before = files_under(root)
        # (a) 관리 사용자 세션이 아님(ubuntu 에서 sudo, 또는 SUDO_USER 없음)
        for su in (None, "ubuntu"):
            r = self.apply(root, self.fake_bin(), su)
            self.assertNotEqual(r.returncode, 0, su)
            self.assertIn("중단", r.stderr)
            self.assert_untouched(root, before)
        # (b) 관리 사용자 sudo 그룹 아님
        r = self.apply(root, self.fake_bin(admin_groups="trladmin"), "trladmin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sudo 그룹", r.stderr)
        self.assert_untouched(root, before)
        # (c) 관리 사용자 비밀번호 없음
        r = self.apply(root, self.fake_bin(admin_pw="L"), "trladmin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("비밀번호", r.stderr)
        self.assert_untouched(root, before)

    def test_8b_apply_and_rollback_with_fakes(self):
        root = self.fake_root()
        r = self.apply(root, self.fake_bin(), "trladmin")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rules = sudoers_rules((root / "etc/sudoers.d/trl-autopull").read_text(encoding="utf-8"))
        self.assertEqual(rules, ["ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart trl-rt_kis trl-rt_serve"])
        self.assertEqual(sudoers_rules((root / "etc/sudoers.d/90-cloud-init-users").read_text(encoding="utf-8")), [])
        calls = (self.tmp / "calls.log").read_text(encoding="utf-8")
        self.assertIn("gpasswd -d ubuntu sudo", calls)
        self.assertIn("gpasswd -d ubuntu lxd", calls)
        self.assertNotIn("gpasswd -d ubuntu adm", calls)
        self.assertIn("systemctl daemon-reload", calls)
        self.assertTrue((root / "etc/systemd/system/trl-rt_kis.service.d/trl-hardening.conf").exists())
        self.assertFalse((root / "etc/systemd/system/trl-autopull.service.d").exists())
        self.assertFalse((root / "etc/systemd/system/trl-opsq.service.d").exists())
        latest = (root / "root/trl-backup-latest").read_text(encoding="utf-8").strip()
        self.assertRegex(latest, r"^/root/trl-backup-\d{8}-\d{6}$")
        self.assertIn("NOPASSWD:ALL", (root / latest.lstrip("/") / "sudoers.d/90-cloud-init-users").read_text(encoding="utf-8"))
        # 되돌리기
        r = run([posix(HARDEN), "--rollback", "--root", posix(root)], None, self.fake_bin())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((root / "etc/sudoers.d/trl-autopull").exists())
        self.assertIn("ubuntu ALL=(ALL) NOPASSWD:ALL", (root / "etc/sudoers.d/90-cloud-init-users").read_text(encoding="utf-8"))
        self.assertEqual([p for p in files_under(root) if p.endswith("trl-hardening.conf")], [])
        calls = (self.tmp / "calls.log").read_text(encoding="utf-8")
        self.assertIn("usermod -aG sudo ubuntu", calls)
        self.assertIn("usermod -aG lxd ubuntu", calls)
        self.assertFalse((root / "root/trl-backup-latest").exists())   # 되돌린 기록은 치움

    def test_8c_reapply_refused_until_rollback(self):
        """이미 적용된 상태에서 다시 적용하면 최신 백업이 '적용 뒤'가 되어 되돌리기가 불완전 → 거부(CTO 검증 11/22)."""
        root = self.fake_root()
        r = self.apply(root, self.fake_bin(), "trladmin")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        first = (root / "root/trl-backup-latest").read_text(encoding="utf-8")
        r = self.apply(root, self.fake_bin(), "trladmin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--rollback", r.stderr)
        self.assertEqual((root / "root/trl-backup-latest").read_text(encoding="utf-8"), first)


class TestStatic(unittest.TestCase):
    def test_6_rt_setup_no_direct_autopull(self):
        text = RT_SETUP.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"ExecStart=.*oracle_autopull\.sh")
        self.assertNotIn("/etc/systemd/system/trl-autopull", text)
        self.assertIn("oracle_autopull_install.sh", text)

    @unittest.skipIf(BASH is None, "bash 없음")
    def test_7_bash_syntax(self):
        for f in (AUTOPULL, INSTALL, HARDEN, RT_SETUP):
            r = run(["-n", posix(f)])
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr}")
            self.assertNotIn(b"\r", f.read_bytes(), f"{f.name}: CRLF")
        sc = shutil.which("shellcheck")
        if sc:
            r = subprocess.run([sc, "-S", "warning", *map(str, (AUTOPULL, INSTALL, HARDEN))], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)

    @unittest.skipIf(BASH is None, "bash 없음")
    def test_7b_rendered_copy_syntax(self):
        d = Path(tempfile.mkdtemp(prefix="trlh_"))
        try:
            r = run([posix(INSTALL), "--render", posix(d), "--user", "ubuntu", "--home", "/home/ubuntu"])
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run(["-n", posix(d / COPY_REL)])
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_9_keys_export_powershell_text(self):
        """운영자 PC(PowerShell 5.1)에 붙여넣는 안내: cmd 문법·&&·자리표시·서버 주소 없음."""
        doc = KEYS_EXPORT.read_text(encoding="utf-8")
        start = doc.index("[1] PC PowerShell")
        pc = doc[start:doc.index("[2] 서버")]
        server = doc[doc.index("[2] 서버"):doc.index('"""', start)]
        self.assertNotIn("%USERPROFILE%", doc)
        self.assertNotRegex(doc, r"(?m)^\s*del\s")
        self.assertNotIn("<서버IP>", doc)
        self.assertNotIn("@<", doc)
        self.assertNotIn("&&", pc)
        self.assertIn("$env:USERPROFILE", pc)
        self.assertIn("Remove-Item", pc)
        self.assertIn("${env:TRL_ORACLE_HOST}:", pc)
        self.assertIn('cat "$n"', server)            # 덮어쓰기 아닌 덧붙이기
        self.assertIn("chmod 600", server)
        self.assertIn('rm -f "$n"', server)
        self.assertTrue(doc.lstrip().startswith('r"""'))   # \t·\n 이스케이프 사고 방지

    def test_10_no_server_address_in_public_files(self):
        ip = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        for f in (AUTOPULL, INSTALL, HARDEN, RT_SETUP, KEYS_EXPORT):
            self.assertEqual(ip.findall(f.read_text(encoding="utf-8")), [], f.name)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main()
