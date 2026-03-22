"""Tests for config.py (P4.5)."""

import pytest


def test_config_loads():
    from src.core.config import cfg

    assert cfg is not None


def test_config_defaults():
    from src.core.config import cfg

    assert cfg.cache_ttl > 0
    assert cfg.cache_dir is not None
    assert isinstance(cfg.use_disk_cache, bool)


def test_factor_weights_sum_to_one():
    from src.core.config import cfg

    weights = cfg.factor_weights
    total = sum(weights.values())
    assert total == pytest.approx(1.0, abs=0.01)


def test_screener_universe_is_list():
    from src.core.config import cfg

    universe = cfg.screener_universe
    assert isinstance(universe, list)
    assert len(universe) > 0


def test_sector_etfs_structure():
    from src.core.config import cfg

    etfs = cfg.sector_etfs
    assert isinstance(etfs, list)
    assert len(etfs) > 0
    for etf in etfs:
        assert "ticker" in etf
        assert "name" in etf


def test_chart_height_positive():
    from src.core.config import cfg

    assert cfg.chart_height > 0


def test_log_level_valid():
    from src.core.config import cfg
    import logging

    assert hasattr(logging, cfg.log_level)


def test_deep_merge():
    from src.core.config import _deep_merge

    base = {"a": 1, "b": {"x": 10, "y": 20}}
    override = {"b": {"x": 99}, "c": 3}
    result = _deep_merge(base, override)
    assert result["a"] == 1
    assert result["b"]["x"] == 99
    assert result["b"]["y"] == 20
    assert result["c"] == 3
