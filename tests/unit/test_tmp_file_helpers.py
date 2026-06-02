"""
Юнит-тесты на хелперы из интеграционных тестов
"""

import unittest
from pathlib import Path
from integration.test_ssh_change_password import (
    TmpFileTestCase,
    _read_tmp,
    _make_entry,
    _make_kp,
)

# ── Указываем модулю на временный файл ДО импорта ────────────────────────────
PATH_TMP_DIR = Path(__file__).parent.parent / "data"
PATH_FILE_TMP = PATH_TMP_DIR / "servers.tmp"

# # Патчим PATH_FILE_TMP на уровне модуля до его загрузки
import keepass_tui.ssh.passwords as pw_mod  # noqa E402

pw_mod.PATH_FILE_TMP = PATH_FILE_TMP


class TestTmpFileHelpers(TmpFileTestCase):
    def test_tmp_write_creates_valid_jsonl(self):
        pw_mod._tmp_write("1.2.3.4", "root", "P@ss1")
        records = _read_tmp()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["ip"], "1.2.3.4")
        self.assertEqual(records[0]["username"], "root")
        self.assertEqual(records[0]["password"], "P@ss1")
        self.assertIn("date", records[0])

    def test_tmp_write_appends(self):
        pw_mod._tmp_write("1.1.1.1", "u1", "pw1")
        pw_mod._tmp_write("2.2.2.2", "u2", "pw2")
        self.assertEqual(len(_read_tmp()), 2)

    def test_tmp_read_empty_when_no_file(self):
        self.assertFalse(PATH_FILE_TMP.exists())
        self.assertEqual(pw_mod._tmp_read(), [])

    def test_find_kp_entry_matches_various_url_formats(self):
        IP, USER = "192.168.1.10", "admin"

        for url in [IP, f"ssh://{IP}", f"ssh://{IP}/", f"ssh://{IP}:22"]:
            with self.subTest(url=url):
                entry = _make_entry(USER, url, "pw")
                kp = _make_kp([entry])
                found = pw_mod._find_kp_entry(kp, IP, USER)
                self.assertIsNotNone(found, f"запись не найдена для url={url!r}")

    def test_find_kp_entry_returns_none_for_wrong_user(self):
        entry = _make_entry("other", "10.0.0.1", "pw")
        kp = _make_kp([entry])
        self.assertIsNone(pw_mod._find_kp_entry(kp, "10.0.0.1", "admin"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
