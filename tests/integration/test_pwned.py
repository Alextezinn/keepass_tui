"""
Тесты для keepass_cli/keepass/pwned.py и логики screen_check_single / screen_check_all.

Что тестируется
───────────────
is_password_pwned:
  - пароль найден в утечках (возвращает True + count)
  - пароль не найден (False, 0)
  - повтор при 429 с Retry-After
  - исчерпаны все попытки при 429 → (False, 0)
  - сетевая ошибка URLError → пробрасывается
  - HTTP-ошибка не-429 → пробрасывается
  - корректность SHA-1 префикса/суффикса в запросе

screen_check_single (логика без curses):
  - пользователь подтверждает → is_password_pwned вызывается с паролем записи
  - пользователь отменяет → is_password_pwned не вызывается
  - пароль найден → результат pwned=True, count передаётся в _show_single_result
  - пароль не найден → pwned=False
  - is_password_pwned бросает исключение → error передаётся в _show_single_result

screen_check_all (логика без curses):
  - записи без пароля пропускаются
  - все записи с пустым паролем → _show_message вызывается, is_password_pwned нет
  - is_password_pwned вызывается ровно по одному разу для каждой записи с паролем
  - пользователь отменяет массовую проверку → is_password_pwned не вызывается
  - результаты разделяются на pwned / clean / error корректно
  - исключение в одной записи не прерывает проверку остальных
"""

import hashlib
import unittest
import urllib.error
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import keepass_tui.security.hibp as pwned_mod
import keepass_tui.screens.pwned_screen as screen_mod


# ── Вспомогательные фабрики ───────────────────────────────────────────────────


def _entry(title: str, password: str) -> SimpleNamespace:
    return SimpleNamespace(title=title, password=password)


def _mock_stdscr() -> MagicMock:
    """Минимальный stdscr-мок: размер терминала и getch."""
    stdscr = MagicMock()
    stdscr.getmaxyx.return_value = (40, 120)
    return stdscr


def _sha1_parts(password: str) -> tuple[str, str]:
    sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
    return sha1[:5], sha1[5:]


def _hibp_response(suffix: str, count: int, extra: list[str] | None = None) -> str:
    """Формирует ответ HIBP API: строка с нужным суффиксом + несколько случайных."""
    lines = [f"{suffix}:{count}"]
    lines += extra or ["AAAAA:1", "BBBBB:2", "CCCCC:999"]
    return "\n".join(lines)


# ── Мок urllib.request.urlopen ────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, body: str):
        self._data = body.encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def decode(self, enc="utf-8") -> str:
        return self._data.decode(enc)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    h = MagicMock()
    h.get = lambda key, default="": (headers or {}).get(key, default)
    return urllib.error.HTTPError(url="", code=code, msg="", hdrs=h, fp=BytesIO())


# ══════════════════════════════════════════════════════════════════════════════
# is_password_pwned
# ══════════════════════════════════════════════════════════════════════════════


