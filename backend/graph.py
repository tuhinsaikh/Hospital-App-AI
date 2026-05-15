import asyncio
from .agents.supervisor_agent import SupervisorAgent
from .state_manager import StateStore

# Simple orchestration entry point
_state_store = StateStore()
_supervisor = SupervisorAgent(state_store=_state_store)

async def handle_user_input(user_input: str):
    """Convenient async wrapper to process a request via the SupervisorAgent.

    Example usage:
        result = asyncio.run(handle_user_input("Find ICU beds"))
    """
    return await _supervisor.handle_request(user_input)

# Sync helper for environments where async is cumbersome
def handle_user_input_sync(user_input: str):
    return asyncio.run(handle_user_input(user_input))
