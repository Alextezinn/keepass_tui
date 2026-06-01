"""
Тесты для keepass_cli/ssh/passwords.py

Покрываемые сценарии
────────────────────
1. Успешная смена пароля на сервере → tmp-файл удаляется.
2. Пароль сменён на сервере, но kp.save() упал →
   recover_from_tmp подключается с tmp-паролем (успех) → обновляет KeePass → удаляет файл.
3. Пароль сменён на сервере, kp.save() упал →
   recover_from_tmp подключается с tmp-паролем (успех) → kp.save() снова падает →
   файл НЕ удаляется.
4. Пароль записан в tmp, но SSH-смена провалилась →
   recover_from_tmp пробует подключиться → неудача → файл удаляется.

Реальные SSH-соединения не используются: все сетевые вызовы заменены моками.
"""

import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ── Указываем модулю на временный файл ДО импорта ────────────────────────────
PATH_TMP_DIR = Path(__file__).parent.parent / "data"
PATH_FILE_TMP = PATH_TMP_DIR / "servers.tmp"

# # Патчим PATH_FILE_TMP на уровне модуля до его загрузки
import keepass_tui.ssh.passwords as pw_mod
pw_mod.PATH_FILE_TMP = PATH_FILE_TMP


def _sync_delete_file() -> None:
    """Синхронно удаляет tmp-файл. Используется вместо fire-and-forget subprocess."""
    pw_mod.PATH_FILE_TMP.unlink(missing_ok=True)


# ── Вспомогательные фабрики ───────────────────────────────────────────────────

def _make_entry(username: str, url: str, password: str):
    """Минимальный объект записи KeePass."""
    e = SimpleNamespace(username=username, url=url, password=password)
    return e


def _make_kp(entries: list, save_ok: bool = True):
    """Минимальный объект PyKeePass с контролируемым save()."""
    kp = MagicMock()
    kp.entries = entries
    if save_ok:
        kp.save = MagicMock(return_value=None)
    else:
        kp.save = MagicMock(side_effect=IOError("disk full"))
    return kp


