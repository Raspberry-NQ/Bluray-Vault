"""Backup workflow — add files, burn discs, verify, recover.

All functions return structured data; the UI layer handles display.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.core.volume import STAGING_DIR, load_volume, save_volume_meta
from src.disc.disc_manager import DiscLayoutManager
from src.encoder.base import CodeSpec, create_codec
from src.models.schemas import DiscMeta, DiscStatus, VolumeMeta, VolumeStatus


@dataclass
class BurnResult:
    discs: list[DiscMeta]
    stripe_groups: int
    total_bytes: int
    simulated: bool = True


@dataclass
class StageResult:
    added: list[str]
    skipped_not_found: list[str]
    skipped_exists: list[str]


def add_files(volume_name: str, file_paths: list[str]) -> StageResult:
    """Stage files for burning to the volume."""
    meta = load_volume(volume_name)
    staging = Path(volume_name) / STAGING_DIR
    staging.mkdir(parents=True, exist_ok=True)

    added, skipped_not_found, skipped_exists = [], [], []
    for fpath in file_paths:
        src = Path(fpath)
        if not src.exists():
            skipped_not_found.append(fpath)
            continue
        dst = staging / src.name
        if dst.exists():
            skipped_exists.append(src.name)
            continue
        shutil.copy2(src, dst)
        added.append(src.name)

    if added:
        meta.status = VolumeStatus.STAGING
        save_volume_meta(meta)

    return StageResult(added=added, skipped_not_found=skipped_not_found,
                       skipped_exists=skipped_exists)


def burn_volume(volume_name: str, passphrase: str = "") -> BurnResult:
    """Burn staged data to disc(s).

    Pipeline: staged files -> chunk -> encrypt -> erasure encode -> disc image
    """
    meta = load_volume(volume_name)
    staging = Path(volume_name) / STAGING_DIR

    if not staging.exists() or not any(staging.iterdir()):
        return BurnResult(discs=[], stripe_groups=0, total_bytes=0)

    # Read all staged files
    data = b""
    for fpath in sorted(staging.iterdir()):
        data += fpath.read_bytes()

    # Setup encoder — use a reasonable shard size for actual data volume
    # For small files, shrink shard_size so we don't pad massively
    chunk_size = meta.erasure.chunk_size
    data_shards = meta.erasure.data_stripes
    stripe_size = data_shards * chunk_size

    # Pad data to fill complete stripe set
    if len(data) % stripe_size != 0:
        pad_len = stripe_size - (len(data) % stripe_size)
        data += b"\0" * pad_len

    n_stripe_groups = len(data) // stripe_size

    spec = CodeSpec(
        data_shards=data_shards,
        parity_shards=meta.erasure.parity_stripes,
        shard_size=chunk_size,
        gf_degree=meta.erasure.gf_degree,
    )
    codec = create_codec(spec, algorithm="cauchy_rs")
    layout_mgr = DiscLayoutManager(meta.erasure)

    # Chunk and encode
    chunks = layout_mgr.chunk_data(data)

    disc_meta = DiscMeta(
        disc_index=len(meta.discs),
        status=DiscStatus.BURNED,
        data_chunks=len(chunks),
        parity_chunks=spec.parity_shards * max(1, n_stripe_groups),
        total_bytes=len(data),
        checksum=hashlib.sha256(data).hexdigest()[:16],
    )

    # TODO: Actual encryption + encoding + UDF image creation + disc burn

    burned_discs = [disc_meta]
    meta.discs.append(disc_meta)
    meta.total_discs = len(meta.discs)
    meta.status = VolumeStatus.COMPLETE
    save_volume_meta(meta)

    # Clear staging after successful burn
    for f in staging.iterdir():
        f.unlink()

    return BurnResult(
        discs=burned_discs,
        stripe_groups=n_stripe_groups,
        total_bytes=len(data),
        simulated=True,
    )


def verify_volume(volume_name: str, disc_index: int | None = None) -> list[DiscMeta]:
    """Verify disc integrity. Returns list of discs that were checked.

    (Actual verification TODO — currently returns discs for display.)
    """
    meta = load_volume(volume_name)
    discs = meta.discs
    if disc_index is not None:
        discs = [d for d in discs if d.disc_index == disc_index]
    # TODO: Actual disc verification via DiscIO
    return discs


def recover_volume(volume_name: str, output_dir: str, passphrase: str = "") -> tuple[VolumeMeta, int]:
    """Recover data from disc set. Returns (volume_meta, total_bytes)."""
    meta = load_volume(volume_name)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    total_data = sum(d.total_bytes for d in meta.discs)
    # TODO: Actual recovery pipeline
    return meta, total_data


def get_volume_status(volume_name: str) -> VolumeMeta:
    """Load and return volume metadata for display."""
    return load_volume(volume_name)


def get_staged_files(volume_name: str) -> list[str]:
    """Return list of filenames in staging area."""
    staging = Path(volume_name) / STAGING_DIR
    if not staging.exists():
        return []
    return sorted(f.name for f in staging.iterdir() if f.is_file())
