"""Утилита для копирования текста в системный буфер обмена."""

import subprocess
import sys


def copy_to_clipboard(text: str) -> None:
    """Копирует текст в буфер обмена (Linux / macOS / Windows).
    Ошибки игнорируются — операция не критична.
    """
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)

        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)

        else:
            # Linux: пробуем xclip, затем xsel
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(), check=True,
                    stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text.encode(), check=True,
                    stderr=subprocess.DEVNULL,
                )

    except Exception:
        pass
