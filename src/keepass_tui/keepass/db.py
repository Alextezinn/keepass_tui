"""Операции с базой KeePass: CRUD для записей и групп."""

from typing import Optional
from pykeepass import PyKeePass


def save(kp: PyKeePass) -> Optional[str]:
    """Сохраняет базу. Возвращает сообщение об ошибке или None."""
    try:
        kp.save()
        return None
    except Exception as exc:
        return str(exc)


# ─── Группы ──────────────────────────────────────────────────────────────────

def refresh_group(kp: PyKeePass, group):
    """После kp.reload() возвращает свежий объект группы по UUID."""
    fresh = kp.find_groups(uuid=group.uuid, first=True)
    return fresh if fresh is not None else kp.root_group


def group_path(group) -> str:
    """Путь от корня до группы, например: 'Work / Email'."""
    parts = []
    g = group

    while g and g.name:
        parts.append(g.name)
        g = g.group  # родительская группа

    return " / ".join(reversed(parts))


def create_group(kp: PyKeePass, parent_group, name: str) -> Optional[str]:
    """Создаёт подгруппу. Возвращает ошибку или None."""
    try:
        kp.add_group(parent_group, name)
        return save(kp)
    except Exception as exc:
        return str(exc)


def rename_group(kp: PyKeePass, group, new_name: str) -> Optional[str]:
    """Переименовывает группу. Возвращает ошибку или None."""
    try:
        group.name = new_name
        return save(kp)
    except Exception as exc:
        return str(exc)


def delete_group(kp: PyKeePass, group) -> Optional[str]:
    """Удаляет группу. Возвращает ошибку или None."""
    try:
        kp.delete_group(group)
        return save(kp)
    except Exception as exc:
        return str(exc)


# ─── Записи ──────────────────────────────────────────────────────────────────

def create_entry(
    kp: PyKeePass,
    group,
    title: str,
    username: str = "",
    password: str = "",
    url: str = "",
) -> Optional[str]:
    """Создаёт запись. Возвращает ошибку или None."""
    try:
        kp.add_entry(group, title, username, password, url=url)
        return save(kp)
    except Exception as exc:
        return str(exc)


def update_entry(
    kp: PyKeePass,
    entry,
    title: str,
    username: str,
    password: str,
    url: str,
) -> Optional[str]:
    """Обновляет поля записи. Возвращает ошибку или None."""
    try:
        entry.title    = title
        entry.username = username
        entry.password = password
        entry.url      = url
        return save(kp)
    except Exception as exc:
        return str(exc)


def delete_entry(kp: PyKeePass, entry) -> Optional[str]:
    """Удаляет запись. Возвращает ошибку или None."""
    try:
        kp.delete_entry(entry)
        return save(kp)
    except Exception as exc:
        return str(exc)
