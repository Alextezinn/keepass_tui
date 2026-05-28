"""Генерация паролей и смена пароля через SSH."""

import base64
import secrets
import string
from typing import Optional, Tuple


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

        encoded = base64.b64encode(
            f"{username}:{new_password}".encode()
        ).decode()
        command = (
            f"printf '%s\\n' {current_password!r} | sudo -S sh -c "
            f'"echo {encoded} | base64 -d | chpasswd"'
        )

        _, stdout, stderr = ssh.exec_command(command, get_pty=False)
        exit_code = stdout.channel.recv_exit_status()
        error_raw = stderr.read().decode().strip()
        real_err = "\n".join(
            line for line in error_raw.splitlines()
            if not line.startswith("[sudo]")
        )
        ssh.close()

        if exit_code == 0:
            return new_password, None
        return None, real_err or f"exit code {exit_code}"

    except Exception as exc:
        return None, str(exc)