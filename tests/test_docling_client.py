"""Tests for DoclingClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._docling_client import DoclingClient

DOCLING_BASE = "http://docling:5001"


@pytest.fixture
def client() -> DoclingClient:
    return DoclingClient(
        http_client=httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0),
        vlm_api_url=None,
        vlm_api_key=None,
        vlm_model="gpt-4o",
    )


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_standard_convert(respx_mock: respx.MockRouter, client: DoclingClient) -> None:
    task_id = "task-001"
    respx_mock.post("/v1/convert/file/async").mock(
        return_value=httpx.Response(200, json={"task_id": task_id})
    )
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(
        return_value=httpx.Response(200, json={"task_status": "success"})
    )
    respx_mock.get(f"/v1/result/{task_id}").mock(
        return_value=httpx.Response(
            200, json={"document": {"md_content": "# Paper Title\n\nContent here."}}
        )
    )
    result = await client.convert(b"%PDF-1.4 fake", "paper.pdf", use_vlm=False, poll_interval=0.0)
    assert result == "# Paper Title\n\nContent here."


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_convert_polls_until_success(
    respx_mock: respx.MockRouter, client: DoclingClient
) -> None:
    task_id = "task-002"
    respx_mock.post("/v1/convert/file/async").mock(
        return_value=httpx.Response(200, json={"task_id": task_id})
    )
    call_count = 0

    def _status_side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(200, json={"task_status": "pending"})
        return httpx.Response(200, json={"task_status": "success"})

    respx_mock.get(f"/v1/status/poll/{task_id}").mock(side_effect=_status_side_effect)
    respx_mock.get(f"/v1/result/{task_id}").mock(
        return_value=httpx.Response(200, json={"document": {"md_content": "# Done"}})
    )
    result = await client.convert(b"pdf", "test.pdf", use_vlm=False, poll_interval=0.0)
    assert result == "# Done"
    assert call_count == 3


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_convert_task_failure(
    respx_mock: respx.MockRouter, client: DoclingClient
) -> None:
    task_id = "task-003"
    respx_mock.post("/v1/convert/file/async").mock(
        return_value=httpx.Response(200, json={"task_id": task_id})
    )
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(
        return_value=httpx.Response(200, json={"task_status": "failure", "error_message": "Bad PDF"})
    )
    with pytest.raises(RuntimeError, match="failed"):
        await client.convert(b"bad", "bad.pdf", use_vlm=False, poll_interval=0.0)
