import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _key_material() -> str:
    material = (
        getattr(settings, 'STREAMING_ENCRYPTION_KEY', '')
        or getattr(settings, 'SECRET_KEY', '')
    )
    if not material:
        raise ValueError('No streaming encryption key configured')
    return material


def _fernet() -> Fernet:
    digest = hashlib.sha256(_key_material().encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    """Encrypt a secret for at-rest storage. Empty values pass through."""
    if not value:
        return ''
    return _fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt(value: str) -> str:
    """Decrypt an at-rest secret.

    Plaintext (unencrypted / legacy) values are returned unchanged so existing
    rows keep working until they are re-saved.
    """
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return value


class EncryptedTextField(models.TextField):
    """A TextField that transparently encrypts on write and decrypts on read."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        return encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        return decrypt(value)
