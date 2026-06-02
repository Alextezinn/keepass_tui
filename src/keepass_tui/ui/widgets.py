"""Низкоуровневые примитивы отрисовки: рамки, строки, подсказки, диалоги."""

import curses

from .colors import (
    C_HEADER,
    C_TITLE,
    C_DIM,
    C_VALUE,
    C_WARN,
    C_BORDER,
)


# ─── Утилиты ──────────────────────────────────────────────────────────────────


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def trunc(s: str | None, n: int) -> str:
    s = s or ""
    return s[: n - 1] + "…" if len(s) > n else s


# ─── Примитивы отрисовки ──────────────────────────────────────────────────────


def safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        max_len = w - x - 1
        if max_len <= 0:
            return
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def draw_box(win, y: int, x: int, h: int, w: int, title: str = "") -> None:
    try:
        win.attron(curses.color_pair(C_BORDER))
        win.addch(y, x, curses.ACS_ULCORNER)
        win.addch(y, x + w - 1, curses.ACS_URCORNER)
        win.addch(y + h - 1, x, curses.ACS_LLCORNER)
        win.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER)

        for i in range(1, w - 1):
            win.addch(y, x + i, curses.ACS_HLINE)
            win.addch(y + h - 1, x + i, curses.ACS_HLINE)

        for i in range(1, h - 1):
            win.addch(y + i, x, curses.ACS_VLINE)
            win.addch(y + i, x + w - 1, curses.ACS_VLINE)

        if title:
            label = f" {title} "
            win.addstr(y, x + (w - len(label)) // 2, label, curses.color_pair(C_HEADER))
        win.attroff(curses.color_pair(C_BORDER))
    except curses.error:
        pass


def render_hint(stdscr, y: int, w: int, items: list[tuple[str, str]]) -> None:
    """Адаптивная multiline hint-строка.

    items: [("Enter", "открыть"), ("q", "выход"), ...]
    """
    parts = [f"{k} - {v}" for k, v in items]
    one_line = "   ".join(parts)

    if len(one_line) <= w - 6:
        safe_addstr(stdscr, y, 3, one_line, curses.color_pair(C_WARN))
        return

    two_per_line = ["   ".join(parts[i : i + 2]) for i in range(0, len(parts), 2)]
    if max(len(x) for x in two_per_line) <= w - 6:
        for i, line in enumerate(two_per_line):
            safe_addstr(stdscr, y + i, 3, line, curses.color_pair(C_WARN))
        return

    for i, line in enumerate(parts):
        safe_addstr(stdscr, y + i, 3, trunc(line, w - 6), curses.color_pair(C_WARN))


# ─── Диалоги ──────────────────────────────────────────────────────────────────


def show_error(stdscr, text: str) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Ошибка")
    safe_addstr(stdscr, h // 2, 3, trunc(text, w - 6), curses.color_pair(C_WARN))
    safe_addstr(stdscr, h - 3, 3, "Нажмите любую клавишу...", curses.color_pair(C_DIM))
    stdscr.refresh()
    stdscr.getch()


def confirm_delete(stdscr, text: str) -> bool:
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Подтверждение удаления")
        safe_addstr(
            stdscr,
            h // 2 - 1,
            3,
            trunc(text, w - 6),
            curses.color_pair(C_WARN) | curses.A_BOLD,
        )
        safe_addstr(
            stdscr, h // 2 + 1, 3, "y - удалить\t\tn - отмена", curses.color_pair(C_DIM)
        )
        stdscr.refresh()
        key = stdscr.getch()

        if key in (ord("y"), ord("Y")):
            return True

        if key in (ord("n"), ord("N"), 27):
            return False


def input_box(stdscr, title: str, prompt: str, initial: str = "") -> str | None:
    """Однострочный текстовый ввод. Возвращает строку или None (Esc)."""
    text = initial

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, title)
        safe_addstr(stdscr, 3, 3, prompt, curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(stdscr, 5, 3, f"> {text}_", curses.color_pair(C_VALUE))
        safe_addstr(
            stdscr,
            h - 3,
            3,
            "Enter - подтвердить\t\tEsc - отмена",
            curses.color_pair(C_WARN),
        )
        stdscr.refresh()

        key = stdscr.getch()

        if key == 27:
            return None

        elif key in (curses.KEY_ENTER, 10, 13):
            value = text.strip()

            if value:
                return value

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            text = text[:-1]

        elif 32 <= key < 256:
            text += chr(key)
