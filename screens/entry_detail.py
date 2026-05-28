"""Экран детального просмотра одной записи."""

import curses
from typing import Optional

from ui.widgets import draw_box, safe_addstr, render_hint, trunc
from ui.colors import C_TITLE, C_DIM, C_VALUE, C_GOOD
from ui.clipboard import copy_to_clipboard


def screen_entry_detail(stdscr, entry, kp=None, db_path=None) -> Optional[str]:
    """Детальный просмотр записи с возможностью копирования пароля.

    Returns:
        "quit" если пользователь выбрал выход, None — просто назад.
    """
    show_pw = False
    copied  = ""
    has_url = bool((entry.url or "").strip())

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, entry.title or "Запись")

        fields = [
            ("Название",  entry.title    or ""),
            ("Группа",    entry.group.name if entry.group else ""),
            ("Логин",     entry.username  or ""),
            ("Пароль",    entry.password  or ""),
            ("URL",       entry.url       or ""),
            ("Заметки",   (entry.notes or "").replace("\n", " ").strip()),
        ]

        row = 2
        for label, value in fields:

            if row >= h - 5:
                break

            safe_addstr(stdscr, row, 3, f"{label}:",
                        curses.color_pair(C_TITLE) | curses.A_BOLD)

            if label == "Пароль":
                actual  = entry.password or ""
                display = actual if show_pw else "●" * min(len(actual), 20) or "(пусто)"
                safe_addstr(stdscr, row, 14, trunc(display, w - 16),
                            curses.color_pair(C_VALUE))
            else:
                safe_addstr(stdscr, row, 14, trunc(value, w - 16),
                            curses.color_pair(C_DIM))
            row += 2

        if copied:
            safe_addstr(stdscr, h - 4, 3, f"✓ {copied} скопировано в буфер",
                        curses.color_pair(C_GOOD))

        hint = [("p", "пароль"), ("c", "копировать пароль")]

        if has_url and kp:
            hint.append(("r", "сменить пароль"))

        hint.append(("q", "назад"))
        render_hint(stdscr, h - 3, w, hint)

        stdscr.refresh()
        key = stdscr.getch()

        if key == ord('p'):
            show_pw = not show_pw
            copied  = ""

        elif key == ord('c'):
            copy_to_clipboard(entry.password or "")
            copied = "Пароль"

        elif key == ord('r') and has_url and kp:
            # отложенный импорт для разрыва циклической зависимости
            from .ssh_screens import screen_change_password
            screen_change_password(stdscr, entry, kp, db_path)
            copied = ""

        elif key in (ord('q'), 27):
            return None
