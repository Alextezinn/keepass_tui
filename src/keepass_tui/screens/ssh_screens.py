"""Экраны для смены паролей через SSH (одиночная и массовая)."""

import curses

from keepass_tui.ui.widgets import draw_box, safe_addstr, render_hint, trunc, show_error
from keepass_tui.ui.colors import C_TITLE, C_DIM, C_VALUE, C_WARN, C_GOOD
from keepass_tui.ui.clipboard import copy_to_clipboard
from keepass_tui.ssh.passwords import (
    ssh_change_password,
    cleanup_tmp_against_keepass,
    recover_from_tmp,
)


def screen_change_password(stdscr, entry, kp, db_path) -> None:
    """Экран подтверждения и выполнения смены пароля на сервере по SSH."""
    ip = _extract_ip(entry.url or "")
    username = entry.username or ""
    current_password = entry.password or ""

    if not ip:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        draw_box(stdscr, 0, 0, h, w, "Смена пароля")
        safe_addstr(
            stdscr,
            h // 2 - 1,
            3,
            "⚠  В записи не заполнено поле URL (нужен IP/hostname сервера)",
            curses.color_pair(C_WARN) | curses.A_BOLD,
        )
        safe_addstr(
            stdscr, h // 2 + 1, 3, "Нажмите любую клавишу...", curses.color_pair(C_DIM)
        )
        stdscr.refresh()
        stdscr.getch()
        return

    if not _confirm_change(stdscr, ip, username, current_password):
        return

    # Прогресс
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Смена пароля")
    safe_addstr(
        stdscr,
        h // 2,
        w // 2 - 18,
        f"Подключаюсь к {trunc(ip, 30)}...",
        curses.color_pair(C_WARN) | curses.A_BOLD,
    )
    stdscr.refresh()

    new_password, error = ssh_change_password(ip, username, current_password)
    _show_change_result(stdscr, entry, kp, ip, new_password, error)


def mass_change_passwords(stdscr, kp, entries, db_path) -> None:
    """Массовая смена паролей для всех записей с заполненным URL."""
    to_process = [e for e in entries if (e.url or "").strip()]

    if not to_process:
        show_error(stdscr, "Не найдено записей с заполненным URL")
        return

    if not _confirm_mass_change(stdscr, len(to_process)):
        return

    success, failed, results = 0, 0, []

    for i, entry in enumerate(to_process):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_box(stdscr, 0, 0, h, w, "Массовая смена паролей")
        safe_addstr(
            stdscr,
            h // 2 - 1,
            3,
            f"Обрабатывается ({i + 1}/{len(to_process)}): "
            f"{trunc(entry.title or '', 50)}",
            curses.color_pair(C_WARN),
        )
        stdscr.refresh()

        ip = _extract_ip(entry.url or "")
        new_pw, error = ssh_change_password(
            ip, entry.username or "", entry.password or ""
        )
        if error:
            failed += 1
            results.append(f"✗ {entry.title}: {error[:80]}")
        else:
            success += 1
            entry.password = new_pw
            results.append(f"✓ {entry.title}")

    try:
        kp.save()
        cleanup_tmp_against_keepass(kp)
    except Exception as exc:
        show_error(stdscr, f"Ошибка сохранения базы: {exc}")

    _show_mass_result(stdscr, success, failed, results)


# ─── Вспомогательные функции ─────────────────────────────────────────────────


def _extract_ip(raw_url: str) -> str:
    ip = raw_url.strip()
    for prefix in ("ssh://", "http://", "https://", "ftp://"):
        if ip.lower().startswith(prefix):
            ip = ip[len(prefix) :]
            break
    return ip.rstrip("/").split("/")[0].split(":")[0]


def _confirm_change(stdscr, ip, username, current_password) -> bool:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Смена пароля — подтверждение")

    safe_addstr(
        stdscr,
        2,
        3,
        "Будет выполнена смена пароля на сервере:",
        curses.color_pair(C_TITLE) | curses.A_BOLD,
    )
    safe_addstr(stdscr, 4, 3, "Сервер:", curses.color_pair(C_DIM))
    safe_addstr(stdscr, 4, 16, trunc(ip, w - 20), curses.color_pair(C_VALUE))
    safe_addstr(stdscr, 6, 3, "Пользователь:", curses.color_pair(C_DIM))
    safe_addstr(stdscr, 6, 16, trunc(username, w - 20), curses.color_pair(C_VALUE))
    safe_addstr(stdscr, 8, 3, "Текущий пароль:", curses.color_pair(C_DIM))
    safe_addstr(
        stdscr, 8, 20, "●" * min(len(current_password), 20), curses.color_pair(C_VALUE)
    )
    safe_addstr(
        stdscr,
        10,
        3,
        "Новый пароль будет сгенерирован и сохранён в KeePass автоматически.",
        curses.color_pair(C_DIM),
    )
    render_hint(stdscr, h - 3, w, [("Enter", "подтвердить и сменить"), ("q", "отмена")])
    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if key in (ord("q"), 27):
            return False
        if key in (curses.KEY_ENTER, 10, 13):
            return True


