"""RunningHub RHArt text-to-video and image-to-video generation."""

from __future__ import annotations

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
from tools.runninghub_client import (
    RunningHubClient,
    collect_media_urls,
    get_runninghub_api_key,
    output_path_for_url,
)


class RunningHubVideo(BaseTool):
    name = "runninghub_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "runninghub"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set RUNNINGHUB_API_KEY to your RunningHub enterprise shared API key.\n"
        "  RunningHub standard model API docs use Authorization: Bearer ${RUNNINGHUB_API_KEY}"
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_image": True,
        "multiple_reference_images": True,
        "aspect_ratio": True,
        "duration": True,
        "resolution": True,
        "camera_direction": True,
    }
    best_for = [
        "RunningHub RHArt text-to-video and image-to-video standard models",
        "Chinese prompt workflows with 6-30 second clips",
        "720p or 480p generated video via RunningHub wallet billing",
    ]
    not_good_for = ["offline generation", "native synchronized audio guarantees"]
    fallback_tools = ["seedance_fgpro", "seedance_video", "kling_video", "minimax_video"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "minLength": 5, "maxLength": 20000},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model": {
                "type": "string",
                "enum": ["rhart-video-g"],
                "default": "rhart-video-g",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["2:3", "3:2", "1:1", "16:9", "9:16"],
                "default": "16:9",
            },
            "aspectRatio": {
                "type": "string",
                "enum": ["2:3", "3:2", "1:1", "16:9", "9:16"],
                "description": "RunningHub-native alias for aspect_ratio",
            },
            "resolution": {
                "type": "string",
                "enum": ["720p", "480p"],
                "default": "720p",
            },
            "duration": {
                "type": "integer",
                "minimum": 6,
                "maximum": 30,
                "default": 6,
            },
            "image_url": {"type": "string", "description": "Single source image URL for image_to_video"},
            "image_path": {"type": "string", "description": "Single local source image path; uploaded to RunningHub"},
            "reference_image_url": {"type": "string", "description": "Alias for image_url"},
            "reference_image_path": {"type": "string", "description": "Alias for image_path"},
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 7,
                "description": "Source image URLs for image_to_video, max 7 images, 10 MB each",
            },
            "imageUrls": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 7,
                "description": "RunningHub-native alias for reference_image_urls",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 7,
                "description": "Local source images; uploaded to RunningHub",
            },
            "webhook_url": {"type": "string"},
            "webhookUrl": {"type": "string", "description": "RunningHub-native alias for webhook_url"},
            "output_path": {"type": "string"},
            "poll_interval_seconds": {"type": "integer", "minimum": 2, "default": 5},
            "timeout_seconds": {"type": "integer", "minimum": 30, "default": 1200},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=800, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "operation", "model", "duration", "aspect_ratio", "resolution"]
    side_effects = [
        "uploads local input images to RunningHub when image_path/reference_image_path is provided",
        "writes video file to output_path",
        "calls RunningHub OpenAPI",
    ]
    user_visible_verification = ["Watch generated clip for motion coherence and prompt fidelity"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if get_runninghub_api_key() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # RunningHub bills via wallet/RH coins and does not expose fixed USD rates here.
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        duration = int(inputs.get("duration", 6))
        return 90.0 + duration * 10.0

    def _collect_image_urls(self, inputs: dict[str, Any], client: RunningHubClient) -> list[str]:
        image_urls = collect_media_urls(
            client,
            url_keys=["image_url", "reference_image_url", "reference_image_urls", "imageUrls"],
            path_keys=["image_path", "reference_image_path", "reference_image_paths"],
            inputs=inputs,
        )
        if len(image_urls) > 7:
            raise ValueError(f"RunningHub image-to-video accepts at most 7 images; got {len(image_urls)}")
        return image_urls

    def _build_payload(self, inputs: dict[str, Any], client: RunningHubClient) -> dict[str, Any]:
        operation = inputs.get("operation", "text_to_video")
        aspect_ratio = inputs.get("aspect_ratio") or inputs.get("aspectRatio") or "16:9"
        webhook_url = inputs.get("webhook_url") or inputs.get("webhookUrl")
        payload: dict[str, Any] = {
            "prompt": inputs["prompt"],
            "aspectRatio": aspect_ratio,
            "resolution": inputs.get("resolution", "720p"),
        }
        if inputs.get("duration") is not None:
            payload["duration"] = int(inputs.get("duration", 6))
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        if operation == "image_to_video":
            image_urls = self._collect_image_urls(inputs, client)
            if not image_urls:
                raise ValueError("RunningHub image-to-video requires image_url/image_path or reference_image_url/reference_image_path")
            payload["imageUrls"] = image_urls

        return payload

    @staticmethod
    def _output_paths(output_path: str | None, results: list[dict[str, Any]]) -> list[Path]:
        paths: list[Path] = []
        for idx, item in enumerate(results):
            output_type = str(item.get("outputType") or "mp4").lstrip(".")
            url = str(item.get("url") or "")
            if output_path and len(results) == 1:
                paths.append(output_path_for_url("runninghub_video", output_path, url, output_type))
                continue
            if output_path:
                base = Path(output_path)
                stem = base.with_suffix("") if base.suffix else base
                paths.append(stem.parent / f"{stem.name}_{idx + 1}.{output_type}")
            else:
                paths.append(Path(f"runninghub_video_{idx + 1}.{output_type}"))
        return paths

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = get_runninghub_api_key()
        if not api_key:
            return ToolResult(success=False, error="RUNNINGHUB_API_KEY not set. " + self.install_instructions)

        start = time.time()
        client = RunningHubClient(api_key)
        operation = inputs.get("operation", "text_to_video")
        model = inputs.get("model", "rhart-video-g")
        endpoint = f"{model}/{operation.replace('_', '-')}"

        try:
            payload = self._build_payload(inputs, client)
            submitted = client.submit(endpoint, payload)
            task_id = submitted.get("taskId")
            if not task_id:
                return ToolResult(success=False, error=f"RunningHub submit response missing taskId: {submitted}")

            final = client.wait_for_task(
                str(task_id),
                poll_interval_seconds=int(inputs.get("poll_interval_seconds", 5)),
                timeout_seconds=int(inputs.get("timeout_seconds", 1200)),
            )
            results = final.get("results") or []
            downloadable = [item for item in results if item.get("url")]
            if not downloadable:
                return ToolResult(success=False, error=f"RunningHub returned no downloadable video results: {final}")

            output_paths = self._output_paths(inputs.get("output_path"), downloadable)
            artifacts: list[str] = []
            for item, output_path in zip(downloadable, output_paths):
                client.download(str(item["url"]), output_path)
                artifacts.append(str(output_path))

        except Exception as e:
            return ToolResult(success=False, error=f"RunningHub video generation failed: {e}")

        try:
            from tools.video._shared import probe_output

            probed = probe_output(Path(artifacts[0]))
        except Exception:
            probed = {}

        return ToolResult(
            success=True,
            data={
                "provider": "runninghub",
                "model": model,
                "prompt": inputs["prompt"],
                "operation": operation,
                "task_id": str(task_id),
                "status": final.get("status"),
                "aspect_ratio": inputs.get("aspect_ratio") or inputs.get("aspectRatio") or "16:9",
                "resolution": inputs.get("resolution", "720p"),
                "duration": int(inputs.get("duration", 6)),
                "output": artifacts[0],
                "output_path": artifacts[0],
                "outputs": artifacts,
                "remote_results": results,
                "usage": final.get("usage"),
                "format": Path(artifacts[0]).suffix.lstrip(".") or "mp4",
                **probed,
            },
            artifacts=artifacts,
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
