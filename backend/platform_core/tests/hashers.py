"""TEST-ONLY password hasher: PBKDF2-SHA256 with a small work factor so the test suite stays fast.

Configured only in ``aleekhan.settings_test``; production uses Django's PBKDF2PasswordHasher defaults.
"""

from __future__ import annotations

from django.contrib.auth.hashers import PBKDF2PasswordHasher


class FastPBKDF2ForTests(PBKDF2PasswordHasher):
    algorithm = "pbkdf2_sha256_test"
    iterations = 1000
