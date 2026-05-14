# Task 4: Booking Sub-Agent with ToolNode

## Objective
Build the Booking Agent using LangGraph's `ToolNode` to enable autonomous appointment scheduling based on LLM decisions.

## Requirements

### 1. Tool Creation
- Create a new file: `backend/agents/booking_agent.py`.
- Wrap existing functions from `backend/services/booking_service.py` (e.g., `find_doctor_by_name`, `get_available_slots`, `book_appointment`) with LangChain's `@tool` decorator. Include clear descriptions so the LLM understands when and how to use them.

### 2. StateGraph Construction
- Build a `StateGraph` specifically for the Booking Agent, utilizing the booking sub-state defined in Task 3.
- Bind the newly created tools to the LLM (`llm.bind_tools(tools)`).

### 3. ToolNode Integration
- Add a `ToolNode` to the graph.
- Define the flow such that the LLM Node can invoke tools, the ToolNode executes them, and returns the result to the LLM Node. The agent should loop autonomously until it gathers all necessary information (doctor, slot, patient name, reason) and successfully books the appointment.

### 4. Integration
- Integrate this compiled Booking sub-graph into the Supervisor's routing logic (replacing the placeholder node from Task 3).
- Ensure all tool executions and LLM loops within this sub-agent are visible in LangSmith traces.
