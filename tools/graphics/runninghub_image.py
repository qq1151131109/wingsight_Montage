"""RunningHub RHArt image-to-image generation."""

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


class RunningHubImage(BaseTool):
    name = "runninghub_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
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

    capabilities = ["edit_image", "image_to_image", "style_transfer"]
    supports = {
        "image_edit": True,
        "style_transfer": True,
        "reference_image": True,
        "multiple_reference_images": True,
        "aspect_ratio": True,
        "resolution": True,
        "text_to_image": True,
        "model_aliases": ["nano banana", "nano banana v2"],
    }
    best_for = [
        "Nano Banana v2 image generation/editing via RunningHub",
        "image-to-image style transfer through RunningHub standard models",
        "multi-reference image transformation with up to 10 input images",
        "Chinese prompt workflows and RH-hosted ComfyUI model access",
    ]
    not_good_for = ["text-to-image without a source image", "offline generation"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 20000},
            "generation_mode": {
                "type": "string",
                "enum": ["edit"],
                "default": "edit",
            },
            "model": {
                "type": "string",
                "enum": ["rhart-image-n-g31-flash"],
                "default": "rhart-image-n-g31-flash",
                "description": "RunningHub model id for Nano Banana v2 image generation/editing.",
            },
            "image_url": {"type": "string", "description": "Single source image URL"},
            "image_path": {"type": "string", "description": "Single local source image path; uploaded to RunningHub"},
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "Source image URLs, max 10 images, 30 MB each",
            },
            "imageUrls": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "RunningHub-native alias for image_urls",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "Local source images; uploaded to RunningHub",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": [
                    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
                    "5:4", "4:5", "21:9", "1:4", "4:1", "1:8", "8:1",
                ],
                "default": "1:1",
            },
            "aspectRatio": {
                "type": "string",
                "enum": [
                    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
                    "5:4", "4:5", "21:9", "1:4", "4:1", "1:8", "8:1",
                ],
                "description": "RunningHub-native alias for aspect_ratio",
            },
            "resolution": {
                "type": "string",
                "enum": ["1k", "2k", "4k"],
                "default": "1k",
            },
            "webhook_url": {"type": "string"},
            "webhookUrl": {"type": "string", "description": "RunningHub-native alias for webhook_url"},
            "output_path": {"type": "string"},
            "poll_interval_seconds": {"type": "integer", "minimum": 2, "default": 5},
            "timeout_seconds": {"type": "integer", "minimum": 30, "default": 900},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=200, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "model", "aspect_ratio", "resolution"]
    side_effects = [
        "uploads local input images to RunningHub when image_path/image_paths are provided",
        "writes image file(s) to output_path",
        "calls RunningHub OpenAPI",
    ]
    user_visible_verification = ["Inspect output image for edit fidelity and visual quality"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if get_runninghub_api_key() else ToolStatus.UNAVAILABLE

    @staticmethod
    def _count_inputs(inputs: dict[str, Any]) -> int:
        count = 0
        if inputs.get("image_url") or inputs.get("image_path"):
            count += 1
        count += len(inputs.get("image_urls") or [])
        count += len(inputs.get("imageUrls") or [])
        count += len(inputs.get("image_paths") or [])
        return count

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # RunningHub bills via wallet/RH coins and does not expose fixed USD rates here.
        return 0.0

    def _build_payload(self, inputs: dict[str, Any], client: RunningHubClient) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prompt": inputs["prompt"],
            "resolution": inputs.get("resolution", "1k"),
        }
        aspect_ratio = inputs.get("aspect_ratio") or inputs.get("aspectRatio")
        webhook_url = inputs.get("webhook_url") or inputs.get("webhookUrl")
        if aspect_ratio:
            payload["aspectRatio"] = aspect_ratio
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        image_urls = collect_media_urls(
            client,
            url_keys=["image_url", "image_urls", "imageUrls"],
            path_keys=["image_path", "image_paths"],
            inputs=inputs,
        )
        if image_urls:
            if len(image_urls) > 10:
                raise ValueError(f"RunningHub image-to-image accepts at most 10 images; got {len(image_urls)}")
            payload["imageUrls"] = image_urls
        return payload

    @staticmethod
    def _output_paths(output_path: str | None, results: list[dict[str, Any]]) -> list[Path]:
        paths: list[Path] = []
        for idx, item in enumerate(results):
            output_type = str(item.get("outputType") or "png").lstrip(".")
            url = str(item.get("url") or "")
            if output_path and len(results) == 1:
                paths.append(output_path_for_url("runninghub_image", output_path, url, output_type))
                continue
            if output_path:
                base = Path(output_path)
                stem = base.with_suffix("") if base.suffix else base
                paths.append(stem.parent / f"{stem.name}_{idx + 1}.{output_type}")
            else:
                paths.append(Path(f"runninghub_image_{idx + 1}.{output_type}"))
        return paths

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = get_runninghub_api_key()
        if not api_key:
            return ToolResult(success=False, error="RUNNINGHUB_API_KEY not set. " + self.install_instructions)

        start = time.time()
        client = RunningHubClient(api_key)
        model = inputs.get("model", "rhart-image-n-g31-flash")

        try:
            payload = self._build_payload(inputs, client)
            endpoint = f"{model}/image-to-image" if payload.get("imageUrls") else f"{model}/text-to-image"
            submitted = client.submit(endpoint, payload)
            task_id = submitted.get("taskId")
            if not task_id:
                return ToolResult(success=False, error=f"RunningHub submit response missing taskId: {submitted}")

            final = client.wait_for_task(
                str(task_id),
                poll_interval_seconds=int(inputs.get("poll_interval_seconds", 5)),
                timeout_seconds=int(inputs.get("timeout_seconds", 900)),
            )
            results = final.get("results") or []
            downloadable = [item for item in results if item.get("url")]
            if not downloadable:
                return ToolResult(success=False, error=f"RunningHub returned no downloadable image results: {final}")

            output_paths = self._output_paths(inputs.get("output_path"), downloadable)
            artifacts: list[str] = []
            for item, output_path in zip(downloadable, output_paths):
                client.download(str(item["url"]), output_path)
                artifacts.append(str(output_path))

        except Exception as e:
            return ToolResult(success=False, error=f"RunningHub image generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "runninghub",
                "model": model,
                "prompt": inputs["prompt"],
                "generation_mode": "edit" if final.get("results") and payload.get("imageUrls") else "generate",
                "operation": "image_to_image" if payload.get("imageUrls") else "text_to_image",
                "task_id": str(task_id),
                "status": final.get("status"),
                "output": artifacts[0],
                "outputs": artifacts,
                "remote_results": results,
                "usage": final.get("usage"),
            },
            artifacts=artifacts,
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
