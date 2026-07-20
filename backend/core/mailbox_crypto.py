import os

from fastapi import HTTPException
from cryptography.fernet import Fernet

_fernet = None


def _get():
    global _fernet
    if _fernet is None:
        key = os.environ.get("MAILBOX_MASTER_KEY")
        if not key:
            raise HTTPException(status_code=500, detail="Mailbox encryption key (MAILBOX_MASTER_KEY) is not configured on the server.")
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_text(value: str) -> str:
    return _get().encrypt((value or "").encode()).decode()


def decrypt_text(value: str) -> str:
    return _get().decrypt((value or "").encode()).decode()
