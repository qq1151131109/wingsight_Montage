from __future__ import annotations

from tools.video.seedance_fgpro import SeedanceFGPro
from tools.video.seedance_video import SeedanceVideo
from tools.video.video_selector import VideoSelector


def test_seedance_selector_uses_fgpro_when_fal_key_is_absent(monkeypatch):
    monkeypatch.setenv("FGPRO_SEEDANCE_API_KEY", "test-fgpro-key")
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FAL_AI_API_KEY", raising=False)

    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [SeedanceVideo(), SeedanceFGPro()])

    rankings = selector.execute(
        {
            "prompt": "cinematic smoke test",
            "operation": "rank",
            "preferred_provider": "seedance",
        }
    )

    seedance_rows = [
        item
        for item in rankings.data["rankings"]
        if item["tool_name"] in {"seedance_video", "seedance_fgpro"}
    ]

    assert seedance_rows[0]["tool_name"] == "seedance_fgpro"
    assert seedance_rows[0]["status"] == "ToolStatus.AVAILABLE"
    assert seedance_rows[1]["tool_name"] == "seedance_video"
    assert seedance_rows[1]["status"] == "ToolStatus.UNAVAILABLE"
