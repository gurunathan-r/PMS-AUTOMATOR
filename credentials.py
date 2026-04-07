"""
Encrypted credential storage using Fernet symmetric encryption.
The encryption key is generated once and stored in .secret.key (gitignored).
Credentials are stored per-user in credentials/{chat_id}.enc (gitignored).
"""

import os
import json
from cryptography.fernet import Fernet

BASE_DIR = os.path.dirname(__file__)
KEY_PATH = os.path.join(BASE_DIR, ".secret.key")
CREDS_DIR = os.path.join(BASE_DIR, "credentials")


def _creds_path(chat_id: int) -> str:
    os.makedirs(CREDS_DIR, exist_ok=True)
    return os.path.join(CREDS_DIR, f"{chat_id}.enc")


def _get_or_create_key() -> bytes:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_PATH, "wb") as f:
        f.write(key)
    os.chmod(KEY_PATH, 0o600)
    return key


def _fernet() -> Fernet:
    return Fernet(_get_or_create_key())


def save_credentials(chat_id: int, email: str, password: str) -> None:
    data = json.dumps({"email": email, "password": password}).encode()
    encrypted = _fernet().encrypt(data)
    path = _creds_path(chat_id)
    with open(path, "wb") as f:
        f.write(encrypted)
    os.chmod(path, 0o600)


def load_credentials(chat_id: int) -> "dict | None":
    path = _creds_path(chat_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        encrypted = f.read()
    try:
        data = _fernet().decrypt(encrypted)
        return json.loads(data)
    except Exception:
        return None


def credentials_exist(chat_id: int) -> bool:
    return os.path.exists(_creds_path(chat_id)) and os.path.exists(KEY_PATH)


def clear_credentials(chat_id: int) -> None:
    path = _creds_path(chat_id)
    if os.path.exists(path):
        os.remove(path)
