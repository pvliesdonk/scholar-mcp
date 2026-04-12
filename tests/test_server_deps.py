"""Tests for _server_deps module."""

from scholar_mcp._enrichment import EnrichmentPipeline
from scholar_mcp._server_deps import _build_enrichment_pipeline


def test_build_enrichment_pipeline() -> None:
    """Pipeline builder returns an EnrichmentPipeline with registered enrichers."""
    pipeline = _build_enrichment_pipeline()
    assert isinstance(pipeline, EnrichmentPipeline)
    # Should have enrichers in at least two phases (0 and 1)
    assert len(pipeline._phases) >= 2