class TestIsPasswordPwned(unittest.TestCase):
    def _patch_urlopen(self, response_body: str):
        return patch(
            "keepass_tui.keepass.pwned.urllib.request.urlopen",
            return_value=_FakeResponse(response_body),
        )

    # ── Основные сценарии ─────────────────────────────────────────────────────

    def test_password_found_returns_true_and_count(self):
        pw = "password123"
        _, suffix = _sha1_parts(pw)
        response_body = _hibp_response(suffix, 54321)

        with self._patch_urlopen(response_body):
            pwned, count = pwned_mod.is_password_pwned(pw)

        self.assertTrue(pwned)
        self.assertEqual(count, 54321)

    def test_password_not_found_returns_false_zero(self):
        pw = "very-unique-p@ssword-xyz-2025!"
        _, suffix = _sha1_parts(pw)
        # Ответ без нашего суффикса
        response_body = "AAAAA:1\nBBBBB:2\nCCCCC:3"

        with self._patch_urlopen(response_body):
            pwned, count = pwned_mod.is_password_pwned(pw)

        self.assertFalse(pwned)
        self.assertEqual(count, 0)

    def test_sends_only_sha1_prefix_not_full_hash(self):
        """На сервер должен уходить URL только с первыми 5 символами хэша."""
        pw = "secret"
        prefix, _ = _sha1_parts(pw)
        response_body = "AAAAA:1"

        with patch(
            "keepass_tui.keepass.pwned.urllib.request.urlopen",
            return_value=_FakeResponse(response_body),
        ) as mock_open:
            pwned_mod.is_password_pwned(pw)

        called_url = mock_open.call_args[0][0].full_url
        self.assertIn(prefix, called_url)
        self.assertNotIn(_sha1_parts(pw)[1], called_url)

    def test_count_parsed_correctly_for_large_number(self):
        pw = "qwerty"
        _, suffix = _sha1_parts(pw)
        response_body = _hibp_response(suffix, 3_500_000)

        with self._patch_urlopen(response_body):
            _, count = pwned_mod.is_password_pwned(pw)

        self.assertEqual(count, 3_500_000)

    def test_empty_password_handled(self):
        pw = ""
        _, suffix = _sha1_parts(pw)
        response_body = _hibp_response(suffix, 1)

        with self._patch_urlopen(response_body):
            pwned, count = pwned_mod.is_password_pwned(pw)

        self.assertTrue(pwned)
        self.assertEqual(count, 1)

    # ── Retry-логика ──────────────────────────────────────────────────────────

    def test_retries_on_429_then_succeeds(self):
        """При 429 делает повтор и в итоге получает ответ."""
        pw = "retry-test"
        _, suffix = _sha1_parts(pw)
        response_body = _hibp_response(suffix, 7)
        err_429 = _http_error(429, {"Retry-After": "0"})

        side_effects = [err_429, _FakeResponse(response_body)]

        with patch(
            "keepass_tui.keepass.pwned.urllib.request.urlopen", side_effect=side_effects
        ):
            with patch("keepass_tui.keepass.pwned.time.sleep") as mock_sleep:
                pwned, count = pwned_mod.is_password_pwned(pw, retries=3)

        self.assertTrue(pwned)
        self.assertEqual(count, 7)
        mock_sleep.assert_called_once_with(0)

    def test_exhausted_retries_on_429_raises_on_last_attempt(self):
        """На последней попытке 429 пробрасывается (нет следующего retry)."""
        err_429 = _http_error(429, {"Retry-After": "0"})

        with patch(
            "keepass_tui.keepass.pwned.urllib.request.urlopen",
            side_effect=[err_429, err_429, err_429],
        ):
            with patch("keepass_tui.keepass.pwned.time.sleep"):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    pwned_mod.is_password_pwned("pw", retries=3)

        self.assertEqual(ctx.exception.code, 429)

    def test_non_429_http_error_raises(self):
        """HTTP-ошибка с кодом не 429 должна пробрасываться."""
        with patch(
            "keepass_tui.keepass.pwned.urllib.request.urlopen",
            side_effect=_http_error(500),
        ):
            with self.assertRaises(urllib.error.HTTPError):
                pwned_mod.is_password_pwned("pw")

    def test_url_error_raises(self):
        """Сетевая ошибка URLError должна пробрасываться."""
        with patch(
            "keepass_tui.keepass.pwned.urllib.request.urlopen",
            side_effect=urllib.error.URLError("no network"),
        ):
            with self.assertRaises(urllib.error.URLError):
                pwned_mod.is_password_pwned("pw")


# ══════════════════════════════════════════════════════════════════════════════
# screen_check_single — логика (curses не используется)
# ══════════════════════════════════════════════════════════════════════════════


