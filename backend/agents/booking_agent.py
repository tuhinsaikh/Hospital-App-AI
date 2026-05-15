import asyncio
from typing import Any
from ..state_manager import StateStore

class BookingAgent:
    """Stub booking sub‑agent.

    Future implementation will interact with the booking_service to schedule appointments.
    """

    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    async def run(self, user_input: str) -> Any:
        self.state_store.set("booking_input", user_input)
        self.state_store.set("booking_status", "running")
        self.state_store.save_state()
        await asyncio.sleep(0)
        result = {"booking": f"Processed booking request: {user_input}"}
        self.state_store.set("booking_status", "completed")
        self.state_store.set("booking_result", result)
        self.state_store.save_state()
        return result
