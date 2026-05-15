# Supervisor Agent Task Plan

## Objective
Design and implement a **Supervisor Agent** that orchestrates specialized sub‑agents (navigation, booking, emergencies, etc.) within the Hospital‑App‑AI system. The supervisor must maintain a **perfect state**—ensuring deterministic, reproducible behavior across sessions—and leverage the **Gemma** LLM for decision‑making and planning.
Context Update
The project now includes two prerequisite pipelines:
- **01_image_upload_pipeline.md** – handles image upload, preprocessing, and initial graph extraction.
- **02_ai_embedding_pipeline.md** – generates embeddings for extracted graph data and stores them in the vector database.

The Supervisor Agent will sit atop these pipelines, detecting user intents and routing requests to the appropriate sub‑agent or pipeline.

## Key Requirements
- **Perfect State Management**
  - Centralized state store (e.g., Redis or in‑memory singleton) that records the current workflow, sub‑agent statuses, and intermediate outputs.
  - Immutable snapshots after each transition to allow rollback and audit.
  - Serialize state to JSON for persistence between runs.
- **Gemma Integration**
  - Use the local Gemma model (via Ollama or direct API) for all LLM calls.
  - Prompt engineering for clear task decomposition and error handling.
- **Modular Sub‑Agents**
  - Define clear interfaces (`input`, `output`, `status`) for navigation, booking, emergency handling, etc.
  - Supervisor decides which sub‑agent to invoke based on intent analysis.
- **Tool Nodes**
  - Wrap external tools (database, image processing) as LangGraph `ToolNode`s, callable by the supervisor.
- **Observability**
  - Emit events to LangSmith for tracing.
  - Log state transitions and LLM responses.

## Implementation Steps
1. **State Layer**
   - Create `backend/state_manager.py` with `StateStore` class.
   - Implement `save_state`, `load_state`, `snapshot`, and `rollback` methods.
2. **Gemma Wrapper**
   - Add `backend/llm/gemma_client.py` to abstract model calls.
   - Provide `generate(prompt, temperature=0.0)` returning deterministic output.
3. **Supervisor Agent**
   - Create `backend/agents/supervisor_agent.py` using LangGraph.
   - Define nodes: `IntentNode`, `DispatchNode`, `StateUpdateNode`.
   - Integrate `StateStore` and `GemmaClient`.
4. **Sub‑Agent Stubs**
   - Scaffold `navigation_agent.py`, `booking_agent.py`, `emergency_agent.py` with standard `run(state)` signatures.
5. **Tool Nodes**
   - Wrap existing services (`rag_service`, `navigation_service`) as LangGraph `ToolNode`s.
6. **Orchestration Flow**
   - Build LangGraph graph connecting nodes, ensuring each transition records a state snapshot.
7. **Testing**
   - Write unit tests for state persistence and rollback.
   - Simulate end‑to‑end scenarios using a mock Gemma response.
8. **Documentation**
   - Add README section explaining perfect state concept and how to switch LLM models.

## Verification Plan
- **Automated Tests**: Run `pytest` to confirm state snapshots match expected JSON after each step.
- **Manual Walkthrough**: Execute a sample user request (e.g., "Find available ICU beds") and observe state logs.
- **Performance Check**: Ensure Gemma responses are deterministic (temperature=0) and latency < 500 ms.
- **Observability**: Verify LangSmith traces contain all state change events.

---
*This plan follows the user's request to use Gemma and maintain a perfect state.*
