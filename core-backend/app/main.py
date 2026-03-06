import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv(Path(__file__).parent.parent / ".env")

from app.agents.hospital_agent import hospital_agent_app
from app.services.rag_service import rag_service
from app.services.vision_service import vision_service

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# --- Pydantic models ---
class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    response: str

class UpdatePlanRequest(BaseModel):
    location_id: str | None = None
    document: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("GROQ_API_KEY") and os.getenv("LLM_PROVIDER", "groq") == "groq":
        print("WARNING: GROQ_API_KEY is not set.")
    yield


app = FastAPI(
    title="Hospital AI Agent — Core Backend",
    description="Handles AI chat, RAG retrieval, and floor plan ingestion.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def get_chat_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "core-backend"}


@app.post("/update_floor_plan")
async def update_floor_plan(
    file: UploadFile = File(None),
    document: str = Form(None),
    location_id: str = Form(None),
):
    try:
        if file:
            file_bytes = await file.read()
            extracted_text = vision_service.extract_floor_plan_from_image(file_bytes, file.content_type)
            doc_ids = rag_service.insert_document(extracted_text, location_id)
            return {
                "status": "success",
                "message": "Floor plan image processed successfully.",
                "location_ids": doc_ids,
                "extracted_text": extracted_text,
            }
        elif document:
            doc_ids = rag_service.insert_document(document, location_id)
            return {"status": "success", "message": "Floor plan stored.", "location_ids": doc_ids}
        else:
            raise HTTPException(status_code=400, detail="Provide 'file' (image) or 'document' (text).")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Error] Floor plan ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clear_floor_plan")
async def clear_floor_plan():
    try:
        rag_service.clear_database()
        return {"status": "success", "message": "All floor plan data cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        initial_state = {
            "user_id": request.user_id,
            "messages": [HumanMessage(content=request.message)],
            "intent": "",
            "search_query": "",
            "context": "",
        }
        config = {"configurable": {"thread_id": request.user_id}}
        result = hospital_agent_app.invoke(initial_state, config=config)
        return ChatResponse(response=result["messages"][-1].content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
