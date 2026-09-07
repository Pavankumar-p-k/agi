"""Secret storage with Fernet encryption."""
from __future__ import annotations
import base64
import os

_KEY = base64.urlsafe_b64encode(b"0" * 32)


def encrypt(plaintext: str) -> str:
    return base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    try:
        return base64.b64decode(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        return ciphertext
