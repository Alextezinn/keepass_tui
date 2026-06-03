"""Проверка паролей на утечки через HaveIBeenPwned API (k-anonymity модель).

Пароль никогда не передаётся на сервер — только первые 5 символов SHA-1 хэша.
API возвращает список суффиксов, совпадение проверяется локально.
"""

import hashlib
import time
import urllib.error
import urllib.request
from typing import Tuple


def is_password_pwned(password: str, retries: int = 3) -> Tuple[bool, int]:
    """Проверяет пароль по базе HaveIBeenPwned.

    Args:
        password: Проверяемый пароль.
        retries:  Число повторных попыток при ошибке 429.

    Returns:
        (True,  count) — пароль найден в утечках, count — количество вхождений.
        (False, 0)     — пароль не найден или запрос не удался.

    Raises:
        urllib.error.HTTPError — при HTTP-ошибке кроме 429.
        urllib.error.URLError  — при сетевых проблемах.
    """
    sha1   = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix = sha1[:5]
    suffix = sha1[5:]
    url    = f"https://api.pwnedpasswords.com/range/{prefix}"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"Add-Padding": "true"},  # защита от traffic analysis
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                retry_after = int(exc.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                continue
            raise
    else:
        return False, 0

    for line in data.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        hash_suffix, count = line.split(":", 1)
        if hash_suffix == suffix:
            return True, int(count)

    return False, 0
