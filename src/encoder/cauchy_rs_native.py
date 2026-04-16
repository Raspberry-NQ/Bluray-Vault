"""ctypes binding to the Cauchy-RS-FEC C library (librs_code).

This module provides a Python wrapper around the C implementation in
Cauchy-RS-FEC/rs_code.c, exposing rs_init / rs_encode / rs_decode via ctypes.

Data model mapping:
  C library:  message = mlen uint32 words
              packets = npackets * plentot uint32 words
  Python API: data = bytes (k * shard_size)
              shards = list[bytes] (k+m shards, each shard_size bytes)

The C library works with "packets" whose internal layout is:
  [index_word, payload_word_0, payload_word_1, ..., payload_word_(plen-1)]

We map our shard concept onto these packets:
  - shard_size = plen * sizeof(uint32)
  - Total data = k shards = mpackets packets of payload
  - Total output = (k+m) packets, each shard_size bytes of payload
"""

from __future__ import annotations

import ctypes
import os
import platform
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

# ── Locate shared library ─────────────────────────────────────

def _find_lib() -> str:
    """Find the compiled rs_code shared library."""
    repo_root = Path(__file__).resolve().parent.parent.parent  # Bluray-Vault/
    lib_dir = repo_root / "Cauchy-RS-FEC" / "build"

    if platform.system() == "Darwin":
        lib_name = "librs_code.dylib"
    elif platform.system() == "Linux":
        lib_name = "librs_code.so"
    else:
        lib_name = "rs_code.dll"

    lib_path = lib_dir / lib_name
    if not lib_path.exists():
        # Try without build subdir, or with different naming
        for candidate in [
            lib_dir / lib_name,
            lib_dir / "CMakeFiles" / "rs_code_shared" / lib_name,
            repo_root / "Cauchy-RS-FEC" / lib_name,
        ]:
            if candidate.exists():
                return str(candidate)
        raise FileNotFoundError(
            f"Shared library not found at {lib_path}. "
            f"Build it with: cd Cauchy-RS-FEC && mkdir -p build && cd build && "
            f"cmake .. && make rs_code_shared"
        )
    return str(lib_path)


# ── C struct definitions ──────────────────────────────────────

class CRsConfig(ctypes.Structure):
    _fields_ = [
        ("lfield", ctypes.c_int),
        ("nsegs", ctypes.c_int),
        ("mpackets", ctypes.c_int),
        ("rpackets", ctypes.c_int),
        ("print_debug", ctypes.c_int),
    ]


class CRsParams(ctypes.Structure):
    _fields_ = [
        ("npackets", ctypes.c_int),
        ("mseglen", ctypes.c_int),
        ("plen", ctypes.c_int),
        ("plentot", ctypes.c_int),
        ("mlen", ctypes.c_int),
        ("elen", ctypes.c_int),
        ("table_length", ctypes.c_int),
        ("smult_field", ctypes.c_int),
    ]


class CRsCtx(ctypes.Structure):
    pass  # Opaque — we only need sizeof for allocation


# Compute sizeof(rs_ctx_t) by replicating the C struct layout
class _RsCtxLayout(ctypes.Structure):
    _fields_ = [
        ("cfg", CRsConfig),
        ("par", CRsParams),
        ("exptoFE", ctypes.POINTER(ctypes.c_uint32)),
        ("fetoExp", ctypes.POINTER(ctypes.c_uint32)),
        ("colbit", ctypes.c_uint32),
        ("bit", ctypes.c_uint32 * 16),
    ]


# ── Library wrapper ───────────────────────────────────────────