class TestScreenCheckSingle(unittest.TestCase):
    """
    Тестируем логику screen_check_single:
    - вызывается ли is_password_pwned с правильным паролем
    - вызывается ли _show_single_result с правильными аргументами
    - что происходит при отмене пользователем
    Curses-вызовы полностью замокированы.
    """

    def setUp(self):
        self.stdscr = _mock_stdscr()

    def _run(self, entry, confirm: bool, pwned_result=None, pwned_exc=None):
        """Запускает screen_check_single с нужными моками."""
        with patch.object(screen_mod, "_confirm", return_value=confirm), patch.object(
            screen_mod, "_draw_progress"
        ), patch.object(screen_mod, "_show_single_result") as mock_result, patch(
            "keepass_tui.screens.pwned_screen.is_password_pwned",
            return_value=pwned_result,
            side_effect=pwned_exc,
        ) as mock_pwned:
            screen_mod.screen_check_single(self.stdscr, entry)

        return mock_pwned, mock_result

    def test_confirmed_calls_is_password_pwned_with_entry_password(self):
        entry = _entry("GitHub", "secret123")
        mock_pwned, _ = self._run(entry, confirm=True, pwned_result=(False, 0))
        mock_pwned.assert_called_once_with("secret123")

    def test_cancelled_does_not_call_is_password_pwned(self):
        entry = _entry("GitHub", "secret123")
        mock_pwned, _ = self._run(entry, confirm=False)
        mock_pwned.assert_not_called()

    def test_cancelled_does_not_call_show_result(self):
        entry = _entry("GitHub", "secret123")
        _, mock_result = self._run(entry, confirm=False)
        mock_result.assert_not_called()

    def test_pwned_result_passed_to_show_single_result(self):
        entry = _entry("Gmail", "password")
        _, mock_result = self._run(entry, confirm=True, pwned_result=(True, 99999))
        args = mock_result.call_args[0]  # (stdscr, entry, pwned, count, error)
        self.assertIs(args[1], entry)
        self.assertTrue(args[2])  # pwned
        self.assertEqual(args[3], 99999)  # count
        self.assertIsNone(args[4])  # error

    def test_clean_result_passed_to_show_single_result(self):
        entry = _entry("Server", "str0ng-P@ss!")
        _, mock_result = self._run(entry, confirm=True, pwned_result=(False, 0))
        args = mock_result.call_args[0]
        self.assertFalse(args[2])
        self.assertEqual(args[3], 0)
        self.assertIsNone(args[4])

    def test_exception_passed_as_error_to_show_single_result(self):
        entry = _entry("Server", "pw")
        exc = urllib.error.URLError("timeout")
        _, mock_result = self._run(entry, confirm=True, pwned_exc=exc)
        args = mock_result.call_args[0]
        self.assertFalse(args[2])  # pwned=False при ошибке
        self.assertEqual(args[3], 0)  # count=0
        self.assertIsNotNone(args[4])  # error — строка с описанием

    def test_empty_password_still_calls_is_password_pwned(self):
        """Пустой пароль передаётся как есть — функция сама решает."""
        entry = _entry("NoPass", "")
        mock_pwned, _ = self._run(entry, confirm=True, pwned_result=(False, 0))
        mock_pwned.assert_called_once_with("")


# ══════════════════════════════════════════════════════════════════════════════
# screen_check_all — логика (curses не используется)
# ══════════════════════════════════════════════════════════════════════════════


