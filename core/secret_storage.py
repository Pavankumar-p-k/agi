# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
        logger.error(f"Encryption failed: {e}")
        raise RuntimeError(f"Could not encrypt secret: {e}")


def decrypt(ciphertext: str) -> str:
    # Handle legacy unencrypted values if necessary, or just fail
    try:
        from cryptography.fernet import Fernet
        key_file = os.path.join(DATA_DIR, ".app_key")
        with open(key_file, "rb") as f:
            key = f.read().strip()
        cipher = Fernet(key)
        return cipher.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise RuntimeError(f"Could not decrypt secret: {e}")
