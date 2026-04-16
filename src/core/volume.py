"""Volume management — create, load, and manage backup volumes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.models.schemas import (
    DiscMeta,
    DiscStatus,
    EncryptionConfig,
    ErasureConfig,
    RedundancyLevel,
    VolumeMeta,
    VolumeStatus,
)

VAULT_DIR = ".bluray-vault"
META_FILE = "volume.json"
STAGING_DIR = "staging"


# Redundancy presets: (data_stripes, parity_stripes)
REDUNDANCY_PRESETS: dict[RedundancyLevel, tuple[int, int]] = {
    RedundancyLevel.STANDARD: (16, 4),
    RedundancyLevel.HIGH: (16, 8),
    RedundancyLevel.EXTREME: (8, 8),
}


def _volume_path(volume_name: str) -> Path:
    """Return the path to a volume's metadata directory."""
    return Path.cwd() / volume_name / VAULT_DIR


def init_volume(
    name: str,
    redundancy: RedundancyLevel = RedundancyLevel.HIGH,
    passphrase: str = "",
) -> VolumeMeta:
    """Initialize a new backup volume on disk."""
    vpath = _volume_path(name)
    if vpath.exists():
        raise FileExistsError(f"Volume '{name}' already exists at {vpath.parent}")

    data_stripes, parity_stripes = REDUNDANCY_PRESETS[redundancy]

    meta = VolumeMeta(
        name=name,
        erasure=ErasureConfig(
            redundancy=redundancy,
            data_stripes=data_stripes,
            parity_stripes=parity_stripes,
        ),
        encryption=EncryptionConfig(),
    )

    # Create directory structure
    vpath.mkdir(parents=True, exist_ok=True)
    staging = vpath.parent / STAGING_DIR
    staging.mkdir(parents=True, exist_ok=True)

    # Save metadata
    save_volume_meta(meta, vpath)
    return meta


def load_volume(name: str) -> VolumeMeta:
    """Load volume metadata from disk."""
    vpath = _volume_path(name)
    meta_file = vpath / META_FILE
    if not meta_file.exists():
        raise FileNotFoundError(f"Volume '{name}' not found")

    with open(meta_file) as f:
        data = json.load(f)

    erasure = ErasureConfig(
        redundancy=RedundancyLevel(data["erasure"]["redundancy"]),
        data_stripes=data["erasure"]["data_stripes"],
        parity_stripes=data["erasure"]["parity_stripes"],
        chunk_size=data["erasure"]["chunk_size"],
        gf_degree=data["erasure"]["gf_degree"],
    )
    encryption = EncryptionConfig(
        algorithm=data["encryption"]["algorithm"],
        kdf=data["encryption"]["kdf"],
        key_length=data["encryption"]["key_length"],
    )
    discs = []
    for d in data.get("discs", []):
        discs.append(DiscMeta(
            disc_id=d["disc_id"],
            disc_index=d["disc_index"],
            status=DiscStatus(d["status"]),
            data_chunks=d.get("data_chunks", 0),
            parity_chunks=d.get("parity_chunks", 0),
            total_bytes=d.get("total_bytes", 0),
            checksum=d.get("checksum", ""),
        ))

    return VolumeMeta(
        volume_id=data["volume_id"],
        name=data["name"],
        status=VolumeStatus(data["status"]),
        erasure=erasure,
        encryption=encryption,
        total_discs=data.get("total_discs", 0),
        discs=discs,
    )


def save_volume_meta(meta: VolumeMeta, vpath: Path | None = None) -> None:
    """Save volume metadata to disk."""
    if vpath is None:
        vpath = _volume_path(meta.name)

    data = {
        "volume_id": meta.volume_id,
        "name": meta.name,
        "created_at": meta.created_at.isoformat(),
        "status": meta.status.value,
        "erasure": {
            "redundancy": meta.erasure.redundancy.value,
            "data_stripes": meta.erasure.data_stripes,
            "parity_stripes": meta.erasure.parity_stripes,
            "chunk_size": meta.erasure.chunk_size,
            "gf_degree": meta.erasure.gf_degree,
        },
        "encryption": {
            "algorithm": meta.encryption.algorithm,
            "kdf": meta.encryption.kdf,
            "key_length": meta.encryption.key_length,
        },
        "total_discs": meta.total_discs,
        "discs": [
            {
                "disc_id": d.disc_id,
                "disc_index": d.disc_index,
                "status": d.status.value,
                "data_chunks": d.data_chunks,
                "parity_chunks": d.parity_chunks,
                "total_bytes": d.total_bytes,
                "checksum": d.checksum,
            }
            for d in meta.discs
        ],
    }

    meta_file = vpath / META_FILE
    with open(meta_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def list_volumes(base_dir: Path | None = None) -> list[str]:
    """List all volumes found under base_dir."""
    if base_dir is None:
        base_dir = Path.cwd()
    volumes = []
    for child in sorted(base_dir.iterdir()):
        vault = child / VAULT_DIR
        if vault.is_dir() and (vault / META_FILE).exists():
            volumes.append(child.name)
    return volumes