class TestScreenCheckAll(unittest.TestCase):
    def setUp(self):
        self.stdscr = _mock_stdscr()

    def _run(self, entries, confirm: bool = True, pwned_side_effect=None):
        results_captured = {}

        def capture_mass_result(stdscr, results):
            results_captured["results"] = results

        with patch.object(
            screen_mod, "_confirm_mass", return_value=confirm
        ), patch.object(screen_mod, "_draw_progress"), patch.object(
            screen_mod, "_show_mass_result", side_effect=capture_mass_result
        ), patch.object(screen_mod, "_show_message") as mock_msg, patch(
            "keepass_tui.screens.pwned_screen.is_password_pwned",
            side_effect=pwned_side_effect or [(False, 0)] * 100,
        ) as mock_pwned:
            screen_mod.screen_check_all(self.stdscr, entries)

        return mock_pwned, mock_msg, results_captured.get("results")

    # ── Фильтрация записей ────────────────────────────────────────────────────

    def test_entries_without_password_skipped(self):
        entries = [_entry("A", "pw1"), _entry("B", ""), _entry("C", "pw2")]
        mock_pwned, _, _ = self._run(entries)
        self.assertEqual(mock_pwned.call_count, 2)
        calls = [c[0][0] for c in mock_pwned.call_args_list]
        self.assertIn("pw1", calls)
        self.assertIn("pw2", calls)
        self.assertNotIn("", calls)

    def test_all_empty_passwords_shows_message_not_check(self):
        entries = [_entry("A", ""), _entry("B", None)]
        mock_pwned, mock_msg, _ = self._run(entries)
        mock_pwned.assert_not_called()
        mock_msg.assert_called_once()

    def test_none_password_treated_as_empty(self):
        entries = [_entry("A", None)]
        mock_pwned, mock_msg, _ = self._run(entries)
        mock_pwned.assert_not_called()
        mock_msg.assert_called_once()

    # ── Подтверждение ─────────────────────────────────────────────────────────

    def test_cancelled_does_not_call_is_password_pwned(self):
        entries = [_entry("A", "pw1"), _entry("B", "pw2")]
        mock_pwned, _, _ = self._run(entries, confirm=False)
        mock_pwned.assert_not_called()

    def test_confirmed_calls_is_password_pwned_for_each_entry(self):
        entries = [_entry(f"E{i}", f"pw{i}") for i in range(5)]
        mock_pwned, _, _ = self._run(entries, confirm=True)
        self.assertEqual(mock_pwned.call_count, 5)

    def test_is_password_pwned_called_with_correct_passwords(self):
        entries = [_entry("A", "alpha"), _entry("B", "beta"), _entry("C", "gamma")]
        mock_pwned, _, _ = self._run(entries)
        expected = [call("alpha"), call("beta"), call("gamma")]
        self.assertEqual(mock_pwned.call_args_list, expected)

    # ── Результаты ────────────────────────────────────────────────────────────

    def test_results_contain_all_checked_entries(self):
        entries = [_entry("A", "pw1"), _entry("B", "pw2"), _entry("C", "pw3")]
        _, _, results = self._run(entries)
        self.assertEqual(len(results), 3)

    def test_pwned_entry_marked_correctly(self):
        entries = [_entry("Leaked", "password")]
        _, _, results = self._run(entries, pwned_side_effect=[(True, 42000)])
        self.assertTrue(results[0]["pwned"])
        self.assertEqual(results[0]["count"], 42000)
        self.assertIsNone(results[0]["error"])

    def test_clean_entry_marked_correctly(self):
        entries = [_entry("Safe", "str0ng!")]
        _, _, results = self._run(entries, pwned_side_effect=[(False, 0)])
        self.assertFalse(results[0]["pwned"])
        self.assertEqual(results[0]["count"], 0)
        self.assertIsNone(results[0]["error"])

    def test_exception_in_one_entry_does_not_stop_others(self):
        """Ошибка на одной записи не прерывает проверку остальных."""
        entries = [_entry("A", "pw1"), _entry("B", "pw2"), _entry("C", "pw3")]
        side_effects = [
            (False, 0),
            urllib.error.URLError("timeout"),
            (True, 500),
        ]
        _, _, results = self._run(entries, pwned_side_effect=side_effects)
        self.assertEqual(len(results), 3)
        self.assertIsNone(results[0]["error"])
        self.assertIsNotNone(results[1]["error"])
        self.assertFalse(results[1]["pwned"])
        self.assertTrue(results[2]["pwned"])

    def test_mixed_results_split_correctly(self):
        """pwned / clean / error правильно разделяются в итоговом списке."""
        entries = [
            _entry("Pwned1", "leaked1"),
            _entry("Clean1", "safe1"),
            _entry("Error1", "err1"),
            _entry("Pwned2", "leaked2"),
        ]
        side_effects = [
            (True, 1000),
            (False, 0),
            urllib.error.URLError("fail"),
            (True, 2000),
        ]
        _, _, results = self._run(entries, pwned_side_effect=side_effects)
        pwned = [r for r in results if r["pwned"]]
        errors = [r for r in results if r["error"]]
        clean = [r for r in results if not r["pwned"] and not r["error"]]
        self.assertEqual(len(pwned), 2)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(clean), 1)

    def test_result_entries_reference_original_objects(self):
        """results[i]['entry'] ссылается на исходный объект записи."""
        e1 = _entry("A", "pw1")
        e2 = _entry("B", "pw2")
        _, _, results = self._run([e1, e2])
        self.assertIs(results[0]["entry"], e1)
        self.assertIs(results[1]["entry"], e2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
