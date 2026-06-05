"""Экран навигации по группам (файловый менеджер)."""

import curses


from keepass_tui.ui.widgets import (
    clamp,
    trunc,
    draw_box,
    safe_addstr,
    render_hint,
    show_error,
    input_box,
    confirm_delete,
)
from keepass_tui.ui.colors import C_SELECTED, C_TITLE, C_DIM, C_VALUE
from keepass_tui.keepass.db import (
    group_path,
    create_group as db_create_group,
    create_entry as db_create_entry,
    rename_group,
    update_entry,
    delete_group as db_delete_group,
    delete_entry as db_delete_entry,
)
from .entry_detail import screen_entry_detail


def screen_groups(stdscr, kp, db_path=None, cfg: dict | None = None) -> None:
    """Файловый менеджер по группам KeePass."""
    stack: list = []
    current_group = kp.root_group
    cursor = offset = 0

    while True:
        # После любого kp.reload() внутри экшенов current_group — устаревший объект.
        # Обновляем его по UUID в начале каждой итерации.
        current_group = (
            kp.find_groups(uuid=current_group.uuid, first=True) or kp.root_group
        )

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "По группам")

        items = _build_items(current_group)
        list_h = h - 7
        cursor = clamp(cursor, 0, max(0, len(items) - 1))

        if cursor < offset:
            offset = cursor
        elif cursor >= offset + list_h:
            offset = cursor - list_h + 1

        breadcrumb = group_path(current_group) or "/"
        safe_addstr(
            stdscr,
            2,
            3,
            trunc(f"📂 {breadcrumb}", w - 6),
            curses.color_pair(C_TITLE) | curses.A_BOLD,
        )

        if not items:
            safe_addstr(stdscr, 5, 5, "(пусто)", curses.color_pair(C_DIM))
        else:
            _draw_item_rows(stdscr, items, cursor, offset, list_h, w)

        counter = f"{cursor + 1}/{len(items)}" if items else "0/0"
        safe_addstr(
            stdscr, h - 4, w - len(counter) - 3, counter, curses.color_pair(C_VALUE)
        )

        render_hint(
            stdscr,
            h - 3,
            w,
            [
                ("Enter", "открыть"),
                ("a", "создать запись"),
                ("f", "создать папку"),
                ("e", "редактировать"),
                ("d", "удалить"),
                ("q", "назад" if stack else "выход"),
            ],
        )
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            cursor = clamp(cursor - 1, 0, max(0, len(items) - 1))

        elif key == curses.KEY_DOWN:
            cursor = clamp(cursor + 1, 0, max(0, len(items) - 1))

        elif key in (curses.KEY_ENTER, 10, 13):
            if not items:
                continue
            kind, obj = items[cursor]
            if kind == "group":
                stack, current_group, cursor, offset = _enter_group(
                    kp, stack, current_group, obj, cursor, offset
                )
            else:
                screen_entry_detail(stdscr, obj, kp=kp, db_path=db_path)

        elif key == ord("a"):
            if _action_create_entry(stdscr, kp, current_group, cfg):
                cursor = len(items)

        elif key == ord("f"):
            if _action_create_group(stdscr, kp, current_group):
                cursor = len(items)

        elif key == ord("e"):
            if items:
                kind, obj = items[cursor]
                if kind == "group":
                    _action_edit_group(stdscr, kp, obj)
                else:
                    _action_edit_entry(stdscr, kp, obj, cfg)

        elif key == ord("d"):
            if items:
                kind, obj = items[cursor]
                if _action_delete(stdscr, kp, kind, obj):
                    cursor = clamp(cursor, 0, max(0, len(items) - 2))

        elif key in (27, ord("q")):
            if stack:
                stack, current_group, cursor, offset = _go_back(kp, stack)
            else:
                try:
                    kp.reload()
                except Exception:
                    pass
                return


# ─── Действия (CRUD) ─────────────────────────────────────────────────────────


def _action_create_entry(stdscr, kp, group, cfg: dict | None = None) -> bool:
    title = input_box(stdscr, "Новая запись", "Название:")
    if not title:
        return False

    username = input_box(stdscr, "Новая запись", "Логин:") or ""
    password = (
        input_box(stdscr, "Новая запись", "Пароль:", is_password=True, cfg=cfg) or ""
    )
    url = input_box(stdscr, "Новая запись", "URL:") or ""

    err = db_create_entry(kp, group, title, username, password, url)

    if err:
        show_error(stdscr, err)
        return False

    return True


def _action_create_group(stdscr, kp, parent_group) -> bool:
    name = input_box(stdscr, "Новая папка", "Введите имя папки:")

    if not name:
        return False

    err = db_create_group(kp, parent_group, name)

    if err:
        show_error(stdscr, err)
        return False

    return True