def _confirm_mass_change(stdscr, count: int) -> bool:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Массовая смена паролей")
    safe_addstr(
        stdscr,
        h // 2 - 2,
        3,
        f"Будет выполнена смена пароля для {count} записей.",
        curses.color_pair(C_WARN) | curses.A_BOLD,
    )
    safe_addstr(
        stdscr,
        h // 2,
        3,
        "Это необратимая операция. Продолжить?",
        curses.color_pair(C_DIM),
    )
    render_hint(stdscr, h - 3, w, [("Enter", "продолжить"), ("q", "отмена")])
    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if key in (ord("q"), 27):
            return False
        if key in (curses.KEY_ENTER, 10, 13):
            return True


def _show_change_result(stdscr, entry, kp, ip, new_password, error) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Смена пароля — результат")

    if error:
        safe_addstr(
            stdscr,
            h // 2 - 2,
            3,
            "⚠  Ошибка при смене пароля:",
            curses.color_pair(C_WARN) | curses.A_BOLD,
        )
        safe_addstr(stdscr, h // 2, 3, trunc(error, w - 6), curses.color_pair(C_WARN))
        safe_addstr(
            stdscr,
            h // 2 + 2,
            3,
            "Пароль в KeePass НЕ изменён.",
            curses.color_pair(C_DIM),
        )
    else:
        entry.password = new_password
        try:
            kp.save()
            save_ok = True
            save_err = ""
        except Exception as exc:
            save_ok = False
            save_err = str(exc)

        if save_ok:
            safe_addstr(
                stdscr,
                h // 2 - 4,
                3,
                "✓  Пароль успешно сменён на сервере!",
                curses.color_pair(C_GOOD) | curses.A_BOLD,
            )
            safe_addstr(
                stdscr, h // 2 - 2, 3, "Новый пароль:", curses.color_pair(C_DIM)
            )
            safe_addstr(
                stdscr,
                h // 2 - 2,
                17,
                trunc(new_password, w - 20),
                curses.color_pair(C_VALUE) | curses.A_BOLD,
            )
            save_ok_msg = "✓  База KeePass сохранена."
            cleanup_tmp_against_keepass(kp)
            safe_addstr(stdscr, h // 2, 3, save_ok_msg, curses.color_pair(C_GOOD))
            copy_to_clipboard(new_password)
            safe_addstr(
                stdscr,
                h // 2 + 1,
                3,
                "  (новый пароль скопирован в буфер обмена)",
                curses.color_pair(C_DIM),
            )
        else:
            safe_addstr(
                stdscr,
                h // 2 - 2,
                3,
                "✓  Пароль сменён на сервере, но не сохранён в KeePass!",
                curses.color_pair(C_WARN) | curses.A_BOLD,
            )
            safe_addstr(
                stdscr,
                h // 2,
                3,
                f"Ошибка сохранения: {trunc(save_err, w - 22)}",
                curses.color_pair(C_WARN),
            )
            safe_addstr(
                stdscr,
                h // 2 + 2,
                3,
                f"Новый пароль: {new_password}",
                curses.color_pair(C_VALUE),
            )

    safe_addstr(stdscr, h - 3, 3, "Нажмите любую клавишу...", curses.color_pair(C_DIM))
    stdscr.refresh()
    stdscr.getch()


def _show_mass_result(stdscr, success: int, failed: int, results: list) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Результат массовой смены паролей")

    color = C_GOOD if failed == 0 else C_WARN
    safe_addstr(
        stdscr, 2, 3, f"Успешно: {success} | Ошибок: {failed}", curses.color_pair(color)
    )

    for i, line in enumerate(results[: h - 8]):
        c = C_GOOD if line.startswith("✓") else C_WARN
        safe_addstr(stdscr, 4 + i, 3, trunc(line, w - 6), curses.color_pair(c))

    safe_addstr(stdscr, h - 3, 3, "Нажмите любую клавишу...", curses.color_pair(C_DIM))
    stdscr.refresh()
    stdscr.getch()


def screen_recover_from_tmp(stdscr, kp) -> None:
    """Экран восстановления паролей из страховочного файла.

    Вызывается автоматически при старте если tmp-файл существует.
    """
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_box(stdscr, 0, 0, h, w, "Обнаружен страховочный файл паролей")

    safe_addstr(
        stdscr,
        2,
        3,
        "При предыдущем запуске пароли могли не сохраниться в KeePass.",
        curses.color_pair(C_WARN) | curses.A_BOLD,
    )
    safe_addstr(
        stdscr,
        3,
        3,
        "Выполняется проверка и восстановление...",
        curses.color_pair(C_DIM),
    )
    stdscr.refresh()

    results = recover_from_tmp(kp)

    if not results:
        return

    stdscr.erase()
    draw_box(stdscr, 0, 0, h, w, "Результат восстановления")

    STATUS_COLOR = {
        "synced": C_DIM,
        "recovered": C_GOOD,
        "failed": C_WARN,
    }
    STATUS_LABEL = {
        "synced": "=",
        "recovered": "✓",
        "failed": "✗",
    }

    for i, res in enumerate(results[: h - 8]):
        color = STATUS_COLOR.get(res["status"], C_DIM)
        mark = STATUS_LABEL.get(res["status"], "?")
        line = f"{mark} {res['ip']} / {res['username']} — {res['detail']}"
        safe_addstr(stdscr, 3 + i, 3, trunc(line, w - 6), curses.color_pair(color))

    safe_addstr(stdscr, h - 3, 3, "Нажмите любую клавишу...", curses.color_pair(C_DIM))
    stdscr.refresh()
    stdscr.getch()
