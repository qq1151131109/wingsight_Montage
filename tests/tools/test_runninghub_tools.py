from __future__ import annotations

import os

from tools.base_tool import ToolStatus
from tools.graphics.runninghub_image import RunningHubImage
from tools.runninghub_client import RunningHubClient, collect_media_urls, normalize_runninghub_status
from tools.tool_registry import ToolRegistry
from tools.video.runninghub_video import RunningHubVideo


def test_runninghub_tools_are_discoverable(monkeypatch):
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    registry = ToolRegistry()
    registry.discover()

    assert "runninghub_image" in registry.list_all()
    assert "runninghub_video" in registry.list_all()
    assert registry.get("runninghub_image").get_status() == ToolStatus.UNAVAILABLE
    assert registry.get("runninghub_video").get_status() == ToolStatus.UNAVAILABLE


def test_runninghub_tools_become_available_with_api_key(monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")

    assert RunningHubImage().get_status() == ToolStatus.AVAILABLE
    assert RunningHubVideo().get_status() == ToolStatus.AVAILABLE


def test_runninghub_image_payload_maps_snake_case_inputs(monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    tool = RunningHubImage()
    payload = tool._build_payload(
        {
            "prompt": "style transfer",
            "image_url": "https://example.com/a.png",
            "image_urls": ["https://example.com/b.png"],
            "aspect_ratio": "9:16",
            "resolution": "2k",
            "webhook_url": "https://example.com/webhook",
        },
        RunningHubClient("test-key"),
    )

    assert payload == {
        "imageUrls": ["https://example.com/a.png", "https://example.com/b.png"],
        "prompt": "style transfer",
        "resolution": "2k",
        "aspectRatio": "9:16",
        "webhookUrl": "https://example.com/webhook",
    }


def test_runninghub_image_payload_accepts_native_field_names(monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    tool = RunningHubImage()
    payload = tool._build_payload(
        {
            "prompt": "style transfer",
            "imageUrls": ["https://example.com/a.png"],
            "aspectRatio": "9:16",
            "resolution": "1k",
            "webhookUrl": "https://example.com/webhook",
        },
        RunningHubClient("test-key"),
    )

    assert payload == {
        "imageUrls": ["https://example.com/a.png"],
        "prompt": "style transfer",
        "resolution": "1k",
        "aspectRatio": "9:16",
        "webhookUrl": "https://example.com/webhook",
    }


def test_runninghub_video_payloads_for_t2v_and_i2v(monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    tool = RunningHubVideo()
    client = RunningHubClient("test-key")

    t2v = tool._build_payload(
        {
            "prompt": "a cinematic forest",
            "operation": "text_to_video",
            "aspect_ratio": "2:3",
            "resolution": "480p",
            "duration": 6,
        },
        client,
    )
    assert "imageUrls" not in t2v
    assert t2v["aspectRatio"] == "2:3"

    i2v = tool._build_payload(
        {
            "prompt": "make the character turn",
            "operation": "image_to_video",
            "reference_image_url": "https://example.com/ref.jpg",
            "aspect_ratio": "2:3",
            "resolution": "480p",
            "duration": 6,
        },
        client,
    )
    assert i2v["imageUrls"] == ["https://example.com/ref.jpg"]


def test_runninghub_video_payload_accepts_native_field_names(monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    tool = RunningHubVideo()
    client = RunningHubClient("test-key")

    payload = tool._build_payload(
        {
            "prompt": "a cinematic forest",
            "operation": "image_to_video",
            "aspectRatio": "2:3",
            "imageUrls": ["https://example.com/ref.jpg"],
            "resolution": "480p",
            "duration": 6,
            "webhookUrl": "https://example.com/webhook",
        },
        client,
    )

    assert payload == {
        "prompt": "a cinematic forest",
        "aspectRatio": "2:3",
        "resolution": "480p",
        "duration": 6,
        "webhookUrl": "https://example.com/webhook",
        "imageUrls": ["https://example.com/ref.jpg"],
    }


def test_collect_media_urls_uploads_local_paths(tmp_path):
    class FakeClient:
        def upload_file(self, file_path: str) -> str:
            return f"https://uploaded.example/{os.path.basename(file_path)}"

    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"fake")

    urls = collect_media_urls(
        FakeClient(),
        url_keys=["image_url", "image_urls"],
        path_keys=["image_path"],
        inputs={
            "image_url": "https://example.com/a.png",
            "image_urls": ["https://example.com/b.png"],
            "image_path": str(image_path),
        },
    )

    assert urls == [
        "https://example.com/a.png",
        "https://example.com/b.png",
        "https://uploaded.example/input.png",
    ]


def test_runninghub_status_normalization():
    assert normalize_runninghub_status(" success ") == "SUCCESS"
