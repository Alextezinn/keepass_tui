"""Экраны: плоский список записей и быстрый поиск."""

import curses

from keepass_tui.ui.widgets import (
    clamp,
    trunc,
    draw_box,
    safe_addstr,
    render_hint,
)
from keepass_tui.ui.colors import C_HEADER, C_SELECTED, C_DIM, C_VALUE, C_WARN
from .entry_detail import screen_entry_detail
from .pwned_screen import screen_check_single, screen_check_all
from .ssh_screens import (
    mass_change_passwords,
    screen_change_password,
    screen_recover_from_tmp,
)


def screen_entries(
    stdscr, kp, entries, title: str = "Все записи", db_path=None
) -> None:
    """Плоский список записей с фильтрацией и действиями."""
    cursor = 0
    offset = 0
    search = ""
    searching = False

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        list_h = h - 6

        q = search.lower()
        filtered = _filter_entries(entries, q)
        cursor = clamp(cursor, 0, max(0, len(filtered) - 1))

        if cursor < offset:
            offset = cursor

        elif cursor >= offset + list_h:
            offset = cursor - list_h + 1

        draw_box(stdscr, 0, 0, h, w, title)
        _draw_columns_header(stdscr, w)
        _draw_entry_rows(stdscr, filtered, cursor, offset, list_h, w)

        counter = f"{cursor + 1}/{len(filtered)}" if filtered else "0/0"
        safe_addstr(
            stdscr, h - 4, w - len(counter) - 3, counter, curses.color_pair(C_VALUE)
        )

        if searching:
            safe_addstr(
                stdscr,
                h - 3,
                3,
                f"Поиск: {search}_  (Esc — сбросить)",
                curses.color_pair(C_WARN),
            )
        else:
            render_hint(
                stdscr,
                h - 3,
                w,
                [
                    ("Enter", "просмотр"),
                    ("/", "поиск"),
                    ("r", "сменить пароль"),
                    ("R", "массовая смена"),
                    ("b", "проверка утечек"),
                    ("B", "массовая проверка утечек"),
                    ("q", "назад"),
                ],
            )

        stdscr.refresh()
        key = stdscr.getch()

        if searching:
            searching, search, cursor = _handle_search_key(
                key, searching, search, cursor
            )

        elif key == ord("/"):
            searching = True
            cursor = 0

        else:
            result = _handle_list_key(
                key, stdscr, kp, filtered, cursor, offset, list_h, db_path
            )

            if result == "quit":
                return
            if isinstance(result, tuple):
                cursor, offset = result


def screen_entries_search(stdscr, kp) -> None:
    """Быстрый поиск с немедленным показом результатов."""
    search = ""

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Поиск")

        safe_addstr(
            stdscr,
            2,
            3,
            f"Запрос: {search}_",
            curses.color_pair(C_VALUE) | curses.A_BOLD,
        )

        q = search.lower()
        filtered = _filter_entries(kp.entries, q) if q else []

        safe_addstr(
            stdscr,
            3,
            3,
            f"Найдено: {len(filtered)}" if q else "Начните вводить...",
            curses.color_pair(C_DIM),
        )

        for i, e in enumerate(filtered[: h - 8]):
            safe_addstr(
                stdscr,
                5 + i,
                5,
                f"{trunc(e.title or '', 30):<32} {trunc(e.username or '', 25)}",
                curses.color_pair(C_DIM),
            )

        render_hint(
            stdscr,
            h - 3,
            w,
            [
                ("Enter", "открыть"),
                ("Esc", "назад"),
            ],
        )
        stdscr.refresh()
        key = stdscr.getch()

        if key == 27:
            return

        elif key in (curses.KEY_ENTER, 10, 13):
            if filtered:
                screen_entries(stdscr, kp, filtered, f'Поиск: "{search}"')

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            search = search[:-1]

        elif 32 <= key < 256:
            search += chr(key)


# ─── Вспомогательные функции ─────────────────────────────────────────────────


def _filter_entries(entries, q: str) -> list:
    if not q:
        return entries
    return [
        e
        for e in entries
        if q in (e.title or "").lower()
        or q in (e.username or "").lower()
        or q in (e.url or "").lower()
    ]


def _draw_columns_header(stdscr, w: int) -> None:
    col_t = 3
    col_u = w // 2
    safe_addstr(
        stdscr,
        2,
        col_t,
        trunc("НАЗВАНИЕ", col_u - col_t - 2),
        curses.color_pair(C_HEADER) | curses.A_BOLD,
    )
    safe_addstr(
        stdscr,
        2,
        col_u,
        trunc("ЛОГИН", w - col_u - 4),
        curses.color_pair(C_HEADER) | curses.A_BOLD,
    )


def _draw_entry_rows(stdscr, filtered, cursor, offset, list_h, w) -> None:
    col_t = 3
    col_u = w // 2

    for i, entry in enumerate(filtered[offset : offset + list_h]):
        row = 3 + i
        idx = offset + i

        t = trunc(entry.title or "(без названия)", col_u - col_t - 2)
        u = trunc(entry.username or "", w - col_u - 4)

        if idx == cursor:
            safe_addstr(stdscr, row, col_t, f"▶ {t}", curses.color_pair(C_SELECTED))
            safe_addstr(stdscr, row, col_u, u, curses.color_pair(C_SELECTED))
        else:
            safe_addstr(stdscr, row, col_t + 2, t, curses.color_pair(C_DIM))
            safe_addstr(stdscr, row, col_u, u, curses.color_pair(C_VALUE))


def _handle_search_key(key, searching, search, cursor):
    if key == 27:
        return False, "", 0

    elif key in (curses.KEY_ENTER, 10, 13):
        return False, search, cursor

    elif key in (curses.KEY_BACKSPACE, 127, 8):
        return True, search[:-1], 0

    elif 32 <= key < 256:
        return True, search + chr(key), 0

    return searching, search, cursor


def _handle_list_key(key, stdscr, kp, filtered, cursor, offset, list_h, db_path):
    if key == curses.KEY_UP:
        return clamp(cursor - 1, 0, max(0, len(filtered) - 1)), offset

    elif key == curses.KEY_DOWN:
        return clamp(cursor + 1, 0, max(0, len(filtered) - 1)), offset

    elif key in (curses.KEY_ENTER, 10, 13):
        if filtered:
            try:
                kp.reload()
            except Exception:
                pass

            result = screen_entry_detail(
                stdscr, filtered[cursor], kp=kp, db_path=db_path
            )
            if result == "quit":
                return "quit"

    elif key == ord("r"):
        if filtered:
            screen_change_password(stdscr, filtered[cursor], kp, db_path)

    elif key == ord("R"):
        mass_change_passwords(stdscr, kp, filtered, db_path)
        screen_recover_from_tmp(stdscr, kp)

    elif key == ord("b"):
        if filtered:
            screen_check_single(stdscr, filtered[cursor])

    elif key == ord("B"):
        screen_check_all(stdscr, filtered)

    elif key in (ord("q"), 27):
        return "quit"

    return cursor, offset
