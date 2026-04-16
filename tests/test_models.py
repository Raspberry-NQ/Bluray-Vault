"""Tests for data models and volume operations."""

import json
import tempfile
from pathlib import Path

import pytest

from src.models.schemas import (
    ErasureConfig,
    RedundancyLevel,
    VolumeMeta,
    VolumeStatus,
)
from src.core.volume import init_volume, load_volume, save_volume_meta, VAULT_DIR


class TestErasureConfig:
    def test_default_config(self):
        cfg = ErasureConfig()
        assert cfg.redundancy == RedundancyLevel.HIGH
        assert cfg.data_stripes == 16
        assert cfg.parity_stripes == 8
        assert cfg.chunk_size == 1048576
        assert cfg.gf_degree == 8


class TestVolumeMeta:
    def test_auto_generated_fields(self):
        meta = VolumeMeta(name="test")
        assert meta.volume_id
        assert meta.status == VolumeStatus.INITIALIZED
        assert len(meta.discs) == 0


class TestVolumeOps:
    def test_init_and_load(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        meta = init_volume("myvol", redundancy=RedundancyLevel.HIGH)
        assert meta.name == "myvol"
        assert meta.erasure.data_stripes == 16
        assert meta.erasure.parity_stripes == 8

        loaded = load_volume("myvol")
        assert loaded.volume_id == meta.volume_id
        assert loaded.erasure.redundancy == RedundancyLevel.HIGH

    def test_init_duplicate_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        init_volume("dup")
        with pytest.raises(FileExistsError):
            init_volume("dup")

    def test_load_nonexistent_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError):
            load_volume("nope")
