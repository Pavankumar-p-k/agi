import logging
import os

from core.constants import DATA_DIR

logger = logging.getLogger(__name__)


def encrypt(plaintext: str) -> str:
    try:
        from cryptography.fernet import Fernet
        key_file = os.path.join(DATA_DIR, ".app_key")
        try:
            with open(key_file, "rb") as f:
                key = f.read().strip()
        except FileNotFoundError:
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, "wb") as f:
                f.write(key)
        cipher = Fernet(key)
        return cipher.encrypt(plaintext.encode()).decode()
    except Exception as e:
        logger.warning(f"encrypt failed: {e}")
        return plaintext


def decrypt(ciphertext: str) -> str:
    if ciphertext.startswith("enc:"):
        return ciphertext[4:]
    try:
        from cryptography.fernet import Fernet
        key_file = os.path.join(DATA_DIR, ".app_key")
        with open(key_file, "rb") as f:
            key = f.read().strip()
        cipher = Fernet(key)
        return cipher.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.warning(f"decrypt failed: {e}")
        return ciphertext
