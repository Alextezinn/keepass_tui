"""Генерация паролей и смена пароля через SSH."""

import base64
import secrets
import string
import json
from typing import Optional, Tuple
from datetime import datetime

from constants import PATH_FILE_TMP


def generate_password(n: int = 20) -> str:
    """Генерирует криптографически стойкий пароль длиной *n* символов.

    Гарантирует наличие хотя бы одного символа каждого класса:
    строчные, прописные, цифры, спецсимволы.
    """
    lower   = string.ascii_lowercase
    upper   = string.ascii_uppercase
    digits  = string.digits
    special = string.punctuation

    required = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    all_chars = lower + upper + digits + special
    rest = [secrets.choice(all_chars) for _ in range(n - 4)]

    password = required + rest
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def ssh_change_password(
        ip: str,
        username: str,
        current_password: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Подключается по SSH и меняет пароль пользователя.

    Returns:
        (new_password, None)   — при успехе
        (None, error_message)  — при ошибке
    """
    try:
        import paramiko
    except ImportError:
        return None, "paramiko не установлен: pip install paramiko"

    new_password = generate_password()
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
        encoded = base64.b64encode(
            f"{username}:{new_password}".encode()
        ).decode()
        command = f"sudo -S sh -c 'echo {encoded} | base64 -d | chpasswd'"

        transport = ssh.get_transport()
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
            line for line in error_raw.splitlines()
            if not line.startswith("[sudo]")
        )

        if exit_code == 0:
            return new_password, None
        return None, real_err or f"exit code {exit_code}"

    except Exception as exc:
        return None, str(exc)
