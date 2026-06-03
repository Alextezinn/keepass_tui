import secrets
import string


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