class CauchyRSLib:
    """Low-level wrapper around the C rs_code library."""

    _instance: CauchyRSLib | None = None

    def __init__(self) -> None:
        lib_path = _find_lib()
        self.lib = ctypes.CDLL(lib_path)

        # rs_init
        self.lib.rs_init.argtypes = [ctypes.POINTER(_RsCtxLayout), ctypes.POINTER(CRsConfig)]
        self.lib.rs_init.restype = ctypes.c_int

        # rs_free
        self.lib.rs_free.argtypes = [ctypes.POINTER(_RsCtxLayout)]
        self.lib.rs_free.restype = None

        # rs_encode
        self.lib.rs_encode.argtypes = [
            ctypes.POINTER(_RsCtxLayout),
            ctypes.POINTER(ctypes.c_uint32),  # message
            ctypes.POINTER(ctypes.c_uint32),  # packets
        ]
        self.lib.rs_encode.restype = None

        # rs_decode
        self.lib.rs_decode.argtypes = [
            ctypes.POINTER(_RsCtxLayout),
            ctypes.POINTER(ctypes.c_uint32),  # rec_packets
            ctypes.POINTER(ctypes.c_int),     # nrec
            ctypes.POINTER(ctypes.c_uint32),  # rec_message
        ]
        self.lib.rs_decode.restype = ctypes.c_int

    @classmethod
    def get(cls) -> CauchyRSLib:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


@dataclass
class CauchyRSContext:
    """Holds an initialized C library context and its derived parameters.

    This maps the C library's packet-based model to our shard-based model.

    Key relationships:
    - lfield: log2(GF size). For k+m <= 2^(lfield-1), i.e. lfield >= ceil(log2(k+m)) + 1
    - nsegs: segments per packet — controls packet payload size (plen = nsegs * lfield words)
    - plen: payload words per packet (excluding index word)
    - plentot: plen + 1 (including index word)
    - shard_size (Python) = plen * 4 bytes (payload only, no index)
    """

    _ctx: _RsCtxLayout
    mpackets: int   # = data_shards (k)
    rpackets: int   # = parity_shards (m)
    lfield: int
    nsegs: int
    plen: int       # payload words per packet
    plentot: int    # plen + 1
    mlen: int       # total message words
    shard_size: int  # plen * 4 bytes — payload bytes per shard

    def __del__(self) -> None:
        try:
            lib = CauchyRSLib.get()
            lib.lib.rs_free(ctypes.byref(self._ctx))
        except Exception:
            pass


def _compute_lfield(k: int, m: int) -> int:
    """Compute minimum lfield such that max(k,m) <= 2^(lfield-1)."""
    max_mr = max(k, m)
    lfield = 1
    while (1 << (lfield - 1)) < max_mr:
        lfield += 1
    # Clamp to valid range [1, 15]
    return min(max(lfield, 1), 15)


def _compute_nsegs(shard_size: int, lfield: int) -> int:
    """Compute nsegs from desired shard_size and lfield.

    shard_size = nsegs * lfield * sizeof(uint32)
    nsegs = shard_size / (lfield * 4)
    """
    words_per_shard = shard_size // 4  # convert bytes to uint32 words
    nsegs = words_per_shard // lfield
    if nsegs < 1:
        nsegs = 1
    return nsegs


def cauchy_rs_init(data_shards: int, parity_shards: int, shard_size: int) -> CauchyRSContext:
    """Initialize a Cauchy RS context via the C library.

    Args:
        data_shards: Number of data shards (k).
        parity_shards: Number of parity shards (m).
        shard_size: Desired shard size in bytes. Actual shard size may differ
                    slightly because it must be a multiple of lfield * 4.

    Returns:
        An initialized CauchyRSContext.
    """
    lfield = _compute_lfield(data_shards, parity_shards)
    nsegs = _compute_nsegs(shard_size, lfield)

    lib = CauchyRSLib.get()

    cfg = CRsConfig(
        lfield=lfield,
        nsegs=nsegs,
        mpackets=data_shards,
        rpackets=parity_shards,
        print_debug=0,
    )

    ctx = _RsCtxLayout()
    ret = lib.lib.rs_init(ctypes.byref(ctx), ctypes.byref(cfg))
    if ret != 0:
        raise RuntimeError(f"rs_init failed with code {ret}")

    actual_shard_size = ctx.par.plen * 4  # payload bytes per packet

    return CauchyRSContext(
        _ctx=ctx,
        mpackets=data_shards,
        rpackets=parity_shards,
        lfield=lfield,
        nsegs=nsegs,
        plen=ctx.par.plen,
        plentot=ctx.par.plentot,
        mlen=ctx.par.mlen,
        shard_size=actual_shard_size,
    )


