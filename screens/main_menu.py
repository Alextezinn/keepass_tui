"""Главное меню приложения."""

import curses

from ui.widgets import draw_box, safe_addstr, trunc
from ui.colors import C_TITLE, C_DIM, C_SELECTED, C_WARN
from .entry_list import screen_entries, screen_entries_search
from .group_browser import screen_groups


def screen_main_menu(stdscr, kp, db_name: str) -> None:
    items = [
        ("📋  Все записи", "all"),
        ("🔍  Поиск",      "search"),
        ("📁  По группам", "groups"),
        ("❌  Выход",      "quit"),
    ]
    cursor = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Главное меню")

        safe_addstr(
            stdscr, 2, 3,
            f"База: {trunc(db_name, w - 10)}  •  Записей: {len(kp.entries)}",
            curses.color_pair(C_TITLE) | curses.A_BOLD,
        )

        start_y = (h - len(items) * 2) // 2

        for i, (label, _) in enumerate(items):
            row = start_y + i * 2

            if i == cursor:
                safe_addstr(stdscr, row, w // 2 - 15, f"▶  {label}",
                            curses.color_pair(C_SELECTED) | curses.A_BOLD)
            else:
                safe_addstr(stdscr, row, w // 2 - 13, label,
                            curses.color_pair(C_DIM))

        safe_addstr(stdscr, h - 3, 3, "Enter - выбрать\t\tq - выход",
                    curses.color_pair(C_WARN))
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            cursor = (cursor - 1) % len(items)

        elif key == curses.KEY_DOWN:
            cursor = (cursor + 1) % len(items)

        elif key in (curses.KEY_ENTER, 10, 13, ord(' ')):
            action = items[cursor][1]

            if action == "quit":
                return

            _reload_safe(kp)

            if action == "all":
                screen_entries(stdscr, kp, kp.entries, "Все записи")

            elif action == "search":
                screen_entries_search(stdscr, kp)

            elif action == "groups":
                screen_groups(stdscr, kp)

        elif key == ord('q'):
            return


def _reload_safe(kp) -> None:
    try:
        kp.reload()
    except Exception:
        pass
