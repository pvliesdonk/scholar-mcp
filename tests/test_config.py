import os

from scholar_mcp.config import load_config


def test_defaults(monkeypatch):
    monkeypatch.delenv("SCHOLAR_MCP_S2_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_DOCLING_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_MODEL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_CACHE_DIR", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_READ_ONLY", raising=False)
    cfg = load_config()
    assert cfg.s2_api_key is None
    assert cfg.docling_url is None
    assert cfg.vlm_api_url is None
    assert cfg.vlm_api_key is None
    assert cfg.vlm_model == "gpt-4o"
    assert str(cfg.cache_dir) == "/data/scholar-mcp"
    assert cfg.read_only is True


def test_env_vars_loaded(monkeypatch):
    monkeypatch.setenv("SCHOLAR_MCP_S2_API_KEY", "test-key")
    monkeypatch.setenv("SCHOLAR_MCP_DOCLING_URL", "http://docling:5001")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_API_URL", "http://litellm:4000")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_API_KEY", "vlm-key")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", "/tmp/scholar-test")
    cfg = load_config()
    assert cfg.s2_api_key == "test-key"
    assert cfg.docling_url == "http://docling:5001"
    assert cfg.vlm_api_url == "http://litellm:4000"
    assert cfg.vlm_api_key == "vlm-key"
    assert cfg.vlm_model == "gpt-4o-mini"
    assert str(cfg.cache_dir) == "/tmp/scholar-test"


def test_read_only_false_values(monkeypatch):
    for falsy in ("0", "false", "False", "FALSE", "no", "No", "off", "n"):
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", falsy)
        assert load_config().read_only is False, f"expected False for {falsy!r}"


def test_read_only_true_values(monkeypatch):
    for truthy in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", truthy)
        assert load_config().read_only is True, f"expected True for {truthy!r}"


def test_epo_keys_default_none(monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("SCHOLAR_MCP_"):
            monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.epo_consumer_key is None
    assert config.epo_consumer_secret is None


def test_epo_keys_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "test-secret")
    config = load_config()
    assert config.epo_consumer_key == "test-key"
    assert config.epo_consumer_secret == "test-secret"


def test_epo_configured_both_set(monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "key")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "secret")
    config = load_config()
    assert config.epo_configured is True


def test_epo_configured_partial(monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "key")
    for key in list(os.environ):
        if key == "SCHOLAR_MCP_EPO_CONSUMER_SECRET":
            monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.epo_configured is False
