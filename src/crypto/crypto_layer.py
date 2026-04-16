"""Encryption layer — AES-256-GCM with Argon2id key derivation.

This module provides authenticated encryption for data at rest on disc.
Per-chunk nonces prevent nonce reuse across chunks.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class EncryptionLayer(ABC):
    """Abstract encryption interface."""

    @abstractmethod
    def encrypt(self, plaintext: bytes, chunk_index: int) -> bytes:
        """Encrypt a chunk. Nonce derived from chunk_index + disc salt."""
        ...

    @abstractmethod
    def decrypt(self, ciphertext: bytes, chunk_index: int) -> bytes:
        """Decrypt a chunk."""
        ...


class AES256GCM(EncryptionLayer):
    """AES-256-GCM authenticated encryption.

    - Key: derived from user passphrase via Argon2id
    - Nonce: 12 bytes, derived from (disc_salt || chunk_index)
    - Salt: random per-disc, stored unencrypted in disc header
    """

    NONCE_SIZE = 12  # 96-bit nonce for GCM
    SALT_SIZE = 32
    KEY_SIZE = 32  # 256-bit key

    def __init__(self, passphrase: str, disc_salt: bytes | None = None) -> None:
        self.disc_salt = disc_salt or os.urandom(self.SALT_SIZE)
        self._key: bytes | None = None
        self._passphrase = passphrase

    def _derive_key(self) -> bytes:
        """Derive AES-256 key from passphrase using Argon2id."""
        if self._key is not None:
            return self._key

        # TODO: Implement Argon2id key derivation
        # from argon2.low_level import hash_secret_raw, Type
        # self._key = hash_secret_raw(
        #     secret=self._passphrase.encode(),
        #     salt=self.disc_salt,
        #     time_cost=3, memory_cost=65536, parallelism=4,
        #     hash_len=self.KEY_SIZE, type=Type.ID
        # )

        # Placeholder: for development only
        self._key = self._passphrase.encode().ljust(self.KEY_SIZE, b"\0")[:self.KEY_SIZE]
        return self._key

    def _derive_nonce(self, chunk_index: int) -> bytes:
        """Derive a unique nonce from disc salt and chunk index."""
        # TODO: Use a proper KDF or MAC for nonce derivation
        # nonce = HMAC-SHA256(disc_salt, chunk_index)[:12]
        index_bytes = chunk_index.to_bytes(8, "big")
        raw = self.disc_salt[:4] + index_bytes
        # Pad or truncate to 12 bytes
        return raw.ljust(self.NONCE_SIZE, b"\0")[:self.NONCE_SIZE]

    def encrypt(self, plaintext: bytes, chunk_index: int) -> bytes:
        key = self._derive_key()
        nonce = self._derive_nonce(chunk_index)

        # TODO: Implement AES-256-GCM encryption
        # from Crypto.Cipher import AES
        # cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        # ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        # return tag + ciphertext

        # Placeholder: pass through for development
        return plaintext

    def decrypt(self, ciphertext: bytes, chunk_index: int) -> bytes:
        key = self._derive_key()
        nonce = self._derive_nonce(chunk_index)

        # TODO: Implement AES-256-GCM decryption
        # from Crypto.Cipher import AES
        # tag = ciphertext[:16]
        # data = ciphertext[16:]
        # cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        # return cipher.decrypt_and_verify(data, tag)

        # Placeholder: pass through for development
        return ciphertext
