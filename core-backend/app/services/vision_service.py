import os
import base64
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI


class VisionService:
    def __init__(self):
        self.provider = os.getenv("VISION_PROVIDER", "local").lower()

    def _get_vision_llm(self):
        if self.provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not set for Gemini Vision.")
            return ChatGoogleGenerativeAI(model="gemini-1.5-flash")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_VISION_MODEL", "gemma3:27b")
        return ChatOllama(base_url=base_url, model=model, temperature=0.1)

    def extract_floor_plan_from_image(self, file_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """Uses a Vision-Language Model to extract floor plan details from an image."""
        llm = self._get_vision_llm()
        base64_image = base64.b64encode(file_bytes).decode("utf-8")
        prompt_text = (
            "You are an expert Hospital Layout Architect. "
            "Analyze this hospital floor plan image and extract a detailed textual description. "
            "List all floors, departments, rooms, and paths shown. "
            "Structure the output for use in a vector database for navigation questions."
        )
        message = HumanMessage(content=[
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
        ])
        try:
            response = llm.invoke([message])
            return response.content
        except Exception as e:
            raise Exception(f"Vision model ({self.provider}) failed: {str(e)}")


vision_service = VisionService()
