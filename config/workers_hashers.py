"""PBKDF2 compatibility without Web Crypto's deployed 100,000-iteration ceiling."""

import base64

from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.utils.encoding import force_bytes


class WorkersPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    # Keep Django's algorithm name, work factor, salt and encoded format. Existing
    # password hashes remain usable; verification retains Django's constant-time compare.
    def encode(self, password, salt, iterations=None):
        self._check_encode_args(password, salt)
        iterations = iterations or self.iterations
        digest = PBKDF2(
            force_bytes(password),
            force_bytes(salt),
            dkLen=32,
            count=iterations,
            hmac_hash_module=SHA256,
        )
        encoded = base64.b64encode(digest).decode("ascii")
        return f"{self.algorithm}${iterations}${salt}${encoded}"
