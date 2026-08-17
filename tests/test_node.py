import importlib.util
import json
import os
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import torch
from PIL import Image

from cloudbridge.nodes.kie_seedream import (
    KieSeedream5LiteImageToImage,
    resolve_api_key,
)
from cloudbridge.providers.kie import KieTaskResult


def result_image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (120, 80, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


class NodeTests(unittest.TestCase):
    def test_environment_api_key_has_precedence(self):
        with patch.dict(os.environ, {"KIE_API_KEY": "environment-key"}):
            self.assertEqual(resolve_api_key("widget-key"), "environment-key")

    def test_widget_api_key_is_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_api_key("widget-key"), "widget-key")

    def test_missing_api_key_error_explains_secure_option(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "KIE_API_KEY"):
                resolve_api_key("")

    def test_node_exposes_fourteen_image_inputs(self):
        input_types = KieSeedream5LiteImageToImage.INPUT_TYPES()

        self.assertIn("image_1", input_types["required"])
        self.assertEqual(
            [name for name in input_types["optional"] if name.startswith("image_")],
            [f"image_{index}" for index in range(2, 15)],
        )

    def test_regenerate_controls_cache_fingerprint(self):
        self.assertEqual(KieSeedream5LiteImageToImage.IS_CHANGED(False), 0)
        self.assertNotEqual(
            KieSeedream5LiteImageToImage.IS_CHANGED(True),
            KieSeedream5LiteImageToImage.IS_CHANGED(True),
        )

    @patch("cloudbridge.nodes.kie_seedream.KieClient")
    def test_generation_returns_image_and_task_metadata(self, client_class):
        client = MagicMock()
        client.upload_image.return_value = "https://files.example/input.png"
        client.create_seedream_task.return_value = "task-1"
        client.wait_for_task.return_value = KieTaskResult(
            "task-1", ["https://result.example/image.png"]
        )
        client.download_image.return_value = result_image_bytes()
        client_class.return_value = client

        output, task_id, urls_json = KieSeedream5LiteImageToImage().generate(
            image_1=torch.zeros((1, 8, 8, 3)),
            prompt="Edit this image",
            api_key="widget-key",
            aspect_ratio="1:1",
            quality="basic",
            output_format="png",
            nsfw_checker=False,
            regenerate=False,
        )

        self.assertEqual(tuple(output.shape), (1, 8, 8, 3))
        self.assertEqual(task_id, "task-1")
        self.assertEqual(json.loads(urls_json), ["https://result.example/image.png"])

    def test_root_package_registers_stable_node_id(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "comfyui_cloudbridge_test_package",
            root / "__init__.py",
            submodule_search_locations=[str(root)],
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)

        self.assertIn(
            "CloudBridgeKieSeedream5LiteImageToImage",
            module.NODE_CLASS_MAPPINGS,
        )


if __name__ == "__main__":
    unittest.main()
