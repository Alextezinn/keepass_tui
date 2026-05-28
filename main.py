#!/usr/bin/env python3
"""
Интерактивный просмотрщик паролей KeePassXC.

Точка входа в приложение.
"""

import curses
import sys
from pathlib import Path

try:
    from pykeepass import PyKeePass
    from pykeepass.exceptions import CredentialsError
except ImportError:
    print("Установите зависимость: pip install pykeepass")
    sys.exit(1)

from ui.colors import init_colors
from ui.widgets import draw_box, safe_addstr
from ui.colors import C_WARN, C_DIM
from screens.file_picker import screen_pick_file
from screens.auth import screen_enter_password
from screens.main_menu import screen_main_menu


def main(stdscr) -> None:
    curses.curs_set(0)
    init_colors()
    stdscr.keypad(True)

    # 1. Выбор файла
    db_path = screen_pick_file(stdscr)
    if not db_path:
        return

    # 2. Ввод пароля (с возможностью повтора)
    kp = _open_database(stdscr, db_path)
    if kp is None:
        return

    # 3. Главное меню
    screen_main_menu(stdscr, kp, Path(db_path).name)


def _open_database(stdscr, db_path):
    """Цикл ввода пароля с повтором при ошибке.

    Returns:
        PyKeePass instance, или None если пользователь вышел.
    """
    while True:
        result = screen_enter_password(stdscr, db_path)

        if result == (None, None):
            return None

        password, keyfile = result

        _show_loading(stdscr, "Открываю базу...")

        try:
            return PyKeePass(
                db_path,
                password=password or None,
                keyfile=keyfile or None,
            )

        except CredentialsError:
            _show_message(
                stdscr,
                "Ошибка",
                "⚠  Неверный пароль или ключевой файл",
                "Нажмите любую клавишу...",
            )
            # Продолжаем цикл — пользователь повторит ввод

        except Exception as exc:
            _show_message(
                stdscr,
                "Ошибка",
                str(exc),
                "Нажмите любую клавишу...",
                fatal=True,
            )
            return None


def _show_loading(stdscr, text: str) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    safe_addstr(stdscr, h // 2, w // 2 - 10, text,
                curses.color_pair(C_WARN) | curses.A_BOLD)
    stdscr.refresh()


def _show_message(
    stdscr,
    title: str,
    message: str,
    hint: str,
    fatal: bool = False,
) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, title)
    safe_addstr(stdscr, h // 2 - 1, w // 2 - len(message) // 2, message,
                curses.color_pair(C_WARN) | curses.A_BOLD)
    safe_addstr(stdscr, h // 2 + 1, w // 2 - len(hint) // 2, hint,
                curses.color_pair(C_DIM))
    stdscr.refresh()
    stdscr.getch()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
