import asyncio
from typing import Any
from backend.state_manager import StateStore

class ImageUploadAgent:
    """Stub for the image‑upload pipeline.

    In a full implementation this would call the vision_service to process an
    uploaded floor‑plan image and store the resulting graph.
    """

    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    async def run(self, user_input: str) -> Any:
        # user_input is expected to contain image data or a reference; we just echo.
        self.state_store.set("image_upload_input", user_input)
        self.state_store.set("image_upload_status", "running")
        self.state_store.save_state()
        await asyncio.sleep(0)
        result = {"image_upload": f"Processed image upload request: {user_input}"}
        self.state_store.set("image_upload_status", "completed")
        self.state_store.set("image_upload_result", result)
        self.state_store.save_state()
        return result
