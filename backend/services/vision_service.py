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
            # Requires GOOGLE_API_KEY to be set
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key or api_key == "your_gemini_api_key_here":
                raise ValueError("GOOGLE_API_KEY not set for Gemini Vision.")
            return ChatGoogleGenerativeAI(model="gemini-1.5-flash")
        else:
            # Default to local (Ollama)
            base_url = os.getenv("OLLAMA_BASE_URL") or "http://192.168.1.202:11434"
            model = os.getenv("OLLAMA_VISION_MODEL") or "gemma3:27b"
            return ChatOllama(base_url=base_url, model=model, temperature=0.1)

    def extract_floor_plan_from_image(self, file_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Uses a Vision-Language Model to extract structured details about the floor plan
        from the provided image bytes.
        """
        llm = self._get_vision_llm()
        
        # Base64 encode the image
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        prompt_text = (
            "You are an expert Hospital Layout Architect. "
            "Please analyze this image of a hospital floor plan and extract a highly detailed textual description of it. "
            "List all the floors, departments, rooms, and prominent paths shown in the image. "
            "Structure your output cleanly so it can be used in a vector database for answering navigation questions."
        )
        
        # Construct the multimodal message
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                },
            ]
        )
        
        try:
            # Invoke the VLM
            response = llm.invoke([message])
            return response.content
        except Exception as e:
             raise Exception(f"Failed to process image with Vision model ({self.provider}): {str(e)}")

# Singleton instance
vision_service = VisionService()
