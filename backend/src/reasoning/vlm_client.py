"""
Production Vision-Language Model (VLM) Client.
Connects to hosted OpenAI-compatible multimodal endpoints (such as NVIDIA NIM,
OpenRouter, or hosted vLLM) to perform grounded visual QA with normalized 0-1000
bounding boxes, unit/metric extraction, and deterministic abstention.
"""

import base64
import ast
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Union
import httpx

from backend.src.schemas.contracts import (
    BoundingBox,
    CitationStatus,
    GroundedAnswer,
    VisualCitation,
)
from backend.src.reasoning.prompt_templates import SYSTEM_GROUNDED_QA_PROMPT, format_user_prompt
from backend.src.reasoning.grounding import GroundingEngine


class VLMClient:
    """
    Client for hosted Vision-Language Model inference with bounding-box grounding and abstention.
    Connects to hosted endpoints (NVIDIA NIM, OpenRouter, Together AI, or hosted vLLM).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        grounding_engine: Optional[GroundingEngine] = None,
        timeout_seconds: float = 45.0,
    ):
        self.base_url = (base_url or os.environ.get("VLM_BASE_URL", "https://integrate.api.nvidia.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("VLM_API_KEY", "")
        self.model_name = model_name or os.environ.get("VLM_MODEL_NAME", "nvidia/qwen2.5-vl-7b-instruct")
        self.grounding_engine = grounding_engine or GroundingEngine()
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def encode_image_base64(image_path: Union[str, Path], max_dim: int = 1400) -> str:
        """
        Encode image to base64 with optimal resolution for fast multimodal API transmission.
        Resizes transmission buffer to max_dim (preserving aspect ratio) to eliminate network timeouts,
        while all final visual evidence crops are cut from the master 300 DPI image.
        """
        import io
        from PIL import Image

        path = Path(image_path)
        with Image.open(path) as img:
            # Check if image exceeds transmission canvas
            if max(img.size) > max_dim:
                scale = max_dim / max(img.size)
                new_size = (int(img.width * scale), int(img.height * scale))
                resized = img.resize(new_size, Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                resized.convert("RGB").save(buf, format="JPEG", quality=88)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
            else:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=88)
                return base64.b64encode(buf.getvalue()).decode("utf-8")

    def answer_page_query(
        self,
        query: str,
        page_image_path: Union[str, Path],
        doc_id: str,
        page_number: int,
        pdf_path: Optional[Union[str, Path]] = None,
    ) -> GroundedAnswer:
        """
        Executes grounded QA against a single 300 DPI page image using the hosted VLM.
        Sends base64 image and query prompt, parses structured JSON, and crops visual evidence.
        """
        if not self.api_key:
            raise RuntimeError(
                "VLM_API_KEY is not configured. A valid hosted VLM API key is required to perform "
                "visual reasoning. Please set the VLM_API_KEY environment variable (e.g. from NVIDIA NIM "
                "at https://build.nvidia.com) or pass api_key to VLMClient."
            )

        start_time = time.perf_counter()
        img_path = Path(page_image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"Page image not found: {img_path}")

        # Encode 300 DPI image to base64
        b64_image = self.encode_image_base64(img_path)
        user_prompt = format_user_prompt(query, page_number)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_GROUNDED_QA_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                    ],
                },
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        content = None
        for attempt in range(1, 4):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                    if resp.status_code in [429, 502, 503, 504]:
                        time.sleep(attempt * 2.0)
                        continue
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"VLM API returned error HTTP {resp.status_code}: {resp.text}"
                        )

                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    break
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                time.sleep(attempt * 1.5)
        else:
            raise RuntimeError(f"VLM API call failed after 3 retry attempts: {last_error}")

        # Decode the first JSON object.  Do not use a greedy regex here: a
        # model can append an example or explanation containing another object.
        json_start = content.find("{")
        if json_start < 0:
            raise ValueError(f"Model failed to return valid JSON output: {content}")
        raw_json = content[json_start:]
        try:
            parsed, _ = json.JSONDecoder().raw_decode(raw_json)
        except json.JSONDecodeError as error:
            # Some OpenAI-compatible VLMs occasionally use Python-style quotes
            # despite the JSON-only instruction.  Accept only a literal mapping;
            # never evaluate arbitrary model output.
            try:
                parsed = ast.literal_eval(raw_json)
            except (ValueError, SyntaxError) as repair_error:
                raise ValueError("Model returned an invalid structured answer.") from repair_error
        if not isinstance(parsed, dict):
            raise ValueError("Model returned an invalid structured answer.")

        status_str = parsed.get("status", "abstain").lower()
        status = CitationStatus(status_str) if status_str in ["direct", "indirect", "abstain"] else CitationStatus.ABSTAIN

        citation = None
        raw_box = parsed.get("bounding_box_1000")
        box = None

        # 1. Native VLM Bounding Box (if model returned localized coordinates)
        if raw_box and len(raw_box) == 4:
            try:
                # Check if scale is 0..1 float or 0..1000 int
                if max(raw_box) <= 1.0 and any(v > 0 for v in raw_box):
                    scaled_box = [int(round(v * 1000)) for v in raw_box]
                else:
                    scaled_box = [int(round(float(v))) for v in raw_box]

                ymin, xmin, ymax, xmax = scaled_box
                # Ensure it's an actual region, not a whole-page bounding box
                if ymax > ymin and xmax > xmin and not (ymin <= 10 and xmin <= 10 and ymax >= 950 and xmax >= 950):
                    box = BoundingBox(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)
            except Exception:
                box = None

        # 2. PDFium Text-Span Localization (high precision sub-pixel localization)
        if box is None and pdf_path and status == CitationStatus.DIRECT:
            ans_text = parsed.get("answer") or ""
            box = self.grounding_engine.locate_text_span(pdf_path, page_number, ans_text)

        if status == CitationStatus.DIRECT and box:
            citation = self.grounding_engine.crop_evidence(
                img_path,
                box,
                doc_id,
                page_number=page_number,
                target_type=parsed.get("target_type", "table_cell"),
            )

        # Extract numeric value if model left it null
        num_val = parsed.get("numeric_value")
        if num_val is None and parsed.get("answer"):
            nums = re.findall(r"[-+]?\d*\.?\d+", parsed["answer"])
            if nums:
                try:
                    num_val = float(nums[0])
                except ValueError:
                    pass

        return GroundedAnswer(
            query=query,
            status=status,
            answer=parsed.get("answer"),
            numeric_value=num_val,
            unit=parsed.get("unit"),
            citation=citation,
            abstention_reason=parsed.get("abstention_reason"),
            latency_ms=(time.perf_counter() - start_time) * 1000.0,
            model_id=self.model_name,
        )
