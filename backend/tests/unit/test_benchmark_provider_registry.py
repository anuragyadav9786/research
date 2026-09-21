"""Unit tests for get_provider — which Benchmark.provider values resolve
to a working client, given the current Settings.benchmark_nse_provider_enabled
value (true by default — see config.py's docstring for why it's safe to
ship enabled-but-unverified)."""
from data_pipeline.sources.benchmarks.nse import NSEProvider
from data_pipeline.sources.benchmarks.registry import get_provider


def test_nse_is_enabled_by_default():
    provider = get_provider("NSE")
    assert isinstance(provider, NSEProvider)


def test_unimplemented_providers_return_none():
    assert get_provider("BSE") is None
    assert get_provider("CRISIL") is None
    assert get_provider("MSCI") is None


def test_no_provider_set_returns_none():
    assert get_provider(None) is None


def test_unknown_provider_name_returns_none():
    assert get_provider("SOME_UNKNOWN_PROVIDER") is None


def test_nse_disabled_via_settings_returns_none(monkeypatch):
    import data_pipeline.sources.benchmarks.registry as registry_module
    from app.core.config import Settings

    monkeypatch.setattr(registry_module, "get_settings", lambda: Settings(benchmark_nse_provider_enabled=False))
    assert registry_module.get_provider("NSE") is None
