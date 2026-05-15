import asyncio
from typing import Dict, Any

from ..state_manager import StateStore
from ..llm.gemma_client import GemmaClient
from ..agents.navigation_agent import NavigationAgent
from ..agents.booking_agent import BookingAgent
from ..agents.emergency_agent import EmergencyAgent
from ..agents.image_upload_agent import ImageUploadAgent
from ..agents.embedding_agent import EmbeddingAgent

class SupervisorAgent:
    """Supervisor orchestrates sub‑agents based on intent detected via Gemma.

    It maintains a perfect state using ``StateStore``. After each step a snapshot is
    recorded for audit/rollback.
    """

    def __init__(self, state_store: StateStore = None):
        self.state_store = state_store or StateStore()
        self.llm = GemmaClient(temperature=0.0)
        # Initialize sub‑agents (they receive the same state store)
        self.sub_agents = {
            "image_upload": ImageUploadAgent(self.state_store),
            "embedding": EmbeddingAgent(self.state_store),
            "navigation": NavigationAgent(self.state_store),
            "booking": BookingAgent(self.state_store),
            "emergency": EmergencyAgent(self.state_store),
        }

    async def handle_request(self, user_input: str) -> Any:
        """Process a user request: detect intent, dispatch, update state.
        """
        # Record initial snapshot
        self.state_store.set("last_input", user_input)
        self.state_store.set("status", "detect_intent")
        self.state_store.save_state()
        # Intent detection via Gemma
        intent_prompt = (
            "You are an intent classifier for a hospital AI system. "
            "Given the user request, output one of the following intents exactly: "
            "image_upload, embedding, navigation, booking, emergency, unknown.\n"
            f"User request: {user_input}\nIntent:" 
        )
        intent = self.llm.generate(intent_prompt).strip().lower()
        # Fallback
        if intent not in self.sub_agents:
            intent = "unknown"
        # Update state
        self.state_store.set("intent", intent)
        self.state_store.set("status", "dispatch")
        self.state_store.save_state()
        # Dispatch to sub‑agent
        if intent == "unknown":
            result = {"error": "Intent not recognized"}
        else:
            sub_agent = self.sub_agents[intent]
            result = await sub_agent.run(user_input)
        # Final state update
        self.state_store.set("result", result)
        self.state_store.set("status", "completed")
        self.state_store.save_state()
        return result
