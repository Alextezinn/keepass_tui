"""Константы цветов и инициализация curses-палитры."""

import curses

C_HEADER = 1
C_SELECTED = 2
C_TITLE = 3
C_DIM = 4
C_VALUE = 5
C_WARN = 6
C_GOOD = 7
C_BORDER = 8


def init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_SELECTED, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(C_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(C_DIM, curses.COLOR_WHITE, -1)
    curses.init_pair(C_VALUE, curses.COLOR_GREEN, -1)
    curses.init_pair(C_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_GOOD, curses.COLOR_GREEN, -1)
    curses.init_pair(C_BORDER, curses.COLOR_CYAN, -1)
