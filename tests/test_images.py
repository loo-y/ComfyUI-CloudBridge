import unittest
from io import BytesIO

import torch
from PIL import Image

from cloudbridge.utils.images import (
    collect_image_frames,
    encode_image_frame,
    image_bytes_to_tensor,
    stack_result_images,
)


def make_image_bytes(size=(8, 8), color=(20, 40, 60)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class ImageUtilityTests(unittest.TestCase):
    def test_collects_frames_in_socket_and_batch_order(self):
        first_batch = torch.zeros((2, 4, 4, 3))
        second_batch = torch.ones((1, 4, 4, 3))

        frames = collect_image_frames([first_batch, None, second_batch])

        self.assertEqual(len(frames), 3)
        self.assertEqual(float(frames[0].mean()), 0.0)
        self.assertEqual(float(frames[2].mean()), 1.0)

    def test_rejects_more_than_fourteen_expanded_frames(self):
        with self.assertRaisesRegex(ValueError, "at most 14"):
            collect_image_frames([torch.zeros((15, 2, 2, 3))])

    def test_prefers_png_when_it_fits(self):
        encoded = encode_image_frame(torch.zeros((8, 8, 3)), "input")

        self.assertEqual(encoded.filename, "input.png")
        self.assertEqual(encoded.mime_type, "image/png")

    def test_falls_back_to_jpeg_to_meet_limit(self):
        generator = torch.Generator().manual_seed(42)
        frame = torch.rand((64, 64, 3), generator=generator)

        encoded = encode_image_frame(frame, "input", max_bytes=10_000)

        self.assertEqual(encoded.mime_type, "image/jpeg")
        self.assertLessEqual(len(encoded.content), 10_000)

    def test_decodes_and_stacks_equal_sized_results(self):
        output = stack_result_images(
            [make_image_bytes(color=(255, 0, 0)), make_image_bytes(color=(0, 255, 0))]
        )

        self.assertEqual(tuple(output.shape), (2, 8, 8, 3))

    def test_rejects_mixed_result_dimensions(self):
        with self.assertRaisesRegex(ValueError, "different dimensions"):
            stack_result_images([make_image_bytes((8, 8)), make_image_bytes((6, 8))])

    def test_rejects_invalid_download_content(self):
        with self.assertRaisesRegex(ValueError, "not a readable image"):
            image_bytes_to_tensor(b"not an image")


if __name__ == "__main__":
    unittest.main()
