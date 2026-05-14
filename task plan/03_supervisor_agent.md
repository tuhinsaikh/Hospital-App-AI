# Task 3: State Management & Supervisor Agent

## Objective
Implement the core `Supervisor` agent and global state definitions to route incoming chat requests to specific sub-agents. Ensure LangSmith tracing is active.

## Requirements

### 1. State Definitions
- Create a new file: `backend/agents/state.py`.
- Define a global `AgentState` schema (using `TypedDict` or Pydantic).
- This global state must incorporate fields for the sub-states, such as a `BookingState` and a `NavigationState`, allowing data to be segregated appropriately.

### 2. Supervisor Agent Creation
- Create a new file: `backend/agents/supervisor.py`.
- Implement a LangGraph `StateGraph` for the Supervisor.
- Add an `intent_detection` node that uses an LLM with structured output to analyze conversation history and classify the user's intent into predefined categories: `NAVIGATION`, `EMERGENCY`, `BOOKING`, or `GENERAL`.

### 3. Conditional Routing
- Use LangGraph's conditional edges (`add_conditional_edges`) in the Supervisor graph.
- Route the flow to dummy/placeholder nodes representing the sub-agents (e.g., a simple node that prints "Routing to Booking Agent"). These placeholders will be fully implemented in later tasks.

### 4. LangSmith Tracing
- Ensure the Supervisor's graph compilation and execution are fully traced in LangSmith to monitor intent detection accuracy.
