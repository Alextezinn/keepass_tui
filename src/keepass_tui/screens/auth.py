"""Экран авторизации: ввод мастер-пароля и ключевого файла."""

import curses
from typing import Optional, Tuple

from keepass_tui.ui.widgets import draw_box, safe_addstr, render_hint, trunc
from keepass_tui.ui.colors import C_TITLE, C_DIM, C_SELECTED, C_VALUE


def screen_enter_password(
    stdscr, db_path: str
) -> Tuple[Optional[str], Optional[str]]:
    """Ввод мастер-пароля и опционального ключевого файла.

    Returns:
        (password, keyfile) — строки (keyfile может быть None).
        (None, None)        — если пользователь нажал Esc.
    """
    password = ""
    keyfile  = ""
    field    = "password"   # "password" | "keyfile"

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Авторизация")

        safe_addstr(stdscr, 2, 3, f"База: {trunc(db_path, w - 10)}",
                    curses.color_pair(C_TITLE) | curses.A_BOLD)

        # Поле пароля
        safe_addstr(stdscr, 5, 3, "Мастер-пароль:", curses.color_pair(C_DIM))
        stars = "●" * len(password) + ("_" if field == "password" else "")
        pw_attr = (curses.color_pair(C_SELECTED) if field == "password"
                   else curses.color_pair(C_VALUE))
        safe_addstr(stdscr, 6, 5, f"[{trunc(stars, w - 10)}]", pw_attr)

        # Поле ключевого файла
        safe_addstr(stdscr, 9, 3, "Ключевой файл (необязательно):",
                    curses.color_pair(C_DIM))
        kf_display = trunc(keyfile, w - 10) + ("_" if field == "keyfile" else "")
        kf_attr = (curses.color_pair(C_SELECTED) if field == "keyfile"
                   else curses.color_pair(C_DIM))
        safe_addstr(stdscr, 10, 5, f"[{kf_display or ' '}]", kf_attr)

        render_hint(stdscr, h - 3, w, [
            ("Tab",   "следующее поле"),
            ("Enter", "открыть"),
            ("Esc",   "назад"),
        ])
        stdscr.refresh()

        key = stdscr.getch()
        if key == 27:
            return None, None

        elif key == ord('\t'):
            field = "keyfile" if field == "password" else "password"

        elif key in (curses.KEY_ENTER, 10, 13):
            return password, keyfile or None

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if field == "password":
                password = password[:-1]
            else:
                keyfile = keyfile[:-1]

        elif 32 <= key < 256:
            if field == "password":
                password += chr(key)
            else:
                keyfile += chr(key)
