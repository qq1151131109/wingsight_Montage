from __future__ import annotations

from tools.base_tool import BaseTool, ToolResult, ToolStatus
from tools.video.video_selector import VideoSelector


class LocalPathVideoProvider(BaseTool):
    name = "local_path_video_provider"
    capability = "video_generation"
    provider = "local_path"
    capabilities = ["image_to_video"]
    supports = {"image_to_video": True}
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "operation": {"type": "string"},
            "image_path": {"type": "string"},
            "image_url": {"type": "string"},
        },
    }

    def execute(self, inputs):
        return ToolResult(success=True, data={"received": inputs})


class ReferencePathVideoProvider(BaseTool):
    name = "reference_path_video_provider"
    capability = "video_generation"
    provider = "reference_path"
    capabilities = ["image_to_video"]
    supports = {"image_to_video": True}
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "operation": {"type": "string"},
            "reference_image_path": {"type": "string"},
        },
    }

    def execute(self, inputs):
        return ToolResult(success=True, data={"received": inputs})


def test_video_selector_maps_reference_image_path_to_image_path(monkeypatch):
    provider = LocalPathVideoProvider()
    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    monkeypatch.setattr(provider, "get_status", lambda: ToolStatus.AVAILABLE)

    result = selector.execute(
        {
            "prompt": "animate it",
            "operation": "image_to_video",
            "preferred_provider": "local_path",
            "reference_image_path": "/tmp/ref.png",
        }
    )

    assert result.success
    assert result.data["received"]["image_path"] == "/tmp/ref.png"


def test_video_selector_keeps_reference_image_path_when_provider_accepts_it(monkeypatch):
    provider = ReferencePathVideoProvider()
    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    monkeypatch.setattr(provider, "get_status", lambda: ToolStatus.AVAILABLE)

    result = selector.execute(
        {
            "prompt": "animate it",
            "operation": "image_to_video",
            "preferred_provider": "reference_path",
            "reference_image_path": "/tmp/ref.png",
        }
    )

    assert result.success
    assert result.data["received"]["reference_image_path"] == "/tmp/ref.png"
