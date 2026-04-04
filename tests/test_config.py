import os
import pytest
from scholar_mcp.config import ServerConfig, load_config

def test_defaults(monkeypatch):
    monkeypatch.delenv("SCHOLAR_MCP_S2_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_DOCLING_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_MODEL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_CACHE_DIR", raising=False)
    cfg = load_config()
    assert cfg.s2_api_key is None
    assert cfg.docling_url is None
    assert cfg.vlm_api_url is None
    assert cfg.vlm_api_key is None
    assert cfg.vlm_model == "gpt-4o"
    assert str(cfg.cache_dir) == "/data/scholar-mcp"

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
