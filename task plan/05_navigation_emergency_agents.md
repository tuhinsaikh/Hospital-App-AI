# Task 5: Navigation & Emergency Sub-Agents

## Objective
Implement the remaining sub-agents (Navigation and Emergency) and complete the integration of the multi-agent system.

## Requirements

### 1. Navigation Agent
- Create a new file: `backend/agents/navigation_agent.py`.
- Wrap navigation functions (`query_vector_db` from `rag_service.py`, `get_navigation_path` from `navigation_service.py`) as LangChain `@tool`s.
- Build the Navigation `StateGraph` with a `ToolNode` to handle RAG queries and Dijkstra pathfinding autonomously. The agent should use these tools to answer questions like "where is the cafeteria" or "how do I get to Ward A".

### 2. Emergency Agent
- Create a new file: `backend/agents/emergency_agent.py`.
- Build a simpler `StateGraph` for the Emergency Agent. This agent likely does not need complex tool calling; it should focus on immediate, hardcoded, or highly constrained critical responses (e.g., "Call 911 immediately").

### 3. Final Integration & Testing
- Hook both the Navigation and Emergency graphs into the main Supervisor router (replacing their placeholders from Task 3).
- Perform end-to-end testing of the entire multi-agent system via the chat endpoint.
- Verify through LangSmith that intents are correctly routed by the Supervisor and that the appropriate sub-agent successfully executes its `ToolNode` or LLM logic to return a final response.
