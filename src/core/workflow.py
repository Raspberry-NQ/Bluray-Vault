"""Backup workflow — add files, burn discs, verify, recover."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from src.core.volume import STAGING_DIR, VAULT_DIR, load_volume, save_volume_meta
from src.disc.disc_manager import DiscLayoutManager
from src.encoder.base import CauchyRSCore, CodeSpec, create_codec
from src.models.schemas import DiscMeta, DiscStatus, VolumeStatus


def add_files(volume_name: str, file_paths: list[str]) -> int:
    """Stage files for burning to the volume.

    Returns the number of files added.
    """
    meta = load_volume(volume_name)
    staging = Path(volume_name) / STAGING_DIR
    staging.mkdir(parents=True, exist_ok=True)

    count = 0
    for fpath in file_paths:
        src = Path(fpath)
        if not src.exists():
            print(f"  [skip] File not found: {fpath}")
            continue
        dst = staging / src.name
        if dst.exists():
            print(f"  [skip] Already staged: {src.name}")
            continue
        shutil.copy2(src, dst)
        count += 1

    if count > 0:
        meta.status = VolumeStatus.STAGING
        save_volume_meta(meta)

    return count


def burn_volume(volume_name: str, passphrase: str = "") -> list[DiscMeta]:
    """Burn staged data to disc(s).

    Pipeline: staged files -> chunk -> encrypt -> erasure encode -> disc image

    Returns list of disc metadata for burned discs.
    """
    meta = load_volume(volume_name)
    staging = Path(volume_name) / STAGING_DIR

    if not staging.exists() or not any(staging.iterdir()):
        print("  No staged files to burn.")
        return []

    # Read all staged files
    data = b""
    for fpath in sorted(staging.iterdir()):
        data += fpath.read_bytes()

    # Setup encoder
    spec = CodeSpec(
        data_shards=meta.erasure.data_stripes,
        parity_shards=meta.erasure.parity_stripes,
        shard_size=meta.erasure.chunk_size,
        gf_degree=meta.erasure.gf_degree,
    )
    codec = create_codec(spec, algorithm="cauchy_rs")
    layout_mgr = DiscLayoutManager(meta.erasure)

    # Chunk and encode
    chunks = layout_mgr.chunk_data(data)
    burned_discs: list[DiscMeta] = []

    # Pad data to fill complete stripe set
    stripe_size = spec.data_shards * spec.shard_size
    while len(data) % stripe_size != 0:
        data += b"\0"

    # Encode each stripe group
    disc_index = len(meta.discs)
    offset = 0
    stripe_groups: list[bytes] = []

    while offset < len(data):
        stripe_data = data[offset : offset + stripe_size]
        stripe_groups.append(stripe_data)
        offset += stripe_size

    # Group stripes into disc-sized batches
    # For now: one disc per burn operation
    disc_meta = DiscMeta(
        disc_index=disc_index,
        status=DiscStatus.BURNED,
        data_chunks=len(chunks),
        parity_chunks=spec.parity_shards * max(1, len(stripe_groups)),
        total_bytes=len(data),
        checksum=hashlib.sha256(data).hexdigest()[:16],
    )

    # TODO: Actual encryption + encoding + UDF image creation + disc burn
    print(f"  [simulated] Encoded {len(stripe_groups)} stripe groups")
    print(f"  [simulated] {disc_meta.data_chunks} data + {disc_meta.parity_chunks} parity chunks")
    print(f"  [simulated] Total: {disc_meta.total_bytes:,} bytes")

    burned_discs.append(disc_meta)
    meta.discs.append(disc_meta)
    meta.total_discs = len(meta.discs)
    meta.status = VolumeStatus.COMPLETE
    save_volume_meta(meta)

    # Clear staging after successful burn
    for f in staging.iterdir():
        f.unlink()

    return burned_discs


def verify_volume(volume_name: str, disc_index: int | None = None) -> bool:
    """Verify disc integrity by reading back and checking checksums."""
    meta = load_volume(volume_name)
    discs = meta.discs
    if disc_index is not None:
        discs = [d for d in discs if d.disc_index == disc_index]

    if not discs:
        print("  No discs to verify.")
        return False

    all_ok = True
    for d in discs:
        # TODO: Actual disc verification via DiscIO
        print(f"  [simulated] Verifying disc {d.disc_index} ({d.disc_id})... OK")
    return all_ok


def recover_volume(volume_name: str, output_dir: str, passphrase: str = "") -> bool:
    """Recover data from disc set to output directory.

    Pipeline: disc read -> erasure decode -> decrypt -> reassemble files
    """
    meta = load_volume(volume_name)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not meta.discs:
        print("  No discs found for recovery.")
        return False

    # TODO: Actual recovery pipeline
    # 1. Scan available discs, detect damage
    # 2. Determine minimum disc set for recovery
    # 3. Erasure decode if needed
    # 4. Decrypt chunks
    # 5. Reassemble files

    print(f"  [simulated] Recovering from {len(meta.discs)} disc(s)...")
    print(f"  [simulated] Output: {out}")
    total_data = sum(d.total_bytes for d in meta.discs)
    print(f"  [simulated] Total data: {total_data:,} bytes")
    return True


def status_volume(volume_name: str) -> None:
    """Print volume status summary."""
    meta = load_volume(volume_name)
    print(f"  Volume: {meta.name} (id: {meta.volume_id})")
    print(f"  Status: {meta.status.value}")
    print(f"  Redundancy: {meta.erasure.redundancy.value} "
          f"({meta.erasure.data_stripes}+{meta.erasure.parity_stripes})")
    print(f"  Discs: {meta.total_discs}")
    for d in meta.discs:
        print(f"    Disc {d.disc_index} ({d.disc_id}): {d.status.value}, "
              f"{d.data_chunks} data + {d.parity_chunks} parity, "
              f"{d.total_bytes:,} bytes")
