from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .crypto import decrypt_bytes, encrypt_bytes


@dataclass(frozen=True)
class StoredCredentials:
    payload: dict[str, Any]


class EncryptedCredentialStore:
    """
    Simple encrypted-at-rest credential store.

    Stores ONE blob at `path`:
      - encrypted JSON bytes (Fernet)
    """

    def __init__(self, path: str, fernet_key: str):
        self.path = Path(path)
        self.fernet_key = fernet_key

    def exists(self) -> bool:
        return self.path.exists()

    def save(self, creds: StoredCredentials) -> None:
        raw = json.dumps(creds.payload).encode("utf-8")
        enc = encrypt_bytes(self.fernet_key, raw)
        self.path.write_bytes(enc)

    def load(self) -> StoredCredentials:
        enc = self.path.read_bytes()
        raw = decrypt_bytes(self.fernet_key, enc)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Credential payload must be a JSON object.")
        return StoredCredentials(payload=cast(dict[str, Any], payload))
