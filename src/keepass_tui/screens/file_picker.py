"""Экран выбора .kdbx файла."""

import glob
import os
import curses
from pathlib import Path
from typing import Optional

from keepass_tui.ui.widgets import (
    clamp, trunc, draw_box, safe_addstr, render_hint,
)
from keepass_tui.ui.colors import C_TITLE, C_SELECTED, C_DIM, C_VALUE, C_WARN


def screen_pick_file(stdscr) -> Optional[str]:
    """Список найденных баз или ручной ввод пути.

    Returns:
        Путь к .kdbx файлу, или None если пользователь вышел.
    """
    files = sorted(
        glob.glob(os.path.expanduser("~/**/*.kdbx"), recursive=True) +
        glob.glob("**/*.kdbx", recursive=True)
    )
    files = list(dict.fromkeys(files))  # дедупликация

    cursor = 0
    offset = 0
    input_path = ""
    mode = "list" if files else "input"

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "KeePassXC Reader")

        if mode == "list":
            _draw_file_list(stdscr, h, w, files, cursor, offset)
            render_hint(stdscr, h - 3, w, [
                ("Enter", "выбрать"),
                ("m", "вручную"),
                ("q", "выход"),
            ])

        else:
            _draw_manual_input(stdscr, h, w, input_path)

        stdscr.refresh()
        key = stdscr.getch()

        if mode == "list":
            list_h = h - 8
            cursor = clamp(cursor, 0, max(0, len(files) - 1))

            if key == curses.KEY_UP:
                cursor = clamp(cursor - 1, 0, len(files) - 1)

            elif key == curses.KEY_DOWN:
                cursor = clamp(cursor + 1, 0, len(files) - 1)

            elif key in (curses.KEY_ENTER, 10, 13):
                if files:
                    return files[cursor]

            elif key == ord('m'):
                mode = "input"
                input_path = ""

            elif key in (ord('q'), 27):
                return None

        else:
            if key == 27:
                mode = "list" if files else None

                if mode is None:
                    return None

            elif key in (curses.KEY_ENTER, 10, 13):
                p = input_path.strip()

                if p and Path(p).exists():
                    return p

                safe_addstr(stdscr, 6, 3, "Файл не найден!",
                            curses.color_pair(C_WARN))
                stdscr.refresh()
                curses.napms(1200)

            elif key in (curses.KEY_BACKSPACE, 127, 8):
                input_path = input_path[:-1]

            elif 32 <= key < 256:
                input_path += chr(key)


def _draw_file_list(stdscr, h, w, files, cursor, offset):
    safe_addstr(stdscr, 2, 3, "Найденные базы данных (.kdbx):",
                curses.color_pair(C_TITLE) | curses.A_BOLD)

    list_h = h - 8

    if cursor < offset:
        offset = cursor
    elif cursor >= offset + list_h:
        offset = cursor - list_h + 1

    for i, path in enumerate(files[offset:offset + list_h]):
        row = 4 + i
        idx = offset + i
        filename = os.path.basename(path)
        parent   = os.path.dirname(path)
        label    = trunc(f"{filename}   [{parent}]", w - 10)

        if idx == cursor:
            safe_addstr(stdscr, row, 2, f"▶ {label}", curses.color_pair(C_SELECTED))
        else:
            safe_addstr(stdscr, row, 4, label, curses.color_pair(C_DIM))

    counter = f"{cursor + 1}/{len(files)}"
    safe_addstr(stdscr, h - 4, w - len(counter) - 3, counter,
                curses.color_pair(C_VALUE))


def _draw_manual_input(stdscr, h, w, input_path):
    safe_addstr(stdscr, 2, 3, "Введите путь к .kdbx:",
                curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(stdscr, 4, 3, f"> {input_path}_", curses.color_pair(C_VALUE))
    safe_addstr(stdscr, h - 3, 3, "Enter - открыть\t\tEsc - назад",
                curses.color_pair(C_WARN))
