"""keystore — PC·Oracle 공통 키·상태 폴더."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import keystore  # noqa: E402


class KeystoreTest(unittest.TestCase):
    def test_env_then_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "keys.env"
            f.write_text("# 주석\nKIS_APP_KEY=\"from-file\"\nKIS_APP_SECRET=sec\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"TRL_KEYS_FILE": str(f)}, clear=False), \
                    mock.patch.object(keystore, "_from_registry", lambda n: ""):
                for k in ("KIS_APP_KEY", "KIS_APP_SECRET"):
                    os.environ.pop(k, None)   # PC 실제 키가 테스트에 섞이지 않게
                self.assertEqual(keystore.get("KIS_APP_KEY"), "from-file")
                self.assertEqual(keystore.pair("KIS_APP_KEY", "KIS_APP_SECRET"), ("from-file", "sec"))
                with mock.patch.dict(os.environ, {"KIS_APP_KEY": "from-env"}):
                    self.assertEqual(keystore.get("KIS_APP_KEY"), "from-env")      # 환경변수 우선

    def test_nh_from_keys_file_then_nhplug_env(self):
        with tempfile.TemporaryDirectory() as d:
            kf, nf = Path(d) / "keys.env", Path(d) / "nh.env"
            nf.write_text("NHPLUG_APP_KEY=nh-file\nNHPLUG_APP_SECRET=nh-sec\n", encoding="utf-8")
            kf.write_text("KIS_APP_KEY=x\n", encoding="utf-8")
            env = {"TRL_KEYS_FILE": str(kf), "NHPLUG_ENV_FILE": str(nf)}
            with mock.patch.dict(os.environ, env), mock.patch.object(keystore, "_from_registry", lambda n: ""):
                for k in ("NHPLUG_APP_KEY", "KIS_APP_SECRET"):
                    os.environ.pop(k, None)
                self.assertEqual(keystore.get("NHPLUG_APP_KEY"), "nh-file")          # nhplug 설정 파일
                self.assertEqual(keystore.get("KIS_APP_SECRET"), "")                 # NHPLUG_ 아닌 이름은 안 봄
                kf.write_text("NHPLUG_APP_KEY=from-keys\n", encoding="utf-8")
                self.assertEqual(keystore.get("NHPLUG_APP_KEY"), "from-keys")        # keys.env 우선

    def test_linux_state_dir(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_STATE_HOME": d}):
            self.assertEqual(keystore.state_dir("posix"), Path(d) / "trendlab")

    def test_no_registry_on_linux(self):
        with mock.patch.object(keystore.os, "name", "posix"):
            self.assertEqual(keystore._from_registry("KIS_APP_KEY"), "")


if __name__ == "__main__":
    unittest.main()
