"""Генерация паролей, смена пароля через SSH и страховочный tmp-файл."""

import base64
import json
import secrets
import string
import subprocess
import sys
from datetime import datetime

from constants import PATH_FILE_TMP


# ─── Генерация пароля ─────────────────────────────────────────────────────────


def generate_password(n: int = 20) -> str:
    """Криптографически стойкий пароль длиной *n* с символами всех классов."""
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = string.punctuation

    required = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    all_chars = lower + upper + digits + special
    rest = [secrets.choice(all_chars) for _ in range(n - 4)]
    pool = required + rest
    secrets.SystemRandom().shuffle(pool)
    return "".join(pool)


# ─── Страховочный файл ────────────────────────────────────────────────────────


def _tmp_write(ip: str, username: str, new_password: str) -> None:
    """Записывает новый пароль в страховочный файл ДО отправки на сервер."""
    record = {
        "ip": ip,
        "username": username,
        "password": new_password,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(PATH_FILE_TMP, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _tmp_read() -> list[dict]:
    """Возвращает все записи из страховочного файла (или пустой список)."""
    if not PATH_FILE_TMP.exists():
        return []

    records = []

    with open(PATH_FILE_TMP, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    return records


def cleanup_tmp_against_keepass(kp) -> int:
    """Удаляет из страховочного файла записи, уже синхронизированные с KeePass.

    Сравнение: если пароль в tmp совпадает с паролем записи в KeePass
    (найденной по username + ip в поле url) — запись считается синхронизированной.

    Удаление строк происходит в отдельном subprocess, чтобы не блокировать UI.

    Returns:
        Количество удалённых записей.
    """
    records = _tmp_read()

    if not records:
        return 0

    surviving = []
    removed = 0

    for rec in records:
        matched_entry = _find_kp_entry(kp, rec["ip"], rec["username"])

        if matched_entry and matched_entry.password == rec["password"]:
            removed += 1  # пароль совпал — запись уже в KeePass
        else:
            surviving.append(rec)

    if removed == len(records):
        _tmp_delete_file()
        return removed

    # Все записи синхронизированы — удаляем файл целиком в subprocess
    if not surviving:
        _tmp_delete_file()
        return removed

    # Есть несинхронизированные строки — перезаписываем файл в subprocess
    new_content = "\n".join(json.dumps(r, ensure_ascii=False) for r in surviving) + "\n"

    script = (
        "import sys; "
        f"open({str(PATH_FILE_TMP)!r}, 'w', encoding='utf-8').write(sys.stdin.read())"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if proc.stdin is not None:
        proc.stdin.write(new_content.encode("utf-8"))
        proc.stdin.close()
    # Не ждём — fire-and-forget; файл небольшой, гонок нет

    return removed


def _find_kp_entry(kp, ip: str, username: str):
    """Ищет запись в KeePass по username и совпадению ip в поле url."""
    for entry in kp.entries:
        if entry.username != username:
            continue
        url = (entry.url or "").strip()
        # url может быть "192.168.1.1", "ssh://192.168.1.1", "ssh://192.168.1.1/"
        for prefix in ("ssh://", "http://", "https://", "ftp://"):
            if url.lower().startswith(prefix):
                url = url[len(prefix) :]
                break

        url = url.rstrip("/").split("/")[0].split(":")[0]

        if url == ip:
            return entry

    return None


# ─── Восстановление при сбое сохранения KeePass ──────────────────────────────
def _ssh_check_connect(ip: str, username: str, password: str) -> bool:
    """Пробует подключиться по SSH. Возвращает True если успешно."""
    try:
        import paramiko
    except ImportError:
        return False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=ip,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
        ssh.close()
        return True
    except Exception:
        return False


def _tmp_delete_file() -> None:
    """Удаляет страховочный файл в subprocess (fire-and-forget)."""
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import pathlib; pathlib.Path({str(PATH_FILE_TMP)!r}).unlink(missing_ok=True)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def recover_from_tmp(kp) -> list[dict]:
    """Восстанавливает пароли из страховочного файла при сбое сохранения KeePass.

    Для каждой записи из tmp-файла:
    1. Если пароль уже совпадает с KeePass — запись синхронизирована, пропускаем.
    2. Пробуем подключиться к серверу с паролем из tmp-файла.
       - Успех → обновляем пароль в KeePass и сохраняем базу.
       - Неудача → пароль на сервере не был сменён, tmp-запись устарела.
    3. В обоих случаях в конце удаляем страховочный файл.

    Returns:
        Список dict с результатами по каждой записи:
        {"ip", "username", "status": "synced"|"recovered"|"failed", "detail": str}
    """
    records = _tmp_read()
    if not records:
        return []

    results = []

    for rec in records:
        ip = rec["ip"]
        username = rec["username"]
        tmp_pw = rec["password"]

        kp_entry = _find_kp_entry(kp, ip, username)

        # Уже синхронизировано
        if kp_entry and kp_entry.password == tmp_pw:
            results.append(
                {
                    "ip": ip,
                    "username": username,
                    "status": "synced",
                    "detail": "пароль уже совпадает с KeePass",
                }
            )
            continue

        # Пробуем подключиться с паролем из tmp
        connected = _ssh_check_connect(ip, username, tmp_pw)

        if connected:
            # Пароль на сервере сменился, но в KeePass не записался — исправляем
            if kp_entry:
                kp_entry.password = tmp_pw
            try:
                kp.save()
                detail = "пароль восстановлен и сохранён в KeePass"
                status = "recovered"
            except Exception as exc:
                # kp.save() упал — файл трогать нельзя, пароль всё ещё нужен.
                # Возвращаем частичные результаты и выходим без удаления файла.
                results.append(
                    {
                        "ip": ip,
                        "username": username,
                        "status": "failed",
                        "detail": f"пароль актуален на сервере, но сохранить в KeePass не удалось: {exc}",
                    }
                )
                return results
        else:
            # Подключение не удалось — пароль на сервере не был сменён
            detail = "подключение с паролем из tmp не удалось — запись устарела"
            status = "failed"

        results.append(
            {"ip": ip, "username": username, "status": status, "detail": detail}
        )

    # В любом случае удаляем файл — он либо обработан, либо устарел
    _tmp_delete_file()

    return results


# ─── Смена пароля по SSH ─────────────────────────────────────────────────────


def ssh_change_password(
    ip: str,
    username: str,
    current_password: str,
) -> tuple[str | None, str | None]:
    """Подключается по SSH и меняет пароль пользователя.

    Перед подключением записывает новый пароль в страховочный файл,
    чтобы при сбое сохранения KeePass пароль не был потерян.

    Returns:
        (new_password, None)   — при успехе
        (None, error_message)  — при ошибке
    """
    try:
        import paramiko
    except ImportError:
        return None, "paramiko не установлен: pip install paramiko"

    new_password = generate_password()

    # Страховка: пишем ДО отправки на сервер
    _tmp_write(ip, username, new_password)

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=ip,
            username=username,
            password=current_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )

        # Передаём sudo-пароль через stdin напрямую — без shell-интерполяции.
        # Это единственный надёжный способ при паролях со спецсимволами.
        encoded = base64.b64encode(f"{username}:{new_password}".encode()).decode()
        command = f"sudo -S sh -c 'echo {encoded} | base64 -d | chpasswd'"

        transport = ssh.get_transport()

        if transport is None:
            raise RuntimeError("Транспорт SSH недоступен")

        channel = transport.open_session()
        channel.exec_command(command)
        channel.sendall(f"{current_password}\n".encode())
        channel.shutdown_write()

        exit_code = channel.recv_exit_status()
        stderr_buf = b""
        while channel.recv_stderr_ready():
            stderr_buf += channel.recv_stderr(4096)
        ssh.close()

        error_raw = stderr_buf.decode().strip()
        real_err = "\n".join(
            line for line in error_raw.splitlines() if not line.startswith("[sudo]")
        )

        if exit_code == 0:
            return new_password, None
        return None, real_err or f"exit code {exit_code}"

    except Exception as exc:
        return None, str(exc)
