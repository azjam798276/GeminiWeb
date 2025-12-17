from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


def fernet_from_key_str(key_str: str) -> Fernet:
    return Fernet(key_str.encode("utf-8"))


def encrypt_bytes(key_str: str, data: bytes) -> bytes:
    return fernet_from_key_str(key_str).encrypt(data)


def decrypt_bytes(key_str: str, token: bytes) -> bytes:
    try:
        return fernet_from_key_str(key_str).decrypt(token)
    except InvalidToken as e:
        raise ValueError("Failed to decrypt credentials (wrong key or corrupted file).") from e

