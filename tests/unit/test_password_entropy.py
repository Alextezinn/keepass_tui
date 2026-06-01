import unittest
import string
import math
from collections import Counter
import re

from keepass_tui.ssh.passwords import generate_password


class TestPasswordEntropy(unittest.TestCase):

    def test_password_entropy_approximation(self):
        """Примерная оценка криптографической энтропии пароля"""

        lengths = [20, 24, 32]

        alphabet_size = len(
            string.ascii_lowercase +
            string.ascii_uppercase +
            string.digits +
            string.punctuation
        )

        for n in lengths:
            with self.subTest(length=n):
                pwd = generate_password(n)

                # теоретическая энтропия
                min_entropy = len(pwd) * math.log2(alphabet_size)

                # оценка с поправкой на разнообразие символов
                unique_ratio = len(set(pwd)) / len(pwd)
                adjusted_entropy = min_entropy * unique_ratio

                self.assertGreaterEqual(
                    min_entropy,
                    120,
                    f"Слишком низкая теоретическая энтропия: {min_entropy:.1f} бит"
                )

                self.assertGreaterEqual(
                    adjusted_entropy,
                    100,
                    f"Слишком низкая реальная энтропия: {adjusted_entropy:.1f} бит"
                )

    def test_not_always_start_with_same_class(self):
        """
        Проверка детерминированных багов
        Пароль не должен всегда начинаться с одного и того же символа
        """
        starts = {generate_password(20)[0] for _ in range(200)}
        self.assertGreater(len(starts), 10)

    def test_character_distribution(self):
        """Проверка распределения символов (bias test)"""
        samples = [generate_password(20) for _ in range(2000)]
        all_chars = "".join(samples)

        counter = Counter(all_chars)

        avg = len(all_chars) / len(counter)

        # не должно быть сильного перекоса
        for count in counter.values():
            self.assertLess(count, avg * 3)

    def test_all_character_classes_present(self):
        """
        В пароле должен быть хотя бы 1 символ в нижнем регистре,
        в вверхнем, хотя бы 1 цифра и 1 спец символ.
        """
        pwd = generate_password(20)

        self.assertRegex(pwd, r"[a-z]")
        self.assertRegex(pwd, r"[A-Z]")
        self.assertRegex(pwd, r"[0-9]")
        self.assertRegex(pwd, r"[{}]".format(re.escape(string.punctuation)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
