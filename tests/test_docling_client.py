"""Tests for DoclingClient."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from scholar_mcp._docling_client import DoclingClient, parse_vlm_params

DOCLING_BASE = "http://docling:5001"


@pytest.fixture
def client() -> DoclingClient:
    return DoclingClient(
        http_client=httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0),
        vlm_api_url=None,
        vlm_api_key=None,
        vlm_model="gpt-4o",
    )


@pytest.mark.parametrize(
    "use_vlm,vlm_api_url,vlm_api_key,expected",
    [
        (False, None, None, None),
        (True, None, None, "vlm_api_url_not_configured"),
        (True, "http://vlm", None, "vlm_api_key_not_configured"),
        (True, "http://vlm", "key123", None),
    ],
)
def test_vlm_skip_reason(
    use_vlm: bool,
    vlm_api_url: str | None,
    vlm_api_key: str | None,
    expected: str | None,
) -> None:
    c = DoclingClient(
        http_client=httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0),
        vlm_api_url=vlm_api_url,
        vlm_api_key=vlm_api_key,
        vlm_model="gpt-4o",
    )
    assert c.vlm_skip_reason(use_vlm) == expected


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_standard_convert(
    respx_mock: respx.MockRouter, client: DoclingClient
) -> None:
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
    result = await client.convert(
        b"%PDF-1.4 fake", "paper.pdf", use_vlm=False, poll_interval=0.0
    )
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

    def _status_side_effect(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
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
        return_value=httpx.Response(
            200, json={"task_status": "failure", "error_message": "Bad PDF"}
        )
    )
    with pytest.raises(RuntimeError, match="failed"):
        await client.convert(b"bad", "bad.pdf", use_vlm=False, poll_interval=0.0)


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_vlm_convert_limits_tokens_with_max_completion_tokens(
    respx_mock: respx.MockRouter,
) -> None:
    """Every VLM engine sends max_completion_tokens and never max_tokens (#603).

    Current OpenAI models reject max_tokens; docling drops its own max_tokens
    only when the engine params carry max_completion_tokens.
    """
    client = DoclingClient(
        http_client=httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0),
        vlm_api_url="http://vlm",
        vlm_api_key="key123",
        vlm_model="gpt-6-luna",
    )
    task_id = "task-vlm"
    submit = respx_mock.post("/v1/convert/source/async").mock(
        return_value=httpx.Response(200, json={"task_id": task_id})
    )
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(
        return_value=httpx.Response(200, json={"task_status": "success"})
    )
    respx_mock.get(f"/v1/result/{task_id}").mock(
        return_value=httpx.Response(200, json={"document": {"md_content": "# T"}})
    )
    await client.convert(b"%PDF-1.4 fake", "paper.pdf", use_vlm=True, poll_interval=0.0)

    options = json.loads(submit.calls.last.request.content)["options"]
    engines = [
        options["code_formula_custom_config"]["engine_options"],
        options["picture_description_custom_config"]["engine_options"],
    ]
    for engine in engines:
        assert "max_tokens" not in engine["params"]
        assert engine["params"]["max_completion_tokens"] > 0
        assert engine["params"]["model"] == "gpt-6-luna"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, {}), ("", {}), ('{"temperature": 1}', {"temperature": 1})],
)
def test_parse_vlm_params(raw: str | None, expected: dict[str, object]) -> None:
    assert parse_vlm_params(raw) == expected


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]", '"text"'])
def test_parse_vlm_params_rejects_non_objects(raw: str) -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_vlm_params(raw)


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_vlm_convert_merges_operator_params(
    respx_mock: respx.MockRouter,
) -> None:
    """Operator VLM params override the defaults in every engine (#606)."""
    client = DoclingClient(
        http_client=httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0),
        vlm_api_url="http://vlm",
        vlm_api_key="key123",
        vlm_model="gpt-6-luna",
        vlm_params={"temperature": 1, "max_completion_tokens": 4096},
    )
    task_id = "task-params"
    submit = respx_mock.post("/v1/convert/source/async").mock(
        return_value=httpx.Response(200, json={"task_id": task_id})
    )
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(
        return_value=httpx.Response(200, json={"task_status": "success"})
    )
    respx_mock.get(f"/v1/result/{task_id}").mock(
        return_value=httpx.Response(200, json={"document": {"md_content": "# T"}})
    )
    await client.convert(b"%PDF-1.4 fake", "paper.pdf", use_vlm=True, poll_interval=0.0)

    options = json.loads(submit.calls.last.request.content)["options"]
    for key in ("code_formula_custom_config", "picture_description_custom_config"):
        params = options[key]["engine_options"]["params"]
        assert params == {
            "model": "gpt-6-luna",
            "max_completion_tokens": 4096,
            "temperature": 1,
        }
