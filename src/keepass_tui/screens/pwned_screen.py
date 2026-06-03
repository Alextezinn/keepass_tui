"""Экраны проверки паролей на утечки (HaveIBeenPwned)."""

import curses

from keepass_tui.security.hibp import is_password_pwned
from keepass_tui.ui.widgets import draw_box, safe_addstr, render_hint, trunc
from keepass_tui.ui.colors import C_TITLE, C_DIM, C_VALUE, C_WARN, C_GOOD


def screen_check_single(stdscr, entry) -> None:
    """Проверка пароля одной записи с окном подтверждения."""
    if not _confirm(stdscr, entry.title or "(без названия)"):
        return

    _draw_progress(stdscr, "Проверяю пароль...")

    try:
        pwned, count = is_password_pwned(entry.password or "")
        error = None
    except Exception as exc:
        pwned, count, error = False, 0, str(exc)

    _show_single_result(stdscr, entry, pwned, count, error)


def screen_check_all(stdscr, entries) -> None:
    """Массовая проверка всех записей с непустым паролем."""
    has_passwords = [e for e in entries if e.password]
    if not has_passwords:
        _show_message(stdscr, "Нет записей с паролем для проверки.")
        return

    if not _confirm_mass(stdscr, len(has_passwords)):
        return

    results = []
    total   = len(has_passwords)

    for i, entry in enumerate(has_passwords):
        _draw_progress(stdscr, f"Проверяю {i + 1}/{total}: {trunc(entry.title or '', 40)}...")
        try:
            pwned, count = is_password_pwned(entry.password or "")
            error = None
        except Exception as exc:
            pwned, count, error = False, 0, str(exc)
        results.append({"entry": entry, "pwned": pwned, "count": count, "error": error})

    _show_mass_result(stdscr, results)


# ─── Диалоги подтверждения ────────────────────────────────────────────────────

def _confirm(stdscr, entry_title: str) -> bool:
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Проверка утечек")

        safe_addstr(stdscr, 2, 3,
            "Пароль будет проверен по базе HaveIBeenPwned.",
            curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(stdscr, 3, 3,
            "На сервер отправляются только первые 5 символов SHA-1 хэша.",
            curses.color_pair(C_DIM))

        safe_addstr(stdscr, 5, 3, "Запись:", curses.color_pair(C_DIM))
        safe_addstr(stdscr, 5, 12, trunc(entry_title, w - 15),
            curses.color_pair(C_VALUE) | curses.A_BOLD)

        render_hint(stdscr, h - 3, w, [("Enter", "проверить"), ("q", "отмена")])
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            return True
        if key in (ord('q'), 27):
            return False


def _confirm_mass(stdscr, count: int) -> bool:
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Массовая проверка утечек")

        safe_addstr(stdscr, 2, 3,
            f"Будет проверено {count} записей через HaveIBeenPwned.",
            curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(stdscr, 3, 3,
            "На сервер отправляются только первые 5 символов SHA-1 хэша.",
            curses.color_pair(C_DIM))
        safe_addstr(stdscr, 4, 3,
            "Между запросами выдерживается пауза чтобы не превысить лимит API.",
            curses.color_pair(C_DIM))

        render_hint(stdscr, h - 3, w, [("Enter", "проверить"), ("q", "отмена")])
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            return True
        if key in (ord('q'), 27):
            return False


# ─── Результаты ───────────────────────────────────────────────────────────────

def _draw_progress(stdscr, text: str) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Проверка утечек")
    safe_addstr(stdscr, h // 2, 3, trunc(text, w - 6),
        curses.color_pair(C_WARN) | curses.A_BOLD)
    stdscr.refresh()


def _show_single_result(stdscr, entry, pwned: bool, count: int, error) -> None:
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Результат проверки")

        safe_addstr(stdscr, 2, 3, "Запись:", curses.color_pair(C_DIM))
        safe_addstr(stdscr, 2, 11, trunc(entry.title or "", w - 14),
            curses.color_pair(C_VALUE) | curses.A_BOLD)

        if error:
            safe_addstr(stdscr, 4, 3, "⚠  Ошибка при проверке:",
                curses.color_pair(C_WARN) | curses.A_BOLD)
            safe_addstr(stdscr, 5, 3, trunc(error, w - 6), curses.color_pair(C_WARN))
        elif pwned:
            safe_addstr(stdscr, 4, 3,
                f"✗  Пароль найден в утечках!",
                curses.color_pair(C_WARN) | curses.A_BOLD)
            safe_addstr(stdscr, 5, 3,
                f"Количество вхождений: {count:,}".replace(",", " "),
                curses.color_pair(C_WARN))
            safe_addstr(stdscr, 7, 3,
                "Рекомендуется немедленно сменить пароль.",
                curses.color_pair(C_DIM))
        else:
            safe_addstr(stdscr, 4, 3,
                "✓  Пароль не найден в известных утечках.",
                curses.color_pair(C_GOOD) | curses.A_BOLD)

        render_hint(stdscr, h - 3, w, [("q", "закрыть")])
        stdscr.refresh()

        if stdscr.getch() in (ord('q'), 27, curses.KEY_ENTER, 10, 13):
            return


def _show_mass_result(stdscr, results: list) -> None:
    pwned_list = [r for r in results if r["pwned"]]
    error_list = [r for r in results if r["error"]]
    safe_count = len(results) - len(pwned_list) - len(error_list)

    # Страница с итогами
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Результаты проверки утечек")

        safe_addstr(stdscr, 2, 3,
            f"Проверено: {len(results)}   "
            f"✓ Безопасных: {safe_count}   "
            f"✗ В утечках: {len(pwned_list)}   "
            f"⚠ Ошибок: {len(error_list)}",
            curses.color_pair(C_TITLE) | curses.A_BOLD)

        list_h = h - 8
        row    = 4

        # Сначала скомпрометированные
        for r in pwned_list[:list_h]:
            if row >= h - 4:
                break
            title = trunc(r["entry"].title or "", w // 2 - 4)
            count = f"{r['count']:,}".replace(",", " ")
            safe_addstr(stdscr, row, 3,
                f"✗ {title}",
                curses.color_pair(C_WARN) | curses.A_BOLD)
            safe_addstr(stdscr, row, w // 2,
                f"вхождений: {count}",
                curses.color_pair(C_WARN))
            row += 1

        # Потом ошибки
        for r in error_list:
            if row >= h - 4:
                break
            title = trunc(r["entry"].title or "", w // 2 - 4)
            safe_addstr(stdscr, row, 3,
                f"⚠ {title}",
                curses.color_pair(C_WARN))
            safe_addstr(stdscr, row, w // 2,
                trunc(r["error"] or "", w // 2 - 4),
                curses.color_pair(C_DIM))
            row += 1

        hint = [("q", "закрыть")]
        render_hint(stdscr, h - 3, w, hint)
        stdscr.refresh()

        if stdscr.getch() in (ord('q'), 27, curses.KEY_ENTER, 10, 13):
            return


def _show_message(stdscr, text: str) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Проверка утечек")
    safe_addstr(stdscr, h // 2, 3, trunc(text, w - 6), curses.color_pair(C_DIM))
    render_hint(stdscr, h - 3, w, [("q", "закрыть")])
    stdscr.refresh()
    stdscr.getch()