import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse

from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Load env variables (GROQ_API_KEY, POSTGRES_URL)
from pathlib import Path
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

# HTML Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Import the LangGraph compiled agent and RAG service
from backend.agents.hospital_agent import hospital_agent_app
from backend.services.rag_service import rag_service
from backend.services.vision_service import vision_service

# --- Models ---
class ChatRequest(BaseModel):
    user_id: str
    message: str = ""

class ChatResponse(BaseModel):
    response: str

class UpdatePlanRequest(BaseModel):
    # Optional ID. If provided, updates existing rule. If None, makes new rule.
    location_id: str | None = None
    document: str

# --- App Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("GROQ_API_KEY"):
        print("WARNING: GROQ_API_KEY is not set. The LLM nodes will fail.")
    yield

# --- FastAPI Setup ---
app = FastAPI(title="Hospital AI Agent API", lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def get_chat_ui():
    html_content = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)

@app.post("/update_floor_plan")
async def update_floor_plan(
    file: UploadFile = File(None),
    document: str = Form(None),
    location_id: str = Form(None)
):
    print("\n" + "="*70)
    print("[API /update_floor_plan] >>> REQUEST RECEIVED")
    print(f"[API /update_floor_plan] file={file.filename if file else None}, document_len={len(document) if document else 0}, location_id={location_id}")
    print("="*70)
    try:
        if file:
            print(f"[API /update_floor_plan] STEP 1: Reading image file: {file.filename} (content_type={file.content_type})")
            file_bytes = await file.read()
            print(f"[API /update_floor_plan] STEP 2: File read complete. Size={len(file_bytes)} bytes")
            print(f"[API /update_floor_plan] STEP 3: Calling vision_service.extract_floor_plan_from_image()...")
            extracted_text = vision_service.extract_floor_plan_from_image(file_bytes, file.content_type)
            print(f"[API /update_floor_plan] STEP 4: Vision extraction complete. Extracted text length={len(extracted_text)}")
            print(f"[API /update_floor_plan] STEP 4a: Extracted text preview: {extracted_text[:500]}...")
            print(f"[API /update_floor_plan] STEP 5: Calling rag_service.insert_document()...")
            doc_id = rag_service.insert_document(extracted_text, location_id)
            print(f"[API /update_floor_plan] STEP 6: Document inserted. IDs={doc_id}")
            print(f"[API /update_floor_plan] <<< SUCCESS (image mode)")
            return {
                "status": "success", 
                "message": "Floor plan image structured visually successfully.",
                "location_id": doc_id,
                "extracted_text": extracted_text
            }
        elif document:
            print(f"[API /update_floor_plan] STEP 1: Text document received. Length={len(document)}")
            print(f"[API /update_floor_plan] STEP 1a: Document preview: {document[:500]}...")
            print(f"[API /update_floor_plan] STEP 2: Calling rag_service.insert_document()...")
            doc_id = rag_service.insert_document(document, location_id)
            print(f"[API /update_floor_plan] STEP 3: Document inserted. IDs={doc_id}")
            print(f"[API /update_floor_plan] <<< SUCCESS (text mode)")
            return {
                "status": "success", 
                "message": "Floor plan structured successfully.",
                "location_id": doc_id
            }
        else:
             raise HTTPException(status_code=400, detail="Must provide either 'file' (image) or 'document' (text).")
    except Exception as e:
        print(f"[API /update_floor_plan] <<< ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/clear_floor_plan")
async def clear_floor_plan():
    print("\n" + "="*70)
    print("[API /clear_floor_plan] >>> REQUEST RECEIVED")
    print("="*70)
    try:
        print("[API /clear_floor_plan] STEP 1: Calling rag_service.clear_database()...")
        rag_service.clear_database()
        print("[API /clear_floor_plan] STEP 2: Database cleared successfully.")
        print("[API /clear_floor_plan] <<< SUCCESS")
        return {"status": "success", "message": "All floor plan data cleared successfully."}
    except Exception as e:
        print(f"[API /clear_floor_plan] <<< ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    print("\n" + "="*70)
    print(f"[API /chat] >>> REQUEST RECEIVED")
    print(f"[API /chat] user_id={request.user_id}, message='{request.message}'")
    print("="*70)
    try:
        # Only pass fields that must reset per-message.
        # Booking fields (booking_phase, selected_doctor, etc.) are managed
        # by the checkpointer and must NOT be overwritten here.
        initial_state = {
            "user_id": request.user_id,
            "messages": [HumanMessage(content=request.message)],
            "intent": "",
            "context": "",
        }
        print(f"[API /chat] STEP 1: Initial state prepared: user_id={request.user_id}, intent='', context=''")
        
        # 2. Invoke the compiled LangGraph workflow
        config = {"configurable": {"thread_id": request.user_id}}
        print(f"[API /chat] STEP 2: Invoking LangGraph workflow (thread_id={request.user_id})...")
        result = hospital_agent_app.invoke(initial_state, config=config)
        
        # 3. Extract the last message (which is the AIMessage generated by response node)
        final_message = result["messages"][-1].content
        print(f"[API /chat] STEP 3: Workflow complete.")
        print(f"[API /chat] Final intent={result.get('intent')}, context_len={len(result.get('context', ''))}")
        print(f"[API /chat] Final message: {final_message[:300]}...")
        print(f"[API /chat] <<< SUCCESS")
        
        return ChatResponse(response=final_message)
        
    except Exception as e:
        print(f"[API /chat] <<< ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
