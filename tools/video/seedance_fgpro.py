"""Seedance 2.0 video generation via FGPro API router."""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


DEFAULT_TASKS_URL = "https://api-router.fgpro.cn/api/v3/contents/generations/tasks"
DEFAULT_FAST_MODEL = "doubao-seedance-2-0-fast-260128"
DEFAULT_STANDARD_MODEL = "doubao-seedance-2-0-pro-260215"


class SeedanceFGPro(BaseTool):
    name = "seedance_fgpro"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "seedance"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set FGPRO_SEEDANCE_API_KEY to your FGPro Seedance relay key.\n"
        f"Optional: set FGPRO_SEEDANCE_TASKS_URL, default is {DEFAULT_TASKS_URL}"
    )
    agent_skills = ["seedance-2-0", "ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video", "reference_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "multiple_reference_images": True,
        "reference_image": True,
        "local_image_base64": True,
        "native_audio": True,
        "cinematic_quality": True,
        "camera_direction": True,
        "lip_sync": True,
        "multi_shot": True,
        "aspect_ratio": True,
        "seed": True,
    }
    best_for = [
        "Seedance 2.0 through the configured FGPro relay",
        "cinematic text-to-video and image/reference-conditioned video",
        "native synchronized audio, multi-shot prompts, and camera-directed clips",
    ]
    not_good_for = [
        "offline generation",
        "direct reference image/video uploads containing real human faces",
    ]
    fallback_tools = ["seedance_replicate", "seedance_video", "runninghub_video", "kling_video"]
    quality_score = 0.95

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
                "default": "text_to_video",
            },
            "model": {"type": "string"},
            "model_variant": {
                "type": "string",
                "enum": ["standard", "fast"],
                "default": "fast",
            },
            "duration": {
                "type": "string",
                "enum": ["auto", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"],
                "default": "5",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["auto", "adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
                "default": "16:9",
            },
            "resolution": {"type": "string", "enum": ["480p", "720p"], "default": "720p"},
            "generate_audio": {"type": "boolean", "default": True},
            "camera_fixed": {"type": "boolean", "default": False},
            "return_last_frame": {"type": "boolean", "default": False},
            "execution_expires_after": {"type": "integer"},
            "watermark": {"type": "boolean", "default": False},
            "image_url": {"type": "string"},
            "image_path": {"type": "string"},
            "end_image_url": {"type": "string"},
            "end_image_path": {"type": "string"},
            "reference_image_url": {"type": "string"},
            "reference_image_urls": {"type": "array", "items": {"type": "string"}},
            "reference_image_paths": {"type": "array", "items": {"type": "string"}},
            "video_url": {"type": "string"},
            "reference_video_urls": {"type": "array", "items": {"type": "string"}},
            "reference_audio_urls": {"type": "array", "items": {"type": "string"}},
            "subject_type": {"type": "string"},
            "contains_real_person_reference": {
                "type": "boolean",
                "default": False,
                "description": "Set true when image/video references contain real human faces; Seedance 2.0 may reject these.",
            },
            "tools": {"type": "array"},
            "seed": {"type": "integer"},
            "poll_interval_seconds": {"type": "integer", "default": 5},
            "timeout_seconds": {"type": "integer", "default": 600},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "model", "model_variant", "operation", "duration", "seed"]
    side_effects = ["writes video file to output_path", "calls FGPro Seedance relay API"]
    user_visible_verification = [
        "Watch generated clip for motion coherence, audio sync, and visual quality"
    ]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FGPRO_SEEDANCE_API_KEY")

    def _tasks_url(self) -> str:
        return os.environ.get("FGPRO_SEEDANCE_TASKS_URL", DEFAULT_TASKS_URL).rstrip("/")

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if self._get_api_key() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        duration = inputs.get("duration", "5")
        secs = 5 if duration == "auto" else int(duration)
        rate = 0.24 if inputs.get("model_variant", "fast") == "fast" else 0.30
        return round(rate * secs, 2)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 60.0 if inputs.get("model_variant", "fast") == "fast" else 120.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="FGPRO_SEEDANCE_API_KEY not set. " + self.install_instructions,
            )
        if inputs.get("contains_real_person_reference") and self._has_external_reference(inputs):
            return ToolResult(
                success=False,
                error=(
                    "Seedance 2.0 does not support direct reference image/video uploads that contain real human faces. "
                    "Use text-to-video, a non-real-person reference, or a Seedance-generated source video from the same account for edit/extension."
                ),
            )

        import requests

        start = time.time()
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = self._build_payload(inputs)

        try:
            submit = requests.post(self._tasks_url(), headers=headers, json=payload, timeout=(10, 60))
            submit.raise_for_status()
            submitted = submit.json()
            task_id = self._extract_task_id(submitted)
            if not task_id:
                return ToolResult(
                    success=False,
                    error=f"FGPro Seedance submit response missing task id: {self._safe_shape(submitted)}",
                )

            final = self._poll_task(
                requests_module=requests,
                headers=headers,
                task_id=task_id,
                interval_seconds=int(inputs.get("poll_interval_seconds", 5)),
                timeout_seconds=int(inputs.get("timeout_seconds", 600)),
            )
            video_url = self._extract_video_url(final)
            if not video_url:
                return ToolResult(
                    success=False,
                    error=f"FGPro Seedance completed task returned no video URL: {self._safe_shape(final)}",
                )

            download = requests.get(video_url, timeout=(10, 180))
            download.raise_for_status()

            output_path = Path(inputs.get("output_path", "seedance_fgpro_output.mp4"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(download.content)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"FGPro Seedance video generation failed: {self._safe_error(exc)}",
            )

        from tools.video._shared import probe_output

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "seedance",
                "gateway": "fgpro",
                "model": payload.get("model"),
                "task_id": task_id,
                "prompt": inputs["prompt"],
                "operation": inputs.get("operation", "text_to_video"),
                "variant": inputs.get("model_variant", "fast"),
                "aspect_ratio": payload.get("ratio"),
                "resolution": payload.get("resolution"),
                "duration": payload.get("duration"),
                "generate_audio": payload.get("generate_audio", True),
                "seed": final.get("seed") or submitted.get("seed") or inputs.get("seed"),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            seed=final.get("seed") or submitted.get("seed") or inputs.get("seed"),
            model=str(payload.get("model")),
        )

    def _build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        variant = inputs.get("model_variant", "fast")
        model = (
            inputs.get("model")
            or os.environ.get("FGPRO_SEEDANCE_MODEL")
            or (DEFAULT_FAST_MODEL if variant == "fast" else DEFAULT_STANDARD_MODEL)
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": inputs["prompt"]}]
        subject_type = inputs.get("subject_type")

        image_items: list[dict[str, str]] = []
        if inputs.get("image_url"):
            image_items.append({
                "url": inputs["image_url"],
                "role": "first_frame" if inputs.get("operation") == "image_to_video" else "reference_image",
            })
        if inputs.get("image_path"):
            image_items.append({
                "url": self._image_path_to_data_url(inputs["image_path"]),
                "role": "first_frame" if inputs.get("operation") == "image_to_video" else "reference_image",
            })
        if inputs.get("end_image_url"):
            image_items.append({"url": inputs["end_image_url"], "role": "last_frame"})
        if inputs.get("end_image_path"):
            image_items.append({"url": self._image_path_to_data_url(inputs["end_image_path"]), "role": "last_frame"})
        if inputs.get("reference_image_url"):
            image_items.append({"url": inputs["reference_image_url"], "role": "reference_image"})
        for url in inputs.get("reference_image_urls") or []:
            image_items.append({"url": url, "role": "reference_image"})
        for path in inputs.get("reference_image_paths") or []:
            image_items.append({"url": self._image_path_to_data_url(path), "role": "reference_image"})

        seen_image_urls: set[str] = set()
        for image in image_items:
            url = image["url"]
            if url in seen_image_urls:
                continue
            seen_image_urls.add(url)
            item: dict[str, Any] = {
                "type": "image_url",
                "image_url": {"url": url},
                "role": image["role"],
            }
            if subject_type:
                item["subject_type"] = subject_type
            content.append(item)

        video_urls = []
        if inputs.get("video_url"):
            video_urls.append(inputs["video_url"])
        video_urls.extend(inputs.get("reference_video_urls") or [])
        for url in self._dedupe_urls(video_urls):
            content.append({"type": "video_url", "video_url": {"url": url}})
        for url in self._dedupe_urls(inputs.get("reference_audio_urls") or []):
            content.append({"type": "audio_url", "audio_url": {"url": url}})

        duration = inputs.get("duration", "5")
        payload: dict[str, Any] = {
            "model": model,
            "content": content,
            "generate_audio": bool(inputs.get("generate_audio", True)),
            "camera_fixed": bool(inputs.get("camera_fixed", False)),
            "return_last_frame": bool(inputs.get("return_last_frame", False)),
            "resolution": inputs.get("resolution", "720p"),
            "ratio": self._normalize_ratio(inputs.get("aspect_ratio", "16:9")),
            "watermark": bool(inputs.get("watermark", False)),
            "duration": -1 if duration == "auto" else int(duration),
            "seed": int(inputs["seed"]) if inputs.get("seed") is not None else -1,
        }
        if inputs.get("execution_expires_after") is not None:
            payload["execution_expires_after"] = int(inputs["execution_expires_after"])
        if inputs.get("tools"):
            payload["tools"] = inputs["tools"]
        return payload

    def _poll_task(
        self,
        *,
        requests_module: Any,
        headers: dict[str, str],
        task_id: str,
        interval_seconds: int,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        task_url = f"{self._tasks_url()}/{task_id}"
        while time.time() < deadline:
            response = requests_module.get(task_url, headers=headers, timeout=(10, 60))
            response.raise_for_status()
            data = response.json()
            status = str(
                self._get_nested(data, "status") or self._get_nested(data, "data.status") or ""
            ).lower()
            if status in {"succeeded", "success", "completed", "complete", "done"}:
                return data
            if status in {"failed", "error", "cancelled", "canceled", "expired"}:
                raise RuntimeError(f"task {task_id} {status}: {data.get('error') or data.get('message')}")
            time.sleep(max(1, interval_seconds))
        raise TimeoutError(f"task {task_id} timed out after {timeout_seconds} seconds")

    @staticmethod
    def _extract_task_id(data: dict[str, Any]) -> str | None:
        for path in ("id", "task_id", "taskId", "data.id", "data.task_id", "data.taskId"):
            value = SeedanceFGPro._get_nested(data, path)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _extract_video_url(data: dict[str, Any]) -> str | None:
        candidates = (
            "content.video_url",
            "data.content.video_url",
            "data.video.url",
            "data.output.video_url",
            "data.result.video_url",
            "data.result.video.url",
            "data.url",
            "video.url",
            "video_url",
            "url",
        )
        for path in candidates:
            value = SeedanceFGPro._get_nested(data, path)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        output = SeedanceFGPro._get_nested(data, "output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return item
                if isinstance(item, dict):
                    url = SeedanceFGPro._extract_video_url(item)
                    if url:
                        return url
        video_data = SeedanceFGPro._get_nested(data, "data")
        if isinstance(video_data, list):
            for item in video_data:
                if isinstance(item, dict):
                    url = item.get("url")
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        return url
        return None

    @staticmethod
    def _get_nested(data: dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _dedupe_urls(urls: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                deduped.append(url)
        return deduped

    @staticmethod
    def _image_path_to_data_url(path_value: str) -> str:
        path = Path(path_value)
        if not path.is_file():
            raise FileNotFoundError(f"Image reference not found: {path}")
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff", "image/gif"}:
            mime_type = "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _has_external_reference(inputs: dict[str, Any]) -> bool:
        reference_keys = (
            "image_url",
            "image_path",
            "end_image_url",
            "end_image_path",
            "reference_image_url",
            "reference_image_urls",
            "reference_image_paths",
            "video_url",
            "reference_video_urls",
        )
        return any(bool(inputs.get(key)) for key in reference_keys)

    @staticmethod
    def _normalize_ratio(ratio: str) -> str:
        return "adaptive" if ratio == "auto" else ratio

    @staticmethod
    def _safe_shape(data: Any) -> str:
        if not isinstance(data, dict):
            return repr(data)[:500]
        scrubbed = {
            key: ("<omitted>" if key.lower() in {"authorization", "api_key", "token"} else value)
            for key, value in data.items()
        }
        return repr(scrubbed)[:500]

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = str(exc)
        api_key = os.environ.get("FGPRO_SEEDANCE_API_KEY")
        if api_key:
            text = text.replace(api_key, "<redacted>")
        return text
