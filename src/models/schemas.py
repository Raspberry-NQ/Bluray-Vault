"""Data models for Bluray Vault."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RedundancyLevel(str, Enum):
    STANDARD = "standard"  # 16+4 (20% overhead)
    HIGH = "high"          # 16+8 (50% overhead)
    EXTREME = "extreme"    # 8+8  (100% overhead)


class VolumeStatus(str, Enum):
    INITIALIZED = "initialized"
    STAGING = "staging"
    BURNING = "burning"
    COMPLETE = "complete"
    RECOVERING = "recovering"


class DiscStatus(str, Enum):
    EMPTY = "empty"
    BURNED = "burned"
    VERIFIED = "verified"
    DAMAGED = "damaged"


@dataclass
class ErasureConfig:
    """Erasure coding configuration for a volume."""
    redundancy: RedundancyLevel = RedundancyLevel.HIGH
    data_stripes: int = 16
    parity_stripes: int = 8
    chunk_size: int = 1048576  # 1 MiB
    gf_degree: int = 8  # GF(2^8) for intra-disc


@dataclass
class EncryptionConfig:
    """Encryption configuration for a volume."""
    algorithm: str = "AES-256-GCM"
    kdf: str = "Argon2id"
    key_length: int = 256


@dataclass
class DiscMeta:
    """Metadata for a single disc."""
    disc_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    disc_index: int = 0
    status: DiscStatus = DiscStatus.EMPTY
    burned_at: datetime | None = None
    verified_at: datetime | None = None
    data_chunks: int = 0
    parity_chunks: int = 0
    total_bytes: int = 0
    checksum: str = ""


@dataclass
class VolumeMeta:
    """Metadata for a backup volume."""
    volume_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    status: VolumeStatus = VolumeStatus.INITIALIZED
    erasure: ErasureConfig = field(default_factory=ErasureConfig)
    encryption: EncryptionConfig = field(default_factory=EncryptionConfig)
    total_discs: int = 0
    discs: list[DiscMeta] = field(default_factory=list)


@dataclass
class ChunkRef:
    """Reference to a chunk within a disc."""
    chunk_index: int
    offset: int
    size: int
    checksum: str
    stripe_id: int
