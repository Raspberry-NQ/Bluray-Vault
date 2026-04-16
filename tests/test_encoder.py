"""Tests for erasure codec interfaces."""

import pytest

from src.encoder.base import (
    CauchyRSCore,
    CodeSpec,
    LRCCore,
    VandermondeRSCore,
    create_codec,
)


class TestCodeSpec:
    def test_total_shards(self):
        spec = CodeSpec(data_shards=16, parity_shards=8, shard_size=1024)
        assert spec.total_shards == 24

    def test_max_loss(self):
        spec = CodeSpec(data_shards=16, parity_shards=8, shard_size=1024)
        assert spec.max_loss == 8

    def test_overhead_ratio(self):
        spec = CodeSpec(data_shards=16, parity_shards=8, shard_size=1024)
        assert spec.overhead_ratio == 0.5


class TestCodecFactory:
    def test_create_cauchy(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        codec = create_codec(spec, "cauchy_rs")
        assert isinstance(codec, CauchyRSCore)

    def test_create_vandermonde(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        codec = create_codec(spec, "vandermonde_rs")
        assert isinstance(codec, VandermondeRSCore)

    def test_create_lrc(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        codec = create_codec(spec, "lrc")
        assert isinstance(codec, LRCCore)

    def test_unknown_algorithm_raises(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        with pytest.raises(ValueError):
            create_codec(spec, "unknown")


class TestCauchyRSPlaceholder:
    def test_encode_returns_correct_count(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        codec = CauchyRSCore(spec)
        data = bytes(spec.data_shards * spec.shard_size)
        shards = codec.encode(data)
        assert len(shards) == spec.total_shards

    def test_encode_wrong_size_raises(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        codec = CauchyRSCore(spec)
        with pytest.raises(ValueError):
            codec.encode(b"short")

    def test_decode_too_many_lost_raises(self):
        spec = CodeSpec(data_shards=4, parity_shards=2, shard_size=64)
        codec = CauchyRSCore(spec)
        shards = [None] * 3 + [bytes(64)] * 3
        with pytest.raises(ValueError, match="Cannot recover"):
            codec.decode(shards, lost=[0, 1, 2])
