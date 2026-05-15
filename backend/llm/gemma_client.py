import os
from typing import Any, Dict
from langchain_ollama import ChatOllama

class GemmaClient:
    """Wrapper around the local Gemma model accessed via Ollama.

    The project already uses environment variables ``OLLAMA_BASE_URL`` and ``OLLAMA_MODEL``
    for other services. We follow the same pattern here, defaulting to the Gemma model.
    """

    def __init__(self, temperature: float = 0.0):
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        model = os.getenv("OLLAMA_MODEL", "gemma2:9b")  # Adjust as needed for your local install
        self.llm = ChatOllama(base_url=base_url, model=model, temperature=temperature)

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate a deterministic response from the Gemma model.

        ``temperature`` is fixed at 0.0 for perfect‑state behavior, but you may override
        via ``kwargs`` if needed.
        """
        # LangChain's ChatOllama expects a list of messages. We provide a single user message.
        response = self.llm.invoke([{"role": "user", "content": prompt}])
        # ``invoke`` returns either a string or a LangChain Message object; we handle both.
        if isinstance(response, str):
            return response.strip()
        # Fallback: extract content attribute if present
        return getattr(response, "content", str(response)).strip()
