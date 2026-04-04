"""docling-serve client for PDF-to-Markdown conversion."""

from __future__ import annotations

import asyncio
import base64
import html
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_FORMULA_PROMPT = (
    "Extract the mathematical formula from this image. "
    "Output ONLY the LaTeX expression, nothing else. "
    "Use display math format. Include the equation number in \\tag{} if visible."
)

_PICTURE_PROMPT = (
    "Describe this figure from an academic paper. Include: "
    "axis labels and units, all data series with labels, key trends and intersections, "
    "and the figure caption if visible. Use LaTeX ($...$) for mathematical notation. "
    "Be precise and concise."
)


@dataclass
class DoclingClient:
    """Client for docling-serve async conversion API.

    Args:
        http_client: httpx.AsyncClient pointed at docling-serve.
        vlm_api_url: OpenAI-compatible VLM endpoint URL, or None.
        vlm_api_key: API key for the VLM endpoint.
        vlm_model: Model name for VLM enrichment.
    """

    http_client: httpx.AsyncClient
    vlm_api_url: str | None
    vlm_api_key: str | None
    vlm_model: str

    @property
    def vlm_available(self) -> bool:
        """True if VLM enrichment is configured."""
        return bool(self.vlm_api_url and self.vlm_api_key)

    async def _poll(
        self, task_id: str, poll_interval: float = 3.0, max_polls: int = 200
    ) -> str:
        """Poll task until complete, then fetch and return markdown.

        Args:
            task_id: Task ID returned by the async submit endpoint.
            poll_interval: Seconds between status polls.
            max_polls: Maximum poll attempts before giving up (default 200,
                ~10 min at 3 s/poll).

        Returns:
            Markdown string.

        Raises:
            RuntimeError: If task fails, returns no markdown, or times out.
        """
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval)
            r = await self.http_client.get(f"/v1/status/poll/{task_id}", timeout=30)
            r.raise_for_status()
            status_data = r.json()
            status = status_data.get("task_status") or status_data.get("status", "")

            if status.lower() in ("failure", "error"):
                raise RuntimeError(
                    f"docling task {task_id} failed: "
                    f"{status_data.get('error_message', status_data)}"
                )

            if status.lower() == "success":
                result_r = await self.http_client.get(
                    f"/v1/result/{task_id}", timeout=30
                )
                result_r.raise_for_status()
                result = result_r.json()
                doc = result.get("document") or {}
                md = (
                    doc.get("md_content")
                    or doc.get("markdown")
                    or result.get("md_content")
                    or ""
                )
                if not md:
                    raise RuntimeError(f"docling task {task_id} returned no markdown")
                return md

            logger.debug("docling_polling task_id=%s status=%s", task_id, status)
        raise RuntimeError(f"docling task {task_id} timed out after {max_polls} polls")

    async def convert(
        self,
        pdf_bytes: bytes,
        filename: str,
        *,
        use_vlm: bool = False,
        poll_interval: float = 3.0,
    ) -> str:
        """Convert a PDF to Markdown using docling-serve.

        Chooses the VLM-enhanced path if ``use_vlm=True`` and VLM is
        configured; otherwise falls back to the standard path automatically.

        Args:
            pdf_bytes: Raw PDF bytes.
            filename: Filename hint for docling.
            use_vlm: Request VLM enrichment for formulas and figures.
            poll_interval: Seconds between status poll requests.

        Returns:
            Markdown string.
        """
        if use_vlm and self.vlm_available:
            return await self._convert_vlm(pdf_bytes, filename, poll_interval)
        return await self._convert_standard(pdf_bytes, filename, poll_interval)

    async def _convert_standard(
        self, pdf_bytes: bytes, filename: str, poll_interval: float
    ) -> str:
        r = await self.http_client.post(
            "/v1/convert/file/async",
            files={"files": (filename, pdf_bytes, "application/pdf")},
            data={
                "to_formats": "md",
                "do_ocr": "true",
                "image_export_mode": "placeholder",
            },
            timeout=60,
        )
        r.raise_for_status()
        task_id = r.json().get("task_id") or r.json().get("id")
        if not task_id:
            raise RuntimeError(f"docling did not return task_id: {r.text[:200]}")
        return await self._poll(task_id, poll_interval)

    async def _convert_vlm(
        self, pdf_bytes: bytes, filename: str, poll_interval: float
    ) -> str:
        b64 = base64.b64encode(pdf_bytes).decode("ascii")
        payload = {
            "options": {
                "to_formats": ["md"],
                "pipeline": "standard",
                "do_ocr": True,
                "image_export_mode": "placeholder",
                "pdf_backend": "dlparse_v4",
                "do_formula_enrichment": True,
                "do_code_enrichment": True,
                "code_formula_custom_config": {
                    "engine_options": {
                        "engine_type": "api_openai",
                        "url": f"{self.vlm_api_url}/chat/completions",
                        "headers": {"Authorization": f"Bearer {self.vlm_api_key}"},
                        "params": {"model": self.vlm_model, "max_tokens": 1024},
                        "timeout": 120,
                        "concurrency": 2,
                    },
                    "model_spec": {
                        "name": f"{self.vlm_model}-formula",
                        "default_repo_id": self.vlm_model,
                        "prompt": _FORMULA_PROMPT,
                        "response_format": "markdown",
                        "max_new_tokens": 1024,
                    },
                    "scale": 2.0,
                    "extract_code": True,
                    "extract_formulas": True,
                },
                "do_picture_description": True,
                "do_picture_classification": True,
                "picture_description_custom_config": {
                    "engine_options": {
                        "engine_type": "api_openai",
                        "url": f"{self.vlm_api_url}/chat/completions",
                        "headers": {"Authorization": f"Bearer {self.vlm_api_key}"},
                        "params": {"model": self.vlm_model, "max_tokens": 512},
                        "timeout": 120,
                        "concurrency": 2,
                    },
                    "model_spec": {
                        "name": f"{self.vlm_model}-figures",
                        "default_repo_id": self.vlm_model,
                        "prompt": _PICTURE_PROMPT,
                        "response_format": "markdown",
                        "max_new_tokens": 512,
                    },
                    "scale": 2.0,
                    "batch_size": 1,
                    "prompt": _PICTURE_PROMPT,
                    "generation_config": {"max_new_tokens": 512, "do_sample": False},
                },
            },
            "sources": [{"kind": "file", "base64_string": b64, "filename": filename}],
        }
        r = await self.http_client.post(
            "/v1/convert/source/async", json=payload, timeout=60
        )
        r.raise_for_status()
        task_id = r.json().get("task_id") or r.json().get("id")
        if not task_id:
            raise RuntimeError(f"docling VLM did not return task_id: {r.text[:200]}")
        md = await self._poll(task_id, poll_interval)
        return html.unescape(md)
