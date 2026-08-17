from .cloudbridge.nodes.kie_seedream import KieSeedream5LiteImageToImage


NODE_CLASS_MAPPINGS = {
    "CloudBridgeKieSeedream5LiteImageToImage": KieSeedream5LiteImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CloudBridgeKieSeedream5LiteImageToImage": (
        "☁️ Kie.ai · Seedream 5 Lite · Image to Image"
    ),
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