def _write_tmp(ip: str, username: str, password: str) -> None:
    """Записывает одну строку в тестовый tmp-файл."""
    record = {"ip": ip, "username": username, "password": password,
              "date": "2025-01-01 00:00:00"}

    with open(PATH_FILE_TMP, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_tmp() -> list[dict]:
    if not PATH_FILE_TMP.exists():
        return []

    out = []

    for line in PATH_FILE_TMP.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if line:
            out.append(json.loads(line))

    return out


def _wait_file_gone(path: Path, timeout: float = 2.0) -> bool:
    """Ждёт пока файл исчезнет (subprocess fire-and-forget)."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if not path.exists():
            return True

        time.sleep(0.05)

    return False


class TmpFileTestCase(unittest.TestCase):
    """
    Базовый класс с очисткой
    """
    def setUp(self):
        PATH_FILE_TMP.unlink(missing_ok=True)
        # Заменяем fire-and-forget subprocess на синхронное удаление —
        # исключает ResourceWarning и гонки в тестах
        self._patcher = patch.object(pw_mod, "_tmp_delete_file", side_effect=_sync_delete_file)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        PATH_FILE_TMP.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Сценарий 1: успешная смена — tmp удаляется через cleanup_tmp_against_keepass
# ══════════════════════════════════════════════════════════════════════════════

class TestSuccessfulPasswordChange(TmpFileTestCase):
    """
    Смена пароля прошла успешно, kp.save() отработал.
    cleanup_tmp_against_keepass должен удалить файл целиком,
    т.к. пароль в KeePass совпадает с паролем в tmp.
    """

    def test_tmp_file_deleted_after_successful_change(self):
        IP, USER, NEW_PW = "10.0.0.1", "admin", "NewP@ss1!"

        # Симулируем: tmp-файл уже содержит новый пароль (написан до save)
        _write_tmp(IP, USER, NEW_PW)
        self.assertTrue(PATH_FILE_TMP.exists(), "tmp-файл должен существовать до cleanup")

        # KeePass уже содержит этот же пароль (save прошёл успешно)
        entry = _make_entry(USER, f"ssh://{IP}", NEW_PW)
        kp = _make_kp([entry], save_ok=True)

        removed = pw_mod.cleanup_tmp_against_keepass(kp)

        self.assertEqual(removed, 1, "должна быть удалена 1 запись")
        gone = _wait_file_gone(PATH_FILE_TMP)
        self.assertTrue(gone, "tmp-файл должен быть удалён после успешной синхронизации")

    def test_tmp_file_partially_cleaned_when_one_entry_unsynced(self):
        """Если в tmp две записи и только одна синхронизирована — остаётся одна."""
        IP1, IP2, USER = "10.0.0.1", "10.0.0.2", "admin"
        PW_SYNCED = "Synced1!"
        PW_UNSYNCED = "OldPass1!"

        _write_tmp(IP1, USER, PW_SYNCED)
        _write_tmp(IP2, USER, PW_UNSYNCED)

        entry1 = _make_entry(USER, IP1, PW_SYNCED)   # совпадает
        entry2 = _make_entry(USER, IP2, "CurrentPw!")  # не совпадает
        kp = _make_kp([entry1, entry2], save_ok=True)

        # Патчим Popen так чтобы перезапись файла происходила синхронно:
        # перехватываем контент из stdin и пишем напрямую, без subprocess.
        def sync_popen(args, stdin=None, stdout=None, stderr=None, **kw):
            mock_proc = MagicMock()
            mock_proc.stdin = MagicMock()
            captured = []

            def write(data):
                captured.append(data)

            def close():
                content = b"".join(captured).decode("utf-8")
                pw_mod.PATH_FILE_TMP.write_text(content, encoding="utf-8")

            mock_proc.stdin.write = write
            mock_proc.stdin.close = close
            return mock_proc

        with patch("keepass_tui.ssh.passwords.subprocess.Popen", side_effect=sync_popen):
            removed = pw_mod.cleanup_tmp_against_keepass(kp)

        self.assertEqual(removed, 1)
        remaining = _read_tmp()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["ip"], IP2)


# ══════════════════════════════════════════════════════════════════════════════
# Сценарий 2: пароль сменён на сервере, kp.save() упал →
#             recover подключается (успех) → обновляет KeePass → удаляет файл
# ══════════════════════════════════════════════════════════════════════════════

class TestRecoverAfterSaveFailure(TmpFileTestCase):
    """
    Пароль на сервере уже новый, но в KeePass старый (save упал при первой попытке).
    recover_from_tmp: SSH-подключение с tmp-паролем успешно → обновляем KeePass → удаляем файл.
    """

    def test_recover_success_ssh_connects_kp_saved(self):
        IP, USER = "10.0.0.2", "deploy"
        OLD_PW = "OldPass1!"
        NEW_PW = "NewPass1!"

        # tmp содержит новый пароль, KeePass — ещё старый
        _write_tmp(IP, USER, NEW_PW)
        entry = _make_entry(USER, f"ssh://{IP}", OLD_PW)
        kp = _make_kp([entry], save_ok=True)

        with patch.object(pw_mod, "_ssh_check_connect", return_value=True) as mock_ssh:
            results = pw_mod.recover_from_tmp(kp)

        mock_ssh.assert_called_once_with(IP, USER, NEW_PW)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "recovered")

        # Пароль обновлён в объекте записи
        self.assertEqual(entry.password, NEW_PW)
        # kp.save() вызван
        kp.save.assert_called_once()
        # tmp-файл удалён
        gone = _wait_file_gone(PATH_FILE_TMP)
        self.assertTrue(gone, "tmp-файл должен быть удалён после успешного восстановления")

    def test_recover_ssh_connects_but_kp_save_fails_again(self):
        """
        SSH-подключение с tmp-паролем успешно, но kp.save() снова падает →
        функция возвращается немедленно, tmp-файл НЕ удаляется.
        """
        IP, USER = "10.0.0.3", "deploy"
        OLD_PW = "OldPass1!"
        NEW_PW = "NewPass1!"

        _write_tmp(IP, USER, NEW_PW)
        entry = _make_entry(USER, f"ssh://{IP}", OLD_PW)
        kp = _make_kp([entry], save_ok=False)   # save всегда падает

        with patch.object(pw_mod, "_ssh_check_connect", return_value=True):
            results = pw_mod.recover_from_tmp(kp)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("сохранить в KeePass не удалось", results[0]["detail"])

        # tmp-файл должен остаться — пароль не сохранён
        time.sleep(0.2)
        self.assertTrue(PATH_FILE_TMP.exists(),
                        "tmp-файл НЕ должен удаляться при повторном сбое kp.save()")


# ══════════════════════════════════════════════════════════════════════════════
# Сценарий 3: пароль записан в tmp, но SSH-смена не прошла →
#             recover пробует подключиться → неудача → файл удаляется
# ══════════════════════════════════════════════════════════════════════════════

class TestRecoverWhenSshChangeFailed(TmpFileTestCase):
    """
    Пароль был записан в tmp, но команда chpasswd на сервере не выполнилась
    (например, sudo недоступен). На сервере остался старый пароль.
    recover_from_tmp: SSH с tmp-паролем не проходит → запись устарела → файл удаляется.
    """

    def test_recover_ssh_fails_file_deleted(self):
        IP, USER = "10.0.0.4", "ops"
        OLD_PW = "OldPass1!"
        NEW_PW = "NeverApplied1!"

        # tmp содержит новый пароль, KeePass тоже хранит старый
        _write_tmp(IP, USER, NEW_PW)
        entry = _make_entry(USER, f"ssh://{IP}", OLD_PW)
        kp = _make_kp([entry], save_ok=True)

        # SSH с новым паролем не проходит — пароль на сервере не менялся
        with patch.object(pw_mod, "_ssh_check_connect", return_value=False) as mock_ssh:
            results = pw_mod.recover_from_tmp(kp)

        mock_ssh.assert_called_once_with(IP, USER, NEW_PW)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("устарела", results[0]["detail"])

        # kp.save() не должен вызываться — пароль не менялся
        kp.save.assert_not_called()
        # tmp-файл удаляется — запись устарела, хранить её бессмысленно
        gone = _wait_file_gone(PATH_FILE_TMP)
        self.assertTrue(gone, "tmp-файл должен быть удалён если SSH-подключение не удалось")

    def test_recover_ssh_fails_kp_password_unchanged(self):
        """Дополнительная проверка: пароль в KeePass остался старым."""
        IP, USER = "10.0.0.5", "ops"
        OLD_PW = "OldPass1!"
        NEW_PW = "NeverApplied1!"

        _write_tmp(IP, USER, NEW_PW)
        entry = _make_entry(USER, IP, OLD_PW)
        kp = _make_kp([entry], save_ok=True)

        with patch.object(pw_mod, "_ssh_check_connect", return_value=False):
            pw_mod.recover_from_tmp(kp)

        self.assertEqual(entry.password, OLD_PW,
                         "пароль в KeePass не должен меняться при неудачном SSH")


# ══════════════════════════════════════════════════════════════════════════════
# Дополнительно: _tmp_write / _tmp_read / _find_kp_entry
# ══════════════════════════════════════════════════════════════════════════════

class TestTmpFileHelpers(TmpFileTestCase):

    def test_tmp_write_creates_valid_jsonl(self):
        pw_mod._tmp_write("1.2.3.4", "root", "P@ss1")
        records = _read_tmp()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["ip"],       "1.2.3.4")
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
