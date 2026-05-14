# Task 2: AI Embedding & Database Save Pipeline

## Objective
Build the pipeline that processes admin-approved graph data, uses AI to create a rich embedding summary, and saves the final data to the databases. Ensure LangSmith tracing is active.

## Requirements

### 1. AI Embedding Generation
- Create a new AI chain (e.g., in `backend/services/rag_service.py` or a new `embedding_pipeline.py`).
- This chain must take the raw, admin-edited JSON `graph_data` (nodes, edges, labels, doors) and prompt an LLM to generate a rich, natural language summary of the floor plan layout.
- The LLM generation step must be traced by LangSmith.

### 2. Vector Database Insertion
- Take the LLM-generated textual summary from the previous step and insert it into the Vector Database using the existing `rag_service`.

### 3. PostgreSQL Database Insertion
- Save the structured `graph_data` into the PostgreSQL navigation database using the existing `navigation_service.save_graph` method.

### 4. API Endpoint Updates
- Update the `/admin/save_graph` endpoint in `backend/main.py` to trigger this AI Embedding Pipeline when the admin clicks save.
- Ensure the endpoint handles the transition from the temporary draft JSON to permanent database storage seamlessly.
