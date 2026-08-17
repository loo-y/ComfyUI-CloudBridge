from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Sequence

import numpy as np
import torch
from PIL import Image


MAX_INPUT_BYTES = 10_000_000
JPEG_QUALITIES = (95, 90, 85, 80, 75, 70, 60, 50)


@dataclass(frozen=True)
class EncodedImage:
    filename: str
    content: bytes
    mime_type: str


def iter_image_frames(image_tensor: torch.Tensor) -> Iterable[torch.Tensor]:
    """Yield individual BHWC image frames from a ComfyUI IMAGE tensor."""
    if image_tensor is None:
        return
    if not isinstance(image_tensor, torch.Tensor) or image_tensor.ndim != 4:
        raise ValueError("Each image input must be a ComfyUI IMAGE tensor in BHWC format.")
    if image_tensor.shape[-1] not in (1, 3, 4):
        raise ValueError("Image tensors must have 1, 3, or 4 channels.")
    for frame in image_tensor:
        yield frame


def collect_image_frames(
    image_inputs: Sequence[torch.Tensor | None], max_images: int = 14
) -> list[torch.Tensor]:
    frames: list[torch.Tensor] = []
    for image_tensor in image_inputs:
        if image_tensor is None:
            continue
        frames.extend(iter_image_frames(image_tensor))
        if len(frames) > max_images:
            raise ValueError(
                f"Kie Seedream 5 Lite accepts at most {max_images} input images; "
                f"received {len(frames)} after expanding IMAGE batches."
            )
    if not frames:
        raise ValueError("At least one input image is required.")
    return frames


def frame_to_pil(frame: torch.Tensor) -> Image.Image:
    array = frame.detach().cpu().float().numpy()
    array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
    channels = array.shape[-1]
    if channels == 1:
        array = np.repeat(array, 3, axis=-1)
    elif channels == 4:
        array = array[..., :3]
    return Image.fromarray(array, mode="RGB")


def encode_image_frame(
    frame: torch.Tensor,
    basename: str,
    max_bytes: int = MAX_INPUT_BYTES,
) -> EncodedImage:
    """Encode losslessly when possible, then fall back to JPEG under 10 MB."""
    image = frame_to_pil(frame)

    png_buffer = BytesIO()
    image.save(png_buffer, format="PNG", optimize=True)
    png_data = png_buffer.getvalue()
    if len(png_data) <= max_bytes:
        return EncodedImage(f"{basename}.png", png_data, "image/png")

    for quality in JPEG_QUALITIES:
        jpeg_buffer = BytesIO()
        image.save(
            jpeg_buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            subsampling=0,
        )
        jpeg_data = jpeg_buffer.getvalue()
        if len(jpeg_data) <= max_bytes:
            return EncodedImage(f"{basename}.jpg", jpeg_data, "image/jpeg")

    raise ValueError(
        "An input image remains larger than Kie's 10 MB limit after JPEG "
        "compression. Resize the image before connecting it to this node."
    )


def image_bytes_to_tensor(content: bytes) -> torch.Tensor:
    try:
        with Image.open(BytesIO(content)) as image:
            rgb = image.convert("RGB")
            array = np.asarray(rgb, dtype=np.float32) / 255.0
    except Exception as exc:
        raise ValueError("Kie returned data that is not a readable image.") from exc
    return torch.from_numpy(array.copy()).unsqueeze(0)


def stack_result_images(contents: Sequence[bytes]) -> torch.Tensor:
    if not contents:
        raise ValueError("Kie completed the task but returned no downloadable images.")
    tensors = [image_bytes_to_tensor(content) for content in contents]
    shapes = {tuple(tensor.shape[1:]) for tensor in tensors}
    if len(shapes) != 1:
        raise ValueError(
            "Kie returned images with different dimensions, so they cannot be "
            "combined into one ComfyUI IMAGE batch."
        )
    return torch.cat(tensors, dim=0)
