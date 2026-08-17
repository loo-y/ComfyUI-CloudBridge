from __future__ import annotations

import json
import os
import uuid
from typing import Any

from ..providers.kie import KieClient
from ..utils.images import (
    collect_image_frames,
    encode_image_frame,
    stack_result_images,
)


ASPECT_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9")
QUALITIES = ("basic", "high", "ultra")
OUTPUT_FORMATS = ("png", "jpeg")


def resolve_api_key(node_api_key: str | None) -> str:
    environment_key = os.environ.get("KIE_API_KEY", "").strip()
    if environment_key:
        return environment_key
    widget_key = (node_api_key or "").strip()
    if widget_key:
        return widget_key
    raise ValueError(
        "Missing Kie API key. Set the KIE_API_KEY environment variable or enter "
        "an API key in the node. Environment variables are safer because node "
        "values are saved in workflow JSON."
    )


class KieSeedream5LiteImageToImage:
    DESCRIPTION = (
        "Edit up to 14 images with Kie.ai Seedream 5 Lite. Cloud generation may "
        "consume Kie credits."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        optional_images = {f"image_{index}": ("IMAGE",) for index in range(2, 15)}
        return {
            "required": {
                "image_1": ("IMAGE",),
                "prompt": (
                    "STRING",
                    {
                        "default": "Describe how the input image should be edited.",
                        "multiline": True,
                    },
                ),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "aspect_ratio": (ASPECT_RATIOS, {"default": "1:1"}),
                "quality": (QUALITIES, {"default": "basic"}),
                "output_format": (OUTPUT_FORMATS, {"default": "png"}),
                "nsfw_checker": ("BOOLEAN", {"default": False}),
                "regenerate": ("BOOLEAN", {"default": False}),
            },
            "optional": optional_images,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "task_id", "result_urls")
    FUNCTION = "generate"
    CATEGORY = "CloudBridge/Kie.ai"

    @classmethod
    def IS_CHANGED(cls, regenerate: bool = False, **_kwargs: Any) -> float | int:
        return float("NaN") if regenerate else 0

    def generate(
        self,
        image_1,
        prompt: str,
        api_key: str,
        aspect_ratio: str,
        quality: str,
        output_format: str,
        nsfw_checker: bool,
        regenerate: bool,
        **optional_images,
    ):
        del regenerate  # Used by ComfyUI's cache fingerprint through IS_CHANGED.
        prompt = (prompt or "").strip()
        if not 3 <= len(prompt) <= 3000:
            raise ValueError("Prompt length must be between 3 and 3000 characters.")

        key = resolve_api_key(api_key)
        ordered_inputs = [image_1] + [
            optional_images.get(f"image_{index}") for index in range(2, 15)
        ]
        frames = collect_image_frames(ordered_inputs, max_images=14)

        client = KieClient(key)
        uploaded_urls: list[str] = []
        request_token = uuid.uuid4().hex
        for index, frame in enumerate(frames, start=1):
            encoded = encode_image_frame(
                frame,
                basename=f"cloudbridge-{request_token}-{index:02d}",
            )
            uploaded_urls.append(client.upload_image(encoded))

        task_id = client.create_seedream_task(
            prompt=prompt,
            image_urls=uploaded_urls,
            aspect_ratio=aspect_ratio,
            quality=quality,
            output_format=output_format,
            nsfw_checker=nsfw_checker,
        )
        task_result = client.wait_for_task(task_id)
        result_contents = [
            client.download_image(url) for url in task_result.result_urls
        ]
        output_image = stack_result_images(result_contents)
        return (
            output_image,
            task_result.task_id,
            json.dumps(task_result.result_urls, ensure_ascii=False),
        )