def cauchy_rs_encode(ctx: CauchyRSContext, data: bytes) -> list[bytes]:
    """Encode data into (k+m) shards using the C library.

    Args:
        ctx: Initialized context.
        data: Input data. Length must be ctx.mpackets * ctx.shard_size bytes.

    Returns:
        List of (k+m) shards, each ctx.shard_size bytes. First k are data, last m are parity.
    """
    k = ctx.mpackets
    m = ctx.rpackets
    ss = ctx.shard_size
    expected_len = k * ss

    if len(data) != expected_len:
        raise ValueError(f"Data length {len(data)} != k*shard_size ({k}*{ss}={expected_len})")

    lib = CauchyRSLib.get()

    # Convert data bytes -> uint32 message array
    # The C library expects message as mlen uint32 words
    # Message layout: mpackets packets * (plen words per packet, no index)
    msg_words = ctx.mlen
    msg_arr = (ctypes.c_uint32 * msg_words)()

    # Fill message array from data bytes (little-endian uint32)
    # data is laid out as k contiguous shards of shard_size bytes
    # Each shard = plen uint32 words
    for i in range(k):
        shard_bytes = data[i * ss : (i + 1) * ss]
        for w in range(ctx.plen):
            offset = w * 4
            word_val = struct.unpack_from("<I", shard_bytes, offset)[0]
            msg_arr[i * ctx.plen + w] = word_val

    # Allocate packets array: npackets * plentot uint32 words
    pkt_arr = (ctypes.c_uint32 * (ctx.plentot * (k + m)))()

    # Encode
    lib.lib.rs_encode(ctypes.byref(ctx._ctx), msg_arr, pkt_arr)

    # Extract shards from packets (skip the index word at position 0 of each packet)
    shards: list[bytes] = []
    for i in range(k + m):
        pkt_start = i * ctx.plentot
        shard_words = []
        for w in range(ctx.plen):
            shard_words.append(pkt_arr[pkt_start + 1 + w])
        shard_bytes = struct.pack(f"<{ctx.plen}I", *shard_words)
        shards.append(shard_bytes)

    return shards


def cauchy_rs_decode(ctx: CauchyRSContext, shards: list[bytes | None], lost: list[int]) -> bytes:
    """Recover original data from shards with erasures.

    Args:
        ctx: Initialized context.
        shards: List of (k+m) items. Available shards are bytes, lost shards are None.
        lost: Indices of lost shards.

    Returns:
        Reconstructed original data (k * shard_size bytes).
    """
    k = ctx.mpackets
    m = ctx.rpackets
    total = k + m

    if len(lost) > m:
        raise ValueError(
            f"Cannot recover: {len(lost)} shards lost, only {m} parity available"
        )

    lib = CauchyRSLib.get()

    # Build received packets array for rs_decode
    # Only include packets that are available (not None)
    rec_packets_list: list[tuple[int, bytes]] = []  # (original_index, shard_bytes)
    for i, shard in enumerate(shards):
        if shard is not None:
            rec_packets_list.append((i, shard))

    nrec = len(rec_packets_list)
    if nrec < k:
        raise ValueError(
            f"Cannot recover: need {k} packets, only {nrec} received"
        )

    # Build rec_packets: each packet is plentot uint32 words [index, payload...]
    rec_arr = (ctypes.c_uint32 * (ctx.plentot * nrec))()
    for pkt_idx, (orig_idx, shard_bytes) in enumerate(rec_packets_list):
        base = pkt_idx * ctx.plentot
        rec_arr[base] = ctypes.c_uint32(orig_idx)  # index word
        # Parse shard_bytes into plen uint32 words
        for w in range(ctx.plen):
            word_val = struct.unpack_from("<I", shard_bytes, w * 4)[0]
            rec_arr[base + 1 + w] = word_val

    # Decode
    nrec_c = ctypes.c_int(nrec)
    msg_arr = (ctypes.c_uint32 * ctx.mlen)()

    ret = lib.lib.rs_decode(ctypes.byref(ctx._ctx), rec_arr, ctypes.byref(nrec_c), msg_arr)
    if ret != 0:
        raise RuntimeError(f"rs_decode failed with code {ret}")

    # Convert message to bytes
    result = bytearray()
    for i in range(k):
        for w in range(ctx.plen):
            result.extend(struct.pack("<I", msg_arr[i * ctx.plen + w]))

    return bytes(result)
