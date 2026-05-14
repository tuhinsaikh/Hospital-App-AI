# Task 1: Admin Image Upload & Processing Pipeline

## Objective
Finalize the LangGraph/LangChain pipeline to process uploaded floor plans and save them as temporary drafts. This must include proper LangSmith tracing.

## Requirements

### 1. LangSmith Setup
- Add LangSmith environment variables to the `.env` file if not already present:
  ```env
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=your_api_key
  LANGCHAIN_PROJECT=hospital_agent
  ```
- Ensure tracing is initialized in `backend/main.py` or the relevant entry point.

### 2. Vision Extraction Verification
- Verify that `backend/services/vision_service.py` is correctly configured to use an LLM (like `ChatGroq` or `ChatOllama`) that supports structured output for extracting nodes, edges, doors, and paths from an image.
- Ensure the LLM calls within the vision service are tracked by LangSmith.

### 3. API Endpoint Updates
- Review and update the `/update_floor_plan` endpoint in `backend/main.py`.
- The endpoint must process the uploaded image, call the vision service to extract the graph data, and save the result **strictly** to a temporary JSON draft file in the `tmp/floor_plan_drafts/` directory.
- **CRITICAL**: The extracted data must NOT be saved to PostgreSQL or the Vector Database at this stage. It is purely temporary for admin review.

### 4. Code Quality
- Provide clear comments and modularize the extraction logic so the AI can easily read, maintain, and trace the code execution in LangSmith.
