import os

from scholar_mcp.config import ProjectConfig


def test_defaults(monkeypatch):
    monkeypatch.delenv("SCHOLAR_MCP_S2_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_DOCLING_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_MODEL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_CACHE_DIR", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_READ_ONLY", raising=False)
    cfg = ProjectConfig.from_env()
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
    cfg = ProjectConfig.from_env()
    assert cfg.s2_api_key == "test-key"
    assert cfg.docling_url == "http://docling:5001"
    assert cfg.vlm_api_url == "http://litellm:4000"
    assert cfg.vlm_api_key == "vlm-key"
    assert cfg.vlm_model == "gpt-4o-mini"
    assert str(cfg.cache_dir) == "/tmp/scholar-test"


def test_read_only_false_values(monkeypatch):
    for falsy in ("0", "false", "False", "FALSE", "no", "No", "off", "n"):
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", falsy)
        assert ProjectConfig.from_env().read_only is False, (
            f"expected False for {falsy!r}"
        )


def test_read_only_true_values(monkeypatch):
    for truthy in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", truthy)
        assert ProjectConfig.from_env().read_only is True, (
            f"expected True for {truthy!r}"
        )


def test_epo_keys_default_none(monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("SCHOLAR_MCP_"):
            monkeypatch.delenv(key, raising=False)
    config = ProjectConfig.from_env()
    assert config.epo_consumer_key is None
    assert config.epo_consumer_secret is None


def test_epo_keys_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "test-secret")
    config = ProjectConfig.from_env()
    assert config.epo_consumer_key == "test-key"
    assert config.epo_consumer_secret == "test-secret"


def test_epo_configured_both_set(monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "key")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "secret")
    config = ProjectConfig.from_env()
    assert config.epo_configured is True


def test_epo_configured_partial(monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "key")
    for key in list(os.environ):
        if key == "SCHOLAR_MCP_EPO_CONSUMER_SECRET":
            monkeypatch.delenv(key, raising=False)
    config = ProjectConfig.from_env()
    assert config.epo_configured is False


def test_github_token_read_from_env(monkeypatch):
    """github_token is populated from SCHOLAR_GITHUB_TOKEN."""
    monkeypatch.setenv("SCHOLAR_GITHUB_TOKEN", "ghp_abc123")
    config = ProjectConfig.from_env()
    assert config.github_token == "ghp_abc123"


def test_github_token_defaults_to_none(monkeypatch):
    """github_token is None when env var unset."""
    monkeypatch.delenv("SCHOLAR_GITHUB_TOKEN", raising=False)
    config = ProjectConfig.from_env()
    assert config.github_token is None


def test_access_links_read_from_env(monkeypatch):
    """SCHOLAR_MCP_ACCESS_LINKS is read verbatim; unset means off."""
    monkeypatch.delenv("SCHOLAR_MCP_ACCESS_LINKS", raising=False)
    assert ProjectConfig.from_env().access_links is None
    raw = '[{"label": "Library", "template": "https://r.example/link?{openurl}"}]'
    monkeypatch.setenv("SCHOLAR_MCP_ACCESS_LINKS", raw)
    assert ProjectConfig.from_env().access_links == raw


def test_invalid_access_links_refuse_startup():
    """A malformed template list is a configuration error naming the variable."""
    import pytest
    from fastmcp_pvl_core import ConfigurationError

    with pytest.raises(ConfigurationError, match="SCHOLAR_MCP_ACCESS_LINKS"):
        ProjectConfig(access_links='[{"label": "x", "template": "https://r/{isbn}"}]')


def test_transfer_config_reads_env(monkeypatch):
    """The transfer settings behind upload links come from SCHOLAR_MCP_TRANSFER_*."""
    monkeypatch.setenv("SCHOLAR_MCP_TRANSFER_MAX_UPLOAD_BYTES", "1024")
    assert ProjectConfig.from_env().transfer.max_upload_bytes == 1024
