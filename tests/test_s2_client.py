import httpx
import pytest

from scholar_mcp._s2_client import FIELD_SETS, S2Client

S2_BASE = "https://api.semanticscholar.org/graph/v1"


@pytest.fixture
def client():
    return S2Client(api_key=None, delay=0.0)


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper(respx_mock, client):
    respx_mock.get("/paper/abc123").mock(
        return_value=httpx.Response(
            200, json={"paperId": "abc123", "title": "Test Paper", "year": 2024}
        )
    )
    result = await client.get_paper("abc123")
    assert result["paperId"] == "abc123"
    assert result["title"] == "Test Paper"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_not_found(respx_mock, client):
    respx_mock.get("/paper/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_paper("missing")


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers(respx_mock, client):
    respx_mock.get("/paper/search").mock(
        return_value=httpx.Response(
            200, json={"data": [{"paperId": "p1", "title": "Result 1"}], "total": 1}
        )
    )
    result = await client.search_papers(
        "machine learning", fields="compact", limit=10, offset=0
    )
    assert result["total"] == 1
    assert result["data"][0]["paperId"] == "p1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations(respx_mock, client):
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200, json={"data": [{"citingPaper": {"paperId": "c1", "title": "Citer"}}]}
        )
    )
    result = await client.get_citations("p1", fields="compact", limit=10, offset=0)
    assert result["data"][0]["citingPaper"]["paperId"] == "c1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_batch_resolve(respx_mock, client):
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200, json=[{"paperId": "p1", "title": "Paper 1"}, None]
        )
    )
    result = await client.batch_resolve(["p1", "unknown"], fields="standard")
    assert result[0]["paperId"] == "p1"
    assert result[1] is None


def test_field_sets_exist():
    for preset in ("compact", "standard", "full"):
        assert preset in FIELD_SETS
        assert "title" in FIELD_SETS[preset]
