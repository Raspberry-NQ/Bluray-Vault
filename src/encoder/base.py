"""Erasure coding engine — abstract interfaces and implementations.

The encoder module provides a unified interface for erasure coding operations.
Concrete implementations delegate to the C++ core engine (future) or a
pure-Python reference implementation.

Algorithm reference: Cauchy-RS-FEC/ (ICSI TR-95-048)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CodeSpec:
    """Specification for an erasure code instance."""
    data_shards: int       # k — number of data shards
    parity_shards: int     # m — number of parity shards
    shard_size: int        # bytes per shard
    gf_degree: int = 8     # GF(2^w), w=8 for intra-disc, w=16 for inter-disc

    @property
    def total_shards(self) -> int:
        return self.data_shards + self.parity_shards

    @property
    def max_loss(self) -> int:
        return self.parity_shards

    @property
    def overhead_ratio(self) -> float:
        return self.parity_shards / self.data_shards


class ErasureCodec(ABC):
    """Abstract base class for erasure codecs."""

    def __init__(self, spec: CodeSpec) -> None:
        self.spec = spec

    @abstractmethod
    def encode(self, data: bytes) -> list[bytes]:
        """Encode data into k data shards + m parity shards.

        Args:
            data: Input data, must be exactly k * shard_size bytes.

        Returns:
            List of (k + m) shards, each shard_size bytes.
            First k shards are data, last m are parity.
        """
        ...

    @abstractmethod
    def decode(self, shards: list[bytes | None], lost: list[int]) -> bytes:
        """Recover original data from shards with erasures.

        Args:
            shards: List of (k + m) items. Available shards are bytes,
                    lost shards are None.
            lost: Indices of lost shards (must be <= m).

        Returns:
            Reconstructed original data.

        Raises:
            ValueError: If too many shards are lost to recover.
        """
        ...


class CauchyRSCore(ErasureCodec):
    """Cauchy Reed-Solomon codec — primary intra-disc erasure code.

    Uses Cauchy matrix construction for guaranteed invertibility.
    Encoding maps GF multiply operations to XOR schedules for speed.
    Currently a placeholder; will delegate to C++ core or ctypes wrapper
    around the Cauchy-RS-FEC C implementation.
    """

    def encode(self, data: bytes) -> list[bytes]:
        k, m, ss = self.spec.data_shards, self.spec.parity_shards, self.spec.shard_size
        if len(data) != k * ss:
            raise ValueError(f"Data length {len(data)} != k*shard_size ({k}*{ss})")

        # Split into data shards
        data_shards = [data[i * ss : (i + 1) * ss] for i in range(k)]

        # TODO: Implement Cauchy encoding via C++ core or ctypes
        # Reference: Cauchy-RS-FEC/rs_code.c rs_encode()
        # For now, return data shards with zeroed parity placeholders
        parity_shards = [bytes(ss) for _ in range(m)]
        return data_shards + parity_shards

    def decode(self, shards: list[bytes | None], lost: list[int]) -> bytes:
        if len(lost) > self.spec.parity_shards:
            raise ValueError(
                f"Cannot recover: {len(lost)} shards lost, "
                f"but only {self.spec.parity_shards} parity shards available"
            )

        # TODO: Implement Cauchy decoding via C++ core or ctypes
        # Reference: Cauchy-RS-FEC/rs_code.c rs_decode()
        k = self.spec.data_shards
        ss = self.spec.shard_size
        recovered = bytearray(k * ss)
        return bytes(recovered)


class VandermondeRSCore(ErasureCodec):
    """Vandermonde Reed-Solomon codec — inter-disc erasure code.

    Uses Vandermonde matrix construction over GF(2^16) for cross-disc
    parity generation. Suitable for smaller stripe counts across discs.
    """

    def encode(self, data: bytes) -> list[bytes]:
        k, m, ss = self.spec.data_shards, self.spec.parity_shards, self.spec.shard_size
        if len(data) != k * ss:
            raise ValueError(f"Data length {len(data)} != k*shard_size ({k}*{ss})")

        data_shards = [data[i * ss : (i + 1) * ss] for i in range(k)]

        # TODO: Implement Vandermonde RS encoding
        parity_shards = [bytes(ss) for _ in range(m)]
        return data_shards + parity_shards

    def decode(self, shards: list[bytes | None], lost: list[int]) -> bytes:
        if len(lost) > self.spec.parity_shards:
            raise ValueError(
                f"Cannot recover: {len(lost)} shards lost > parity {self.spec.parity_shards}"
            )

        # TODO: Implement Vandermonde RS decoding (Gaussian elimination)
        k = self.spec.data_shards
        ss = self.spec.shard_size
        return bytes(k * ss)


class LRCCore(ErasureCodec):
    """Locally Repairable Code — hybrid local + global parity.

    Reduces I/O for partial damage: local groups allow repair reading
    only a subset of shards instead of all.
    """

    def __init__(self, spec: CodeSpec, local_groups: int = 2) -> None:
        super().__init__(spec)
        self.local_groups = local_groups

    def encode(self, data: bytes) -> list[bytes]:
        k, m, ss = self.spec.data_shards, self.spec.parity_shards, self.spec.shard_size
        if len(data) != k * ss:
            raise ValueError(f"Data length {len(data)} != k*shard_size ({k}*{ss})")

        data_shards = [data[i * ss : (i + 1) * ss] for i in range(k)]

        # TODO: Implement LRC encoding (local parity + global parity)
        parity_shards = [bytes(ss) for _ in range(m)]
        return data_shards + parity_shards

    def decode(self, shards: list[bytes | None], lost: list[int]) -> bytes:
        if len(lost) > self.spec.parity_shards:
            raise ValueError(
                f"Cannot recover: {len(lost)} shards lost > parity {self.spec.parity_shards}"
            )

        # TODO: Implement LRC decoding (local-first, then global)
        k = self.spec.data_shards
        ss = self.spec.shard_size
        return bytes(k * ss)


def create_codec(spec: CodeSpec, algorithm: str = "cauchy_rs") -> ErasureCodec:
    """Factory: create an erasure codec by algorithm name."""
    codecs = {
        "cauchy_rs": CauchyRSCore,
        "vandermonde_rs": VandermondeRSCore,
        "lrc": LRCCore,
    }
    if algorithm not in codecs:
        raise ValueError(f"Unknown algorithm: {algorithm}. Choose from {list(codecs)}")
    cls = codecs[algorithm]
    if algorithm == "lrc":
        return cls(spec, local_groups=2)
    return cls(spec)