def _action_edit_group(stdscr, kp, group) -> bool:
    old_name = group.name or ""
    group_uuid = group.uuid

    new_name = input_box(stdscr, "Редактирование папки", "Новое имя:", old_name)
    if new_name is None:
        return False

    try:
        kp.reload()
    except Exception as exc:
        show_error(stdscr, f"Ошибка перезагрузки базы: {exc}")
        return False

    live_group = kp.find_groups(uuid=group_uuid, first=True)

    if live_group is None:
        show_error(stdscr, "Группа не найдена в базе")
        return False

    err = rename_group(kp, live_group, new_name)

    if err:
        show_error(stdscr, err)
        return False
    return True


def _action_edit_entry(stdscr, kp, entry, cfg: dict | None = None) -> bool:
    # Собираем новые значения ДО reload — используем entry только как источник
    # текущих значений для подстановки в input_box
    old_title = entry.title or ""
    old_username = entry.username or ""
    old_password = entry.password or ""
    old_url = entry.url or ""
    entry_uuid = entry.uuid

    title = input_box(stdscr, "Редактирование записи", "Название:", old_title)
    if title is None:
        return False

    username = input_box(stdscr, "Редактирование записи", "Логин:", old_username)

    if username is None:
        return False

    password = input_box(
        stdscr,
        "Редактирование записи",
        "Пароль:",
        old_password,
        is_password=True,
        cfg=cfg,
    )

    if password is None:
        return False

    url = input_box(stdscr, "Редактирование записи", "URL:", old_url)

    if url is None:
        return False

    # Перезагружаем базу и ищем живой объект по UUID
    try:
        kp.reload()
    except Exception as exc:
        show_error(stdscr, f"Ошибка перезагрузки базы: {exc}")
        return False

    live_entry = kp.find_entries(uuid=entry_uuid, first=True)

    if live_entry is None:
        show_error(stdscr, "Запись не найдена в базе (возможно, была удалена)")
        return False

    err = update_entry(kp, live_entry, title, username, password, url)

    if err:
        show_error(stdscr, err)
        return False

    return True


def _action_delete(stdscr, kp, kind: str, obj) -> bool:
    if kind == "group":
        name = obj.name or "(без имени)"
        has_content = bool(obj.subgroups or obj.entries)

        if has_content:
            if not confirm_delete(
                stdscr, f"Удалить папку '{name}' со всем содержимым?"
            ):
                return False

        err = db_delete_group(kp, obj)
    else:
        title = obj.title or "(без названия)"

        if not confirm_delete(stdscr, f"Удалить запись '{title}'?"):
            return False

        err = db_delete_entry(kp, obj)

    if err:
        show_error(stdscr, err)
        return False

    return True


# ─── Навигация ───────────────────────────────────────────────────────────────


def _build_items(group) -> list:
    subgroups = sorted(group.subgroups, key=lambda g: (g.name or "").lower())
    entries = sorted(group.entries, key=lambda e: (e.title or "").lower())
    return [("group", g) for g in subgroups] + [("entry", e) for e in entries]


def _draw_item_rows(stdscr, items, cursor, offset, list_h, w) -> None:
    for i, (kind, obj) in enumerate(items[offset : offset + list_h]):
        row = 3 + i
        idx = offset + i

        if kind == "group":
            label = trunc(f"📁 {obj.name or '(без имени)'}", w - 8)
            if idx == cursor:
                safe_addstr(
                    stdscr,
                    row,
                    2,
                    f"▶ {label}",
                    curses.color_pair(C_SELECTED) | curses.A_BOLD,
                )
            else:
                safe_addstr(stdscr, row, 4, label, curses.color_pair(C_TITLE))
        else:
            label = trunc(obj.title or "(без названия)", w // 2 - 4)
            login = trunc(obj.username or "", w // 2 - 4)

            if idx == cursor:
                safe_addstr(stdscr, row, 2, f"▶ {label}", curses.color_pair(C_SELECTED))
                safe_addstr(stdscr, row, w // 2, login, curses.color_pair(C_SELECTED))
            else:
                safe_addstr(stdscr, row, 6, label, curses.color_pair(C_DIM))
                safe_addstr(stdscr, row, w // 2, login, curses.color_pair(C_VALUE))


def _enter_group(kp, stack, current_group, obj, cursor, offset):
    stack.append((current_group, cursor, offset))
    target_uuid = obj.uuid

    try:
        kp.reload()
    except Exception:
        pass

    stack = [(_refresh_group_in_stack(kp, g), c, o) for g, c, o in stack]
    new_group = kp.find_groups(uuid=target_uuid, first=True) or kp.root_group
    return stack, new_group, 0, 0


def _go_back(kp, stack):
    current_group, cursor, offset = stack.pop()
    parent_uuid = current_group.uuid

    try:
        kp.reload()
    except Exception:
        pass

    stack = [(_refresh_group_in_stack(kp, g), c, o) for g, c, o in stack]
    current_group = kp.find_groups(uuid=parent_uuid, first=True) or kp.root_group
    return stack, current_group, cursor, offset


def _refresh_group_in_stack(kp, group):
    fresh = kp.find_groups(uuid=group.uuid, first=True)
    return fresh if fresh is not None else kp.root_group
