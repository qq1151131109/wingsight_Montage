from __future__ import annotations

from tools.base_tool import BaseTool
from tools.graphics.image_selector import ImageSelector


class TextToImageProvider(BaseTool):
    name = "text_to_image_provider"
    capability = "image_generation"
    provider = "text"
    capabilities = ["text_to_image"]
    input_schema = {"type": "object", "properties": {"prompt": {"type": "string"}}}

    def execute(self, inputs):
        raise NotImplementedError


class EditOnlyProvider(BaseTool):
    name = "edit_only_provider"
    capability = "image_generation"
    provider = "edit"
    capabilities = ["edit_image", "image_to_image"]
    supports = {"image_edit": True}
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "image_urls": {"type": "array", "items": {"type": "string"}},
        },
    }

    def execute(self, inputs):
        raise NotImplementedError


def test_image_selector_excludes_edit_only_providers_for_text_generation():
    selector = ImageSelector()
    candidates = [TextToImageProvider(), EditOnlyProvider()]

    filtered = selector._filter_candidates({"prompt": "a mountain"}, candidates)

    assert [tool.name for tool in filtered] == ["text_to_image_provider"]


def test_image_selector_includes_edit_only_providers_for_edit_generation():
    selector = ImageSelector()
    candidates = [TextToImageProvider(), EditOnlyProvider()]

    filtered = selector._filter_candidates(
        {"prompt": "repaint this", "image_urls": ["https://example.com/ref.png"]},
        candidates,
    )

    assert [tool.name for tool in filtered] == ["edit_only_provider"]
